"""O laço do coletor (contracts/coletor.md, "Ciclo de uma rodada"; FR-016 a FR-019, FR-023).

```text
janela.dentro() e sem PARAR
  └─▶ GET /fila → tarefas=[] → dormir (motivoVazia decide quanto)
      └─▶ POST /coletas (409 coleta_em_andamento → esperar 5 min; nunca forçar)
          └─▶ navegador.abrir() (Chrome + CDP; 1 aba)
              para cada tarefa: pausa → abrir URL → sinais → coletar → podar → imagens (antes)
                → itens (lotes ≤ 10) → batimento a cada 60 s (thread) → parar=true sai
                → a cada BLOCO_PAGINAS: pausa longa
              fim ou orçamento → POST /fim {motivo}
          captcha | login_perdido → evento; Chrome aberto; espera `continuarEm` por batimento
            + CAPTCHA_ESFRIAR_MIN; `parar=true` (pausa_vencida) → /fim
          bloqueio_suspeito | layout_mudou → evento → /fim → recuo local de 24 h
```

Relógio (`relogio`), espera longa (`dormir`) e o transporte HTTP são injetáveis para os testes.
"""

from __future__ import annotations

import base64
import gzip
import json
import resource
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sociman_coletor import __version__, api, janela, log, modelos, privacidade, ritmo, sinais
from sociman_coletor.config import Config, Segredo, tem_tela
from sociman_coletor.estado import Estado
from sociman_coletor.imagens import Baixador
from sociman_coletor.navegacao import Navegacao, UrlForaDaTarefa
from sociman_coletor.navegador import ErroNavegador, Navegador, achar_chrome, versao_chrome
from sociman_coletor.redes.base import Resultado
from sociman_coletor.redes.tiktok_shop import TIPOS_RESERVADOS, definir

BATIMENTO_S = 60
BRUTO_BYTES_MAX = 2 * 1024 * 1024
DORMIR_SEM_TELA_S = 15 * 60
DORMIR_ERRO_REDE_S = 60
TENTATIVAS_COLETA_EM_ANDAMENTO = 12
PAUSA_MAX_H = sinais.CAPTCHA_ESPERA_MAX_H + 1  # rede do coletor: o servidor encerra antes


class Parou(Exception):
    """Sinal interno: o laço deve fechar a rodada com este `motivo`."""

    def __init__(self, motivo: str, codigo_saida: int = 3):
        super().__init__(motivo)
        self.motivo = motivo
        self.codigo_saida = codigo_saida


def _agora_utc() -> datetime:
    return datetime.now(UTC)


def _memoria_mb() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024)


