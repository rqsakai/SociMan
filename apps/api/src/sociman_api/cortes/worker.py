"""Worker dos cortes (research R1, R2 e R5): `sociman worker`, um corte por vez.

Laço: devolve à fila os abandonados → confere o HD (sem o sentinela, não pega nada e espera
`WORKER_POLL_S`) → pega o próximo → processa → repete (fila vazia: espera 2 s).

Processar um corte, tudo em `${SOCIMAN_DATA_DIR}/work/cortes/{id}/` (removida no fim):
1. exige no HD livre ≥ 3× o original (cópia de trabalho, resultado e resultado no MinIO);
2. baixa o original do bucket de vídeos e confere com o ffprobe;
3. baixa as fontes e imagens do kit (`kit_tokens`, resolvidos no envio; inclusive as de fundo
   do gancho e do card final) e renderiza as camadas;
4. compõe com o ffmpeg, gravando o progresso no banco (junto com o heartbeat, a cada 2 s);
5. envia o `marcado.mp4` (vídeos) e o pôster, o quadro do meio do original (imagens, para a
   prévia do kit no navegador, R7), e marca `pronto`.

Falhas viram `falhou` com a razão em pt-BR (o usuário pode tentar de novo). Parar o worker
(SIGTERM) ou perder o HD no meio devolve o corte à fila sem contar tentativa.
"""

import logging
import shutil
import signal
import threading
import time
from pathlib import Path
from typing import Any

from sociman_api import datadir, storage
from sociman_api.canais import models as _canais_models  # noqa: F401 (FKs, ver abaixo)
from sociman_api.config import get_settings
from sociman_api.cortes import compose, queue
from sociman_api.cortes.compose import ComposeError
from sociman_api.cortes.probe import InvalidVideo, probe
from sociman_api.cortes.queue import Job
from sociman_api.cortes.render import (
    EndCardStyle,
    HookStyle,
    KitRender,
    WatermarkStyle,
    render_layers,
)
from sociman_api.envios import models as _envios_models  # noqa: F401 (FKs, ver abaixo)
from sociman_api.errors import ApiError
from sociman_api.marca.tokens import DEFAULT_FONTS

# Fora da API, nada mais registra as tabelas referenciadas por `cortes` (perfis, users e, desde
# a spec 006, envios → canais_fonte e videos_fonte): sem estes imports o SQLAlchemy não resolve
# as FKs no primeiro UPDATE.
from sociman_api.perfis import models as _perfis_models  # noqa: F401

log = logging.getLogger("sociman.worker")

IDLE_S = 2.0  # fila vazia
HEARTBEAT_S = 2.0
FONTS_DIR = Path(__file__).resolve().parents[1] / "marca" / "fonts"
EXT = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm"}

LOW_SPACE = "Pouco espaço no HD de dados"
INTERNAL = "Erro interno ao processar o corte; tente de novo"


class Interrupted(Exception):
    """O worker foi parado, ou o corte deixou de ser deste processamento."""


# ---- caminhos ----

def work_root() -> Path:
    return Path(get_settings().data_dir) / "work" / "cortes"


def original_key(perfil_id: Any, corte_id: Any, content_type: str) -> str:
    return f"perfis/{perfil_id}/cortes/{corte_id}/original.{EXT[content_type]}"


def result_key(perfil_id: Any, corte_id: Any) -> str:
    return f"perfis/{perfil_id}/cortes/{corte_id}/marcado.mp4"


def poster_key(perfil_id: Any, corte_id: Any) -> str:
    return f"perfis/{perfil_id}/cortes/{corte_id}/poster.jpg"


def cleanup_workdirs() -> int:
    """Remove as pastas de trabalho que sobraram de um worker morto (só há uma réplica)."""
    if datadir.status().reason == "sem_sentinela":
        return 0
    root = work_root()
    if not root.is_dir():
        return 0
    removed = 0
    for child in root.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed


# ---- kit_tokens → KitRender (mapeamento documentado em render.py) ----

def font_file(fonte: dict[str, Any], dest: Path) -> Path:
    """O arquivo de uma fonte resolvida: padrão (no pacote) ou do perfil (baixada para `dest`)."""
    if fonte.get("padrao"):
        return FONTS_DIR / DEFAULT_FONTS[fonte["padrao"]].filename
    key = fonte["object_key"]
    path = dest / f"fonte-{Path(key).name}"
    if not path.exists():
        storage.get_to_file(key, path, bucket="fontes")
    return path


def image_file(key: str, dest: Path, name: str) -> Path:
    path = dest / f"{name}{Path(key).suffix}"
    if not path.exists():
        storage.get_to_file(key, path, bucket="imagens")
    return path


