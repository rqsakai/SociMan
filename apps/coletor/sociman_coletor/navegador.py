"""Chrome real do dono + CDP (contracts/coletor.md, "Navegador").

- Lança o Chrome do sistema com **exatamente** as flags do contrato (sem nenhuma de automação):
  `--user-data-dir=<perfil> --remote-debugging-port=0 --no-first-run --no-default-browser-check
  --lang=pt-BR --window-size=1280,900`. A porta de depuração (efêmera, só loopback) é lida de
  `<perfil>/DevToolsActivePort` e a conexão é `connect_over_cdp("http://127.0.0.1:<porta>")`.
- `flock` exclusivo em `<perfil>/.sociman.lock`: outro processo no mesmo perfil → `perfil_em_uso`.
- Uma única aba (`context.pages[0]`); abas novas são fechadas na hora; downloads cancelados.
- Interceptação **passiva** por `page.on("response")`: só guarda o JSON das URLs da lista fechada
  `INTERCEPTAR` do adaptador e anota as imagens carregadas. Nunca `route`, nunca reproduz chamada.
- `perfil-iniciar` abre o Chrome **sem** CDP na página de login e espera o dono fechar.
"""

from __future__ import annotations

import fcntl
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from sociman_coletor import log
from sociman_coletor.redes.base import Interceptada

CANDIDATOS_CHROME = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
FLAGS_CHROME: tuple[str, ...] = (
    "--no-first-run",
    "--no-default-browser-check",
    "--lang=pt-BR",
    "--window-size=1280,900",
)
ARQUIVO_PORTA = "DevToolsActivePort"
ARQUIVO_LOCK = ".sociman.lock"
ESPERA_PORTA_S = 30.0
ESPERA_FECHAR_S = 10.0
ESPERA_INTERCEPTADAS_MS = 15_000
INTERCEPTADA_BYTES_MAX = 2 * 1024 * 1024
_VERSAO = re.compile(r"(\d+\.\d+\.\d+(?:\.\d+)?)")


class ErroNavegador(Exception):
    def __init__(self, codigo: str, mensagem: str = ""):
        super().__init__(mensagem or codigo)
        self.codigo = codigo


def achar_chrome(chrome_bin: str | None = None) -> str:
    """`chrome_bin` do config, ou o primeiro de `CANDIDATOS_CHROME` no PATH."""
    if chrome_bin:
        caminho = Path(chrome_bin).expanduser()
        if caminho.exists():
            return str(caminho)
        achado = shutil.which(chrome_bin)
        if achado:
            return achado
        raise ErroNavegador("chrome_ausente", f"chrome_bin não encontrado: {chrome_bin}")
    for nome in CANDIDATOS_CHROME:
        achado = shutil.which(nome)
        if achado:
            return achado
    raise ErroNavegador("chrome_ausente", "nenhum Chrome/Chromium no PATH; defina chrome_bin")


def linha_de_comando(
    chrome: str, perfil_dir: Path, cdp: bool = True, url: str | None = None
) -> list[str]:
    """A linha de comando do Chrome. Com `cdp=False` (perfil-iniciar) não há porta de depuração."""
    linha = [chrome, f"--user-data-dir={perfil_dir}"]
    if cdp:
        linha.append("--remote-debugging-port=0")
    linha.extend(FLAGS_CHROME)
    if url:
        linha.append(url)
    return linha