def comprimir_bruto(bruto: Any) -> str | None:
    """gzip + base64 do JSON (≤ 2 MB descomprimido; maior → None, o item vai sem bruto)."""
    texto = json.dumps(bruto, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(texto) > BRUTO_BYTES_MAX:
        return None
    return base64.b64encode(gzip.compress(texto, 6)).decode("ascii")


def _e_fechado_pelo_dono(exc: Exception) -> bool:
    texto = f"{type(exc).__name__} {exc}".lower()
    return (
        "target closed" in texto
        or "targetclosed" in texto
        or "browser has been closed" in texto
        or "connection closed" in texto
    )


class Coletor:
    """Uma instância por processo. `rede` = adaptador (`redes.tiktok_shop.AdaptadorTikTokShop`)."""

    def __init__(
        self,
        cfg: Config,
        token: Segredo,
        rede: Any,
        *,
        transport: Any = None,
        relogio: Callable[[], datetime] = _agora_utc,
        dormir: Callable[[float], None] = time.sleep,
        esperar_pagina: Callable[[Any, int], None] | None = None,
        fabrica_navegador: Callable[[Baixador], Navegador] | None = None,
        semente: int | None = None,
        batimento_s: float = BATIMENTO_S,
    ):
        self.cfg = cfg
        self.rede = rede
        self.relogio = relogio
        self.dormir = dormir
        self._esperar_pagina = esperar_pagina
        self._fabrica_navegador = fabrica_navegador
        self._batimento_s = batimento_s
        self.log = log.obter("rodada")
        self.estado = Estado.carregar(cfg.caminho_estado)
        self.estado.registrar_pid()
        self.parada = sinais.PedidoParada()
        self.api = api.ClienteApi(cfg, token, transport=transport, dormir=dormir)
        self.ritmo = ritmo.Ritmo(semente=semente)
        self.limites: ritmo.LimitesEfetivos | None = None
        self.fuso = "America/Sao_Paulo"
        # estado da rodada corrente
        self._coleta_id: str | None = None
        self._tarefa_atual: str | None = None
        self._parar_servidor: str | None = None
        self._continuar_em: datetime | None = None
        self._batimento_parar = threading.Event()
        self._batimento_pausado = threading.Event()
        self._thread: threading.Thread | None = None
        self._navegador: Navegador | None = None

    # ---- utilidades ----

    def _pedido_parada(self) -> str | None:
        if sinais.parar_local(self.cfg.caminho_parar):
            return "parar_local"
        if self.parada.pedido:
            return "servico_parado"
        return None

    def _novo_navegador(self, baixador: Baixador) -> Navegador:
        if self._fabrica_navegador is not None:
            return self._fabrica_navegador(baixador)
        chrome = achar_chrome(self.cfg.chrome_bin)
        return Navegador(chrome, self.cfg.perfil_dir, self.rede, baixador)

    def _dormir_ate(self, instante: datetime, maximo_s: float = 15 * 60) -> None:
        agora = self.relogio()
        falta = (instante - agora).total_seconds()
        self.dormir(max(1.0, min(falta, maximo_s)))

    def _aplicar_fila(self, fila: modelos.Fila) -> None:
        self.fuso = fila.fuso
        self.estado.virar_dia(fila.data_local)
        self.estado.ultima_fila_em = fila.agora_servidor
        self.limites = ritmo.limites_efetivos(self.cfg.limites, fila.limites, fila.janela)
        self.ritmo = ritmo.Ritmo(
            self.limites.pausa_min_s,
            self.limites.pausa_max_s,
            semente=self.ritmo.rng.randrange(1 << 30),
        )
        self.estado.salvar()

    # ---- laço contínuo ----

    def rodar(self) -> int:
        """`rodar`: sai só por sinal (código 3), `PARAR` (0) ou parada do serviço (4/5)."""
        self.parada.instalar()
        if self.cfg.caminho_parar.exists():
            self.cfg.caminho_parar.unlink()
        try:
            while True:
                if self.parada.pedido:
                    self._evento("parado")
                    return 3
                if sinais.parar_local(self.cfg.caminho_parar):
                    self.log.info("PARAR presente; encerrando")
                    return 0
                if not tem_tela():
                    self.log.warning("sem_tela: sem DISPLAY/WAYLAND_DISPLAY; tentando em 15 min")
                    self.dormir(DORMIR_SEM_TELA_S)
                    continue
                agora = self.relogio()
                if self.estado.em_recuo(agora):
                    self.log.info("em recuo local; dormindo")
                    self._dormir_ate(self.estado.recuo_ate)  # type: ignore[arg-type]
                    continue
                try:
                    fila = self.api.fila(self._limite_fila())
                except api.ColetaDesligada:
                    self.log.info("coleta desligada no servidor; dormindo 15 min")
                    self.dormir(api.DORMIR_DESLIGADA_S)
                    continue
                except api.ErroRede as exc:
                    self.log.warning("sem resposta do SociMan (%s); tentando em 60 s", exc)
                    self.dormir(DORMIR_ERRO_REDE_S)
                    continue
                self._aplicar_fila(fila)
                if not fila.habilitada or not fila.tarefas:
                    self._dormir_fila_vazia(fila)
                    continue
                if (
                    self.limites
                    and self.limites.janela
                    and not self.limites.janela.dentro(self.relogio(), self.fuso)
                ):
                    self.log.info("fora da janela local; dormindo ate abrir")
                    self._dormir_ate(
                        self.limites.janela.proxima_abertura(self.relogio(), self.fuso)
                    )
                    continue
                try:
                    self.executar_rodada(fila)
                except api.ColetaDesligada:
                    self.dormir(api.DORMIR_DESLIGADA_S)
                except api.ErroRede as exc:
                    self.log.warning("falha de rede na rodada: %s", exc)
                    self.dormir(DORMIR_ERRO_REDE_S)
        except api.ParaServico as exc:
            self.log.error("parando o servico: %s (codigo %d)", exc.codigo, exc.codigo_saida)
            self._evento("parado")
            return exc.codigo_saida
        finally:
            self.api.fechar()

    def _limite_fila(self) -> int:
        if self.limites is not None:
            return self.limites.itens_por_coleta
        return 40

    def _dormir_fila_vazia(self, fila: modelos.Fila) -> None:
        motivo = fila.motivo_vazia or "nada_a_coletar"
        self.log.info("fila vazia motivo=%s", motivo)
        agora = self.relogio()
        if motivo == "fora_da_janela":
            j = janela.Janela(fila.janela.inicio, fila.janela.fim)
            alvo = j.proxima_abertura(agora, self.fuso) + timedelta(
                minutes=self.ritmo.jitter_janela_min()
            )
            self._dormir_ate(alvo, maximo_s=60 * 60)
        elif motivo == "orcamento":
            self._dormir_ate(janela.proximo_dia_local(agora, self.fuso), maximo_s=60 * 60)
        elif motivo == "pausada" and fila.pausada_ate is not None:
            self._dormir_ate(fila.pausada_ate)
        else:
            self.dormir(self.ritmo.dormir_fila_vazia_s())

    # ---- uma rodada ----

    def uma_vez(self, limite: int, fora_da_janela: bool = False) -> int:
        """Uma rodada com até `limite` páginas; fecha com `motivo = "limite"`. 0 se tudo
        `gravado|repetido`; 2 se houve `erro|invalido`; 3 se parou por sinal."""
        self.parada.instalar()
        try:
            fila = self.api.fila(limite)
            self._aplicar_fila(fila)
            if not fila.habilitada or not fila.tarefas:
                self.log.info("fila vazia motivo=%s", fila.motivo_vazia)
                return 0
            if not fora_da_janela and not fila.janela.dentro:
                self.log.info("fora da janela do servidor; use --fora-da-janela na sonda")
                return 0
            resumo = self.executar_rodada(fila, limite_paginas=limite, motivo_fim="limite")
        except api.ParaServico as exc:
            self.log.error("parando: %s", exc.codigo)
            return exc.codigo_saida
        finally:
            self.api.fechar()
        if resumo["parou_por_sinal"]:
            return 3
        return 2 if resumo["com_erro"] else 0

    def executar_rodada(
        self, fila: modelos.Fila, limite_paginas: int | None = None, motivo_fim: str = "fila_vazia"
    ) -> dict[str, Any]:
        assert self.limites is not None
        coleta = self._abrir_rodada()
        self._coleta_id = coleta.id
        self.estado.salvar()
        resumo: dict[str, Any] = {
            "paginas": 0,
            "imagens": 0,
            "por_tipo": {},
            "com_erro": False,
            "parou_por_sinal": False,
            "motivo": motivo_fim,
            "resultados": [],
        }
        baixador = Baixador(self.rede)
        self._navegador = self._novo_navegador(baixador)
        motivo = motivo_fim
        try:
            try:
                pagina = self._navegador.abrir()
            except ErroNavegador as exc:
                self.log.error("navegador: %s", exc.codigo)
                motivo = "erro_interno"
                return resumo
            self.api.definir_chrome_versao(self._navegador.versao)
            self._evento(
                "iniciado",
                detalhe=privacidade.detalhe_evento(
                    versaoColetor=__version__, chromeVersao=self._navegador.versao
                ),
            )
            self._iniciar_batimento()
            navegacao = Navegacao(pagina, self.ritmo, self.rede)
            if self._esperar_pagina is not None:
                navegacao.esperar = lambda ms: self._esperar_pagina(pagina, ms)  # type: ignore
            motivo = self._percorrer(fila, navegacao, baixador, resumo, limite_paginas, motivo_fim)
        except Parou as p:
            motivo = p.motivo
            resumo["parou_por_sinal"] = p.motivo in ("parar_local", "servico_parado")
        except api.ParaServico:
            motivo = "erro_interno"
            raise
        except (api.ErroApi, api.ErroRede) as exc:
            self.log.error("erro da API na rodada: %s", exc)
            motivo = "erro_interno"
            resumo["com_erro"] = True
        except Exception as exc:  # noqa: BLE001 - nada pode deixar o Chrome e a rodada abertos
            if _e_fechado_pelo_dono(exc):
                self.log.warning("Chrome fechado pelo dono no meio da rodada")
                motivo = "servico_parado"
            else:
                self.log.error("erro inesperado na rodada: %s", type(exc).__name__,
                               exc_info=True)
                motivo = "erro_interno"
                resumo["com_erro"] = True
        finally:
            resumo["motivo"] = motivo
            self._fechar_tudo(resumo, motivo)
        return resumo

    def _abrir_rodada(self) -> modelos.Coleta:
        for _ in range(TENTATIVAS_COLETA_EM_ANDAMENTO):
            try:
                return self.api.abrir(
                    modelos.LimitesLocais(
                        paginas_dia=self.cfg.limites.paginas_dia,
                        imagens_dia=self.cfg.limites.imagens_dia,
                    ),
                    self.relogio(),
                )
            except api.ErroApi as exc:
                if exc.status == 409 and exc.codigo == "coleta_em_andamento":
                    self.log.info("rodada em andamento no servidor; esperando 5 min")
                    self.dormir(api.ESPERA_COLETA_EM_ANDAMENTO_S)
                    continue
                raise
        raise Parou("erro_interno", 2)

    def _fechar_tudo(self, resumo: dict[str, Any], motivo: str) -> None:
        self._parar_batimento()
        if self._navegador is not None:
            try:
                self._navegador.fechar()
            except Exception:  # noqa: BLE001
                pass
            self._navegador = None
        if self._coleta_id is not None:
            try:
                self.api.fechar_rodada(
                    self._coleta_id,
                    modelos.Fim(
                        motivo=motivo,
                        terminada_em=self.relogio(),
                        paginas=resumo["paginas"],
                        imagens=resumo["imagens"],
                        por_tipo=resumo["por_tipo"],
                    ),
                )
            except (api.ErroApi, api.ErroRede) as exc:
                self.log.warning("nao fechou a rodada: %s", exc)
            self._coleta_id = None
        self._tarefa_atual = None
        self.estado.salvar()
        self.log.info(
            "rodada fechada motivo=%s paginas=%d imagens=%d",
            motivo,
            resumo["paginas"],
            resumo["imagens"],
        )

    # ---- as tarefas ----

    def _percorrer(
        self,
        fila: modelos.Fila,
        navegacao: Navegacao,
        baixador: Baixador,
        resumo: dict[str, Any],
        limite_paginas: int | None,
        motivo_fim: str,
    ) -> str:
        assert self._navegador is not None and self.limites is not None
        bloqueio = sinais.ContadorBloqueio()
        layout = sinais.ContadorLayout()
        imagens_restantes = min(
            fila.orcamento.imagens_restantes,
            max(0, self.limites.imagens_dia - self.estado.imagens_hoje),
        )
        paginas_restantes = min(
            fila.orcamento.paginas_restantes,
            max(0, self.limites.paginas_dia - self.estado.paginas_hoje),
        )
        tarefas = list(fila.tarefas)
        if limite_paginas is not None:
            tarefas = tarefas[:limite_paginas]
        for tarefa in tarefas:
            pedido = self._pedido_parada()
            if pedido:
                if pedido == "parar_local":
                    self._evento("parar_local")
                raise Parou(pedido)
            if self._parar_servidor:
                return self._parar_servidor
            if self.limites.janela and not self.limites.janela.dentro(self.relogio(), self.fuso):
                return "fora_da_janela"
            if paginas_restantes <= 0:
                return "orcamento"
            self._tarefa_atual = tarefa.tarefa_id
            if tarefa.tipo in TIPOS_RESERVADOS or tarefa.tipo not in self.rede.TIPOS:
                self._enviar([self._item_erro(tarefa, "tipo_desconhecido", 0)], resumo)
                continue
            self.dormir(self.ritmo.pausa())
            inicio = time.monotonic()
            self._navegador.nova_pagina()
            navegacao.nova_tarefa(tarefa.url)
            try:
                abertura = navegacao.abrir(tarefa.url)
            except UrlForaDaTarefa:
                self._enviar([self._item_erro(tarefa, "redirecionada", inicio)], resumo)
                continue
            except Exception as exc:  # noqa: BLE001 - timeout de navegação ou Chrome fechado
                if _e_fechado_pelo_dono(exc):
                    raise
                self.log.info("timeout_navegacao tipo=%s", tarefa.tipo)
                self._enviar([self._item_erro(tarefa, "timeout_navegacao", inicio)], resumo)
                continue
            # sinais da página
            if sinais.detectar_captcha(
                abertura.url_final, abertura.titulo, abertura.iframes, self.rede.CAPTCHA_PADROES
            ):
                self._enviar(
                    [
                        modelos.Item(
                            tarefa_id=tarefa.tarefa_id,
                            status="captcha",
                            coletado_em=self.relogio(),
                            duracao_ms=self._ms(inicio),
                        )
                    ],
                    resumo,
                )
                self._pausar("captcha", tarefa, abertura.url_final)
                continue
            self._navegador.esperar_interceptadas(navegacao.pagina)
            if sinais.detectar_login(
                abertura.url_final,
                self.rede.LOGIN_PADROES,
                self.rede.sessao_invalida(self._navegador.interceptadas),
            ):
                self._enviar([self._item_erro(tarefa, "redirecionada", inicio)], resumo)
                self._pausar("login_perdido", tarefa, abertura.url_final)
                continue
            status = abertura.status
            if status is not None and status >= 400:
                codigo = "http_4xx" if status < 500 else "http_5xx"
                self._enviar([self._item_erro(tarefa, codigo, inicio)], resumo)
                if bloqueio.registrar(status):
                    self._recuar("bloqueio_suspeito", tarefa, abertura.url_final, status)
                    return "erro_interno"
                continue
            bloqueio.registrar(status)
            if abertura.redirecionada:
                self._enviar([self._item_erro(tarefa, "redirecionada", inicio)], resumo)
                continue
            navegacao.rolar()
            self._navegador.esperar_interceptadas(navegacao.pagina, minimo=1, ms=3000)
            resultado = self.rede.coletar(navegacao.pagina, tarefa, self._navegador.interceptadas)
            if layout.registrar(resultado.tem_campos):
                self._enviar(
                    [self._item_erro(tarefa, resultado.erro_codigo or "pagina_sem_campos", inicio)],
                    resumo,
                )
                self._recuar("layout_mudou", tarefa, abertura.url_final, None)
                return "erro_interno"
            if not resultado.tem_campos:
                self._enviar(
                    [self._item_erro(tarefa, resultado.erro_codigo or "pagina_sem_campos", inicio)],
                    resumo,
                )
                continue
            item, n_imagens, esgotou = self._montar_item(
                tarefa, resultado, inicio, baixador, imagens_restantes
            )
            imagens_restantes = 0 if esgotou else imagens_restantes - n_imagens
            resumo["imagens"] += n_imagens
            self.estado.contar_imagens(n_imagens)
            resposta = self._enviar([item], resumo)
            resumo["paginas"] += 1
            resumo["por_tipo"][tarefa.tipo] = resumo["por_tipo"].get(tarefa.tipo, 0) + 1
            self.estado.contar_pagina()
            self.estado.salvar()
            paginas_restantes -= 1
            if resposta is not None and resposta.orcamento is not None:
                paginas_restantes = min(paginas_restantes, resposta.orcamento.paginas_restantes)
                imagens_restantes = min(imagens_restantes, resposta.orcamento.imagens_restantes)
            if resposta is not None and resposta.parar:
                return "orcamento" if paginas_restantes <= 0 else "fila_vazia"
            if self.ritmo.e_fim_de_bloco(resumo["paginas"]):
                self.dormir(self.ritmo.pausa_longa_s())
        return motivo_fim

    @staticmethod
    def _ms(inicio: float) -> int:
        return int((time.monotonic() - inicio) * 1000) if inicio else 0

    def _item_erro(self, tarefa: modelos.Tarefa, codigo: str, inicio: float) -> modelos.Item:
        self.log.info("item erro tipo=%s codigo=%s", tarefa.tipo, codigo)
        return modelos.Item(
            tarefa_id=tarefa.tarefa_id,
            status="erro",
            coletado_em=self.relogio(),
            duracao_ms=self._ms(inicio),
            esquema_versao=self.rede.esquema,
            erro_codigo=codigo,
        )

    def _montar_item(
        self,
        tarefa: modelos.Tarefa,
        resultado: Resultado,
        inicio: float,
        baixador: Baixador,
        imagens_restantes: int,
    ) -> tuple[modelos.Item, int, bool]:
        """Poda o bruto, baixa e envia as imagens (antes do item) e monta o item `ok`."""
        assert self.limites is not None and self._coleta_id is not None
        bruto = privacidade.podar(resultado.bruto) if resultado.bruto is not None else None
        resto = privacidade.verificar(bruto) if bruto is not None else None
        if resto is not None:
            self.log.warning("bruto_pessoal_local tipo=%s", tarefa.tipo)
            return self._item_erro(tarefa, "bruto_pessoal_local", inicio), 0, False
        campos = resultado.campos or {}
        shas: list[str] = []
        esgotou = False
        n_novas = 0
        baixar = bool(tarefa.extra.get("baixarImagens", True)) and resultado.imagens
        if baixar and imagens_restantes > 0:
            maximo = min(
                int(tarefa.extra.get("imagensMax") or self.limites.imagens_por_produto),
                self.limites.imagens_por_produto,
                imagens_restantes,
            )
            download = baixador.baixar(resultado.imagens, maximo, tarefa.tarefa_id)
            aceitos: set[str] = set(baixador.cache)
            if download.novas:
                resposta = self.api.enviar_imagens(
                    self._coleta_id,
                    [
                        (
                            img.conteudo,
                            modelos.ManifestoImagem(
                                sha256=img.sha256,
                                tarefa_id=tarefa.tarefa_id,
                                origem=img.origem,
                                content_type=img.content_type,
                            ),
                        )  # type: ignore[arg-type]
                        for img in download.novas
                    ],
                )
                aceitos.update(resposta.aceitas)
                aceitos.update(resposta.repetidas)
                baixador.lembrar(resposta.aceitas)
                baixador.lembrar(resposta.repetidas)
                n_novas = len(resposta.aceitas)
                if any(r.motivo == "orcamento" for r in resposta.recusadas):
                    esgotou = True
                    self.log.info("orcamento de imagens esgotado no servidor")
            for ref in resultado.imagens:
                sha = download.mapa.get(ref.url)
                if sha and sha in aceitos:
                    if sha not in shas:
                        shas.append(sha)
                    if ref.destino:
                        try:
                            definir(campos, ref.destino, sha)
                        except (KeyError, IndexError, TypeError, ValueError):
                            pass
        item = modelos.Item(
            tarefa_id=tarefa.tarefa_id,
            status="ok",
            coletado_em=self.relogio(),
            duracao_ms=self._ms(inicio),
            esquema_versao=self.rede.esquema,
            fonte=resultado.fonte or tarefa.fonte,  # type: ignore[arg-type]
            campos=campos,
            bruto=comprimir_bruto(bruto) if bruto is not None else None,
            imagens=shas,
        )
        return item, n_novas, esgotou

    def _enviar(
        self, itens: list[modelos.Item], resumo: dict[str, Any]
    ) -> modelos.RespostaItens | None:
        assert self._coleta_id is not None
        resposta = self.api.enviar_itens(self._coleta_id, itens)
        for r in resposta.resultados:
            resumo["resultados"].append(r)
            if r.status in ("erro", "invalido"):
                resumo["com_erro"] = True
            self.log.info(
                "resultado tarefa=%s status=%s codigo=%s", r.tarefa_id, r.status, r.erro_codigo
            )
        if resposta.parar:
            self._parar_servidor = (
                "orcamento"
                if (resposta.orcamento and resposta.orcamento.paginas_restantes <= 0)
                else "fila_vazia"
            )
        return resposta

    # ---- eventos, pausas e recuos ----

    def _evento(
        self, tipo: str, tarefa: modelos.Tarefa | None = None, detalhe: dict[str, Any] | None = None
    ) -> modelos.RespostaEvento | None:
        try:
            return self.api.evento(
                modelos.Evento(
                    tipo=tipo,
                    coleta_id=self._coleta_id,  # type: ignore[arg-type]
                    tarefa_id=tarefa.tarefa_id if tarefa else None,
                    ocorreu_em=self.relogio(),
                    detalhe=detalhe or {},
                )
            )
        except (api.ErroApi, api.ErroRede) as exc:
            self.log.warning("evento %s nao enviado: %s", tipo, exc)
            return None

    def _recuar(self, tipo: str, tarefa: modelos.Tarefa, url: str, status: int | None) -> None:
        self._evento(
            tipo,
            tarefa,
            privacidade.detalhe_evento(
                codigoHttp=status, urlSemParametros=url, tipoTarefa=tarefa.tipo
            ),
        )
        self.estado.recuo_ate = self.relogio() + timedelta(hours=sinais.RECUO_BLOQUEIO_H)
        self.estado.salvar()
        self.log.warning("%s: recuo local de %d h", tipo, sinais.RECUO_BLOQUEIO_H)

    def _pausar(self, tipo: str, tarefa: modelos.Tarefa, url: str) -> None:
        """Captcha ou login perdido: evento, Chrome aberto na página, espera o "Continuar" do
        dono (por batimento) e mais `CAPTCHA_ESFRIAR_MIN`; `parar=true` encerra a rodada."""
        self._evento(
            tipo,
            tarefa,
            privacidade.detalhe_evento(urlSemParametros=url, tipoTarefa=tarefa.tipo, contagem=1),
        )
        self.log.warning("%s: aguardando o dono clicar Continuar", tipo)
        self._batimento_pausado.set()
        inicio = self.relogio()
        try:
            while True:
                pedido = self._pedido_parada()
                if pedido:
                    raise Parou(pedido)
                if self.relogio() - inicio > timedelta(hours=PAUSA_MAX_H):
                    raise Parou("pausa_vencida", 2)
                self.dormir(BATIMENTO_S)
                resposta = self._bater(estado="pausada")
                if resposta is None:
                    continue
                if resposta.parar:
                    raise Parou(resposta.motivo or "pausa_vencida", 2)
                continuar = resposta.continuar_em
                if continuar is not None and self.relogio() >= continuar + timedelta(
                    minutes=sinais.CAPTCHA_ESFRIAR_MIN
                ):
                    self._evento("retomou", tarefa)
                    self.log.info("retomou depois de %s", tipo)
                    return
        finally:
            self._batimento_pausado.clear()

    # ---- batimento ----

    def _bater(self, estado: str = "ativa") -> modelos.RespostaBatimento | None:
        if self._coleta_id is None:
            return None
        try:
            resposta = self.api.batimento(
                self._coleta_id,
                modelos.Batimento(
                    estado=estado,
                    tarefa_atual_id=self._tarefa_atual,
                    paginas_hoje=self.estado.paginas_hoje,
                    imagens_hoje=self.estado.imagens_hoje,
                    proxima_acao_em=self.relogio() + timedelta(seconds=self._batimento_s),
                    memoria_mb=_memoria_mb(),
                ),
            )
        except api.ParaServico:
            raise
        except (api.ErroApi, api.ErroRede) as exc:
            self.log.warning("batimento falhou: %s", exc)
            return None
        if resposta.parar:
            self._parar_servidor = resposta.motivo or "fila_vazia"
        self._continuar_em = resposta.continuar_em
        return resposta

    def _iniciar_batimento(self) -> None:
        self._batimento_parar.clear()

        def laco() -> None:
            while not self._batimento_parar.wait(self._batimento_s):
                if self._batimento_pausado.is_set():
                    continue
                try:
                    self._bater()
                except Exception:  # noqa: BLE001 - a thread não pode morrer com a rodada aberta
                    pass

        self._thread = threading.Thread(target=laco, name="batimento", daemon=True)
        self._thread.start()

    def _parar_batimento(self) -> None:
        self._batimento_parar.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


def versao_chrome_local(cfg: Config) -> str | None:
    try:
        return versao_chrome(achar_chrome(cfg.chrome_bin))
    except ErroNavegador:
        return None