def fundo_file(section: dict[str, Any], dest: Path, name: str) -> Path | None:
    """A imagem de fundo da seção (FR-005a), baixada para `dest`; None com fundo de cor.

    Cortes enfileirados antes do fundo com imagem não têm `fundo_tipo`: valem como cor."""
    if section.get("fundo_tipo") != "imagem" or not section.get("fundo_imagem_key"):
        return None
    return image_file(section["fundo_imagem_key"], dest, name)


def hook_style(hook: dict[str, Any], font_path: Path,
               bg_image_path: Path | None = None) -> HookStyle:
    return HookStyle(font_path=font_path, text_color=hook["cor_texto"],
                     bg_color=hook["cor_fundo"], bg_opacity=float(hook["opacidade_fundo"]),
                     stroke_color=hook["cor_contorno"],
                     stroke_width=float(hook["espessura_contorno"]), position=hook["posicao"],
                     size=hook["tamanho"], duration_s=float(hook["duracao_s"]),
                     bg_image_path=bg_image_path)


def kit_render(tokens: dict[str, Any], dest: Path) -> KitRender:
    """Os estilos do render a partir dos tokens resolvidos, baixando os arquivos para `dest`."""
    hook = tokens["hook"]
    hook_st = None
    if hook["ligado"]:
        hook_st = hook_style(hook, font_file(hook["fonte"], dest),
                             fundo_file(hook, dest, "fundo-gancho"))

    wm = tokens["watermark"]
    wm_st = None
    if wm["ligado"]:
        common: dict[str, Any] = {
            "position": wm["posicao"], "scale_pct": float(wm["escala_pct"]),
            "opacity_pct": float(wm["opacidade_pct"]), "margin_pct": float(wm["margem_pct"]),
        }
        if wm["tipo"] == "texto" and wm.get("texto"):
            wm_st = WatermarkStyle(kind="texto", text=wm["texto"],
                                   font_path=font_file(wm["fonte"], dest),
                                   text_color=wm["cor_texto"], **common)
        elif wm["tipo"] == "imagem" and wm.get("imagem_key"):
            wm_st = WatermarkStyle(kind="imagem",
                                   image_path=image_file(wm["imagem_key"], dest, "marca-src"),
                                   **common)
        elif wm["tipo"] == "logo" and wm.get("logo_key"):
            wm_st = WatermarkStyle(kind="imagem",
                                   image_path=image_file(wm["logo_key"], dest, "logo-src"),
                                   **common)

    card = tokens["end_card"]
    card_st = None
    if card["ligado"]:
        logo = None
        if card["mostrar_logo"] and card.get("logo_key"):
            logo = image_file(card["logo_key"], dest, "logo-src")
        card_st = EndCardStyle(cta=card["cta"], font_path=font_file(card["fonte"], dest),
                               text_color=card["cor_texto"], bg_color=card["cor_fundo"],
                               duration_s=float(card["duracao_s"]), logo_path=logo,
                               bg_image_path=fundo_file(card, dest, "fundo-card"),
                               bg_opacity=float(card.get("opacidade_fundo", 0.45)))
    return KitRender(hook=hook_st, watermark=wm_st, end_card=card_st)


# ---- heartbeat ----

class _Heartbeat(threading.Thread):
    """Grava progresso e `heartbeat_at` a cada 2 s enquanto o corte é processado."""

    def __init__(self, job: Job, interval: float = HEARTBEAT_S):
        super().__init__(name=f"heartbeat-{job.id}", daemon=True)
        self.job = job
        self.interval = interval
        self.progress = 0
        self.lost = threading.Event()
        self._done = threading.Event()

    def run(self) -> None:
        while not self._done.wait(self.interval):
            try:
                if not queue.heartbeat(self.job, self.progress):
                    self.lost.set()
                    return
            except Exception:  # banco fora por um instante não derruba o corte
                log.warning("heartbeat do corte %s falhou", self.job.id, exc_info=True)

    def stop(self) -> None:
        self._done.set()
        self.join(timeout=5)


# ---- processamento ----