def versao_chrome(chrome: str) -> str | None:
    try:
        saida = subprocess.run(
            [chrome, "--version"], capture_output=True, text=True, timeout=15, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = _VERSAO.search(saida or "")
    return m.group(1) if m else None


def ler_porta(perfil_dir: Path) -> int | None:
    arquivo = perfil_dir / ARQUIVO_PORTA
    try:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        return int(linhas[0].strip())
    except (OSError, ValueError, IndexError):
        return None


class Trava:
    """`flock` exclusivo no perfil; sai com `perfil_em_uso` se outro processo o tem."""

    def __init__(self, perfil_dir: Path):
        self._caminho = perfil_dir / ARQUIVO_LOCK
        self._fd: int | None = None

    def adquirir(self) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self._caminho, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise ErroNavegador("perfil_em_uso", "outro coletor usa este perfil do Chrome") from exc
        self._fd = fd

    def livre(self) -> bool:
        try:
            self.adquirir()
        except ErroNavegador:
            return False
        self.soltar()
        return True

    def soltar(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
            self._fd = None


class Navegador:
    """Ciclo: `abrir()` (trava + lança + conecta) → `pagina` → `fechar()`.

    `flags_extra` existe **só para o teste de fluxo** (Chromium do Playwright sem janela); em
    produção fica vazia e a linha de comando é exatamente a do contrato.
    """

    def __init__(
        self,
        chrome: str,
        perfil_dir: Path,
        rede: Any,
        baixador: Any = None,
        flags_extra: tuple[str, ...] = (),
    ):
        self.chrome = chrome
        self.perfil_dir = perfil_dir
        self._rede = rede
        self._baixador = baixador
        self._flags_extra = flags_extra
        self._trava = Trava(perfil_dir)
        self._processo: subprocess.Popen | None = None
        self._pw = None
        self._browser = None
        self.pagina: Any = None
        self.versao: str | None = None
        self.interceptadas: list[Interceptada] = []
        self.ultimo_status_interceptado: int | None = None
        self._log = log.obter("navegador")

    # ---- ciclo ----

    def abrir(self) -> Any:
        self._trava.adquirir()
        try:
            self._lancar()
            self._conectar()
        except Exception:
            self.fechar()
            raise
        return self.pagina

    def _lancar(self) -> None:
        self.perfil_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        porta = self.perfil_dir / ARQUIVO_PORTA
        if porta.exists():
            porta.unlink()
        linha = linha_de_comando(self.chrome, self.perfil_dir, cdp=True)
        linha[2:2] = list(self._flags_extra)
        self._processo = subprocess.Popen(
            linha, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        limite = time.monotonic() + ESPERA_PORTA_S
        while time.monotonic() < limite:
            if self._processo.poll() is not None:
                raise ErroNavegador("chrome_saiu", "o Chrome terminou antes de abrir a porta")
            if ler_porta(self.perfil_dir):
                return
            time.sleep(0.2)
        raise ErroNavegador("porta_cdp", "DevToolsActivePort não apareceu a tempo")

    def _conectar(self) -> None:
        from playwright.sync_api import sync_playwright

        porta = ler_porta(self.perfil_dir)
        if not porta:
            raise ErroNavegador("porta_cdp", "porta de depuração ilegível")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
        self.versao = (
            _VERSAO.search(self._browser.version or "").group(1)
            if _VERSAO.search(self._browser.version or "")
            else None
        )
        if not self._browser.contexts:
            raise ErroNavegador("sem_contexto", "o Chrome não tem contexto padrão")
        contexto = self._browser.contexts[0]
        if not contexto.pages:
            raise ErroNavegador("sem_aba", "o Chrome abriu sem aba")
        self.pagina = contexto.pages[0]
        for extra in contexto.pages[1:]:
            self._fechar_aba(extra)
        contexto.on("page", self._fechar_aba)
        self.pagina.on("popup", self._fechar_aba)
        self.pagina.on("download", self._cancelar_download)
        self.pagina.on("response", self._ao_responder)
        if self._baixador is not None:
            self._baixador.ligar(self.pagina)
        self._log.info("conectado chrome=%s", self.versao)

    def fechar(self) -> None:
        try:
            if self._browser is not None:
                try:
                    self._browser.close()
                except Exception:  # noqa: BLE001 - já desconectado
                    pass
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:  # noqa: BLE001
                    pass
            if self._processo is not None and self._processo.poll() is None:
                self._processo.terminate()
                try:
                    self._processo.wait(timeout=ESPERA_FECHAR_S)
                except subprocess.TimeoutExpired:
                    self._processo.kill()
        finally:
            self._browser = None
            self._pw = None
            self._processo = None
            self.pagina = None
            self._trava.soltar()

    def chrome_vivo(self) -> bool:
        return self._processo is not None and self._processo.poll() is None

    # ---- eventos da página (passivos) ----

    def _fechar_aba(self, aba: Any) -> None:
        try:
            if aba is not self.pagina:
                aba.close()
                self._log.info("aba extra fechada")
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _cancelar_download(download: Any) -> None:
        try:
            download.cancel()
        except Exception:  # noqa: BLE001
            pass

    def _ao_responder(self, resposta: Any) -> None:
        """Interceptação passiva: guarda o JSON das URLs da lista fechada; anota imagens."""
        try:
            url = resposta.url
        except Exception:  # noqa: BLE001
            return
        if self._baixador is not None:
            self._baixador.registrar_resposta(resposta)
        if not self._rede.intercepta(url):
            return
        self.ultimo_status_interceptado = resposta.status
        try:
            corpo = resposta.body()
            if len(corpo) > INTERCEPTADA_BYTES_MAX:
                self._log.info("interceptada grande ignorada bytes=%d", len(corpo))
                return
            dados = resposta.json()
        except Exception:  # noqa: BLE001 - não era JSON ou a resposta já se foi
            return
        self.interceptadas.append(Interceptada(url, resposta.status, dados))

    def nova_pagina(self) -> None:
        self.interceptadas = []
        self.ultimo_status_interceptado = None
        if self._baixador is not None:
            self._baixador.nova_pagina()

    def esperar_interceptadas(
        self, pagina: Any, minimo: int = 1, ms: int = ESPERA_INTERCEPTADAS_MS
    ) -> None:
        """Espera (em fatias) até `minimo` respostas interceptadas ou o tempo acabar."""
        if not self._rede.INTERCEPTAR:
            return
        fatia = 250
        passado = 0
        while len(self.interceptadas) < minimo and passado < ms:
            pagina.wait_for_timeout(fatia)
            passado += fatia


def perfil_iniciar(chrome: str, perfil_dir: Path, url_login: str) -> int:
    """Abre o Chrome **sem CDP** no perfil dedicado, na página de login, e espera o dono fechar."""
    perfil_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    trava = Trava(perfil_dir)
    trava.adquirir()
    try:
        processo = subprocess.Popen(
            linha_de_comando(chrome, perfil_dir, cdp=False, url=url_login),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return processo.wait()
    finally:
        trava.soltar()