def process(job: Job, stop: threading.Event | None = None) -> str:
    """Processa um corte já pego pela fila. Devolve o status final: pronto, falhou ou na_fila."""
    stop = stop or threading.Event()
    started = time.monotonic()
    workdir = work_root() / str(job.id)
    beat = _Heartbeat(job)

    def elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    def check() -> None:
        if stop.is_set() or beat.lost.is_set():
            raise Interrupted

    def on_progress(pct: int) -> None:
        beat.progress = pct
        check()

    def fail(code: str, message: str) -> str:
        queue.finish_failed(job, code=code, message=message, processing_ms=elapsed_ms())
        return "falhou"

    try:
        try:
            # 3×: a cópia de trabalho, o resultado temporário e o resultado no MinIO.
            datadir.ensure_writable(3 * job.original_bytes)
        except ApiError as exc:
            if exc.status == 507:
                return fail("low_space", LOW_SPACE)
            raise
        workdir.mkdir(parents=True, exist_ok=True)
        beat.start()

        src = workdir / f"original.{EXT.get(job.original_content_type, 'mp4')}"
        storage.get_to_file(job.original_key, src, bucket="videos")
        check()
        info = probe(src)
        kit = kit_render(job.kit_tokens, workdir)
        overlays = render_layers(workdir, hook_text=job.hook_text, kit=kit, width=info.width,
                                 height=info.height, duration_s=info.duration_s)
        check()

        dst = workdir / "marcado.mp4"
        compose.compose(src, overlays, dst, duration_s=info.duration_s,
                        audio_codec=info.audio_codec, on_progress=on_progress, workdir=workdir)
        check()

        poster = workdir / "poster.jpg"
        compose.extract_frame(src, info.duration_s / 2, poster)
        p_key = poster_key(job.perfil_id, job.id)
        storage.put(p_key, poster.read_bytes(), "image/jpeg", bucket="imagens")
        r_key = result_key(job.perfil_id, job.id)
        r_bytes = storage.put_file(r_key, dst, "video/mp4", bucket="videos")
        beat.stop()
        if not queue.finish_ok(job, result_key=r_key, result_bytes=r_bytes, poster_key=p_key,
                               processing_ms=elapsed_ms()):
            log.warning("corte %s deixou de ser deste processamento antes do fim", job.id)
            return "na_fila"
        log.info("corte %s pronto em %d ms", job.id, elapsed_ms())
        return "pronto"
    except Interrupted:
        queue.release(job)
        log.info("corte %s devolvido à fila (worker parado ou corte retomado)", job.id)
        return "na_fila"
    except InvalidVideo:
        return fail("corrupted", compose.CORRUPTED)
    except ComposeError as exc:
        log.warning("ffmpeg falhou no corte %s (%s): %s", job.id, exc.code, exc.detail[-500:])
        return fail(exc.code, exc.message)
    except Exception as exc:  # qualquer outra falha vira "falhou", nunca some
        if datadir.status().reason == "sem_sentinela":
            queue.release(job)
            log.warning("HD de dados sumiu durante o corte %s; devolvido à fila", job.id)
            return "na_fila"
        if isinstance(exc, ApiError) and exc.status == 507:
            return fail("low_space", LOW_SPACE)
        log.exception("erro interno no corte %s", job.id)
        return fail("internal", INTERNAL)
    finally:
        if beat.is_alive():
            beat.stop()
        shutil.rmtree(workdir, ignore_errors=True)


def run_once(stop: threading.Event | None = None) -> str | None:
    """Uma volta do laço: None = nada feito (sem HD ou fila vazia)."""
    queue.requeue_stale()
    if datadir.status().reason == "sem_sentinela":
        return None
    job = queue.claim()
    if job is None:
        return None
    log.info("corte %s: tentativa %d", job.id, job.attempts)
    return process(job, stop)


def run(stop: threading.Event) -> None:
    """Laço do worker até `stop`. Erros de banco ou MinIO são registrados e o laço segue."""
    try:
        removed = cleanup_workdirs()
        if removed:
            log.info("%d pasta(s) de trabalho antigas removidas", removed)
    except OSError:
        log.warning("não foi possível limpar work/cortes", exc_info=True)
    while not stop.is_set():
        wait = IDLE_S
        try:
            if datadir.status().reason == "sem_sentinela":
                log.warning("HD de dados sem o sentinela; nenhum corte será pego")
                wait = get_settings().worker_poll_s
                queue.requeue_stale()
            elif run_once(stop) is not None:
                wait = 0
        except Exception:  # o worker não morre por uma falha passageira
            log.exception("falha no laço do worker")
            wait = get_settings().worker_poll_s
        if wait:
            stop.wait(wait)


def main() -> None:
    """`sociman worker`: SIGTERM ou SIGINT param o laço (o corte atual volta à fila)."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = threading.Event()

    def _stop(signum: int, _frame: Any) -> None:
        log.info("sinal %s: parando depois de devolver o corte atual à fila", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker de cortes no ar (HD em %s)", get_settings().data_dir)
    run(stop)
    log.info("worker parado")
