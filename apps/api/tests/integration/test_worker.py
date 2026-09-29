"""Worker dos cortes (T025, SC-004 e SC-007): processamento completo com ffmpeg e MinIO reais,
falhas com a razão em pt-BR, HD fora e o laço rodando numa thread."""

import io
import subprocess
import threading
import time
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image as PILImage
from PIL import ImageStat
from sqlalchemy import text

from sociman_api import storage
from sociman_api.config import get_settings
from sociman_api.cortes import compose, queue, render, worker
from sociman_api.cortes.models import Corte, CorteStatus
from sociman_api.cortes.service import resolve_corte_tokens
from sociman_api.db import get_sessionmaker
from sociman_api.marca.tokens import default_kit
from sociman_api.perfis.models import Image, ImageKind, Perfil

GRAY = (128, 128, 128)
YELLOW = (255, 229, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)


@pytest.fixture(scope="module", autouse=True)
def _buckets():
    storage.ensure_buckets()


def make_video(path: Path, *, size: str = "1080x1920", seconds: float = 6,
               audio: bool = True) -> Path:
    args = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=0x808080:s={size}:d={seconds}:r=30"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac"]
    subprocess.run([*args, str(path)], check=True, timeout=120)
    return path


def mean(frame: Path, box: tuple[int, int, int, int]) -> tuple[float, ...]:
    with PILImage.open(frame) as img:
        return tuple(ImageStat.Stat(img.convert("RGB").crop(box)).mean)


def close(color: tuple[float, ...], expected: tuple[int, int, int], tol: float = 20) -> bool:
    return all(abs(c - e) <= tol for c, e in zip(color, expected, strict=True))


def _perfil(db) -> Perfil:
    perfil = Perfil(slug=f"p-{uuid.uuid4().hex[:8]}", name="Perfil")
    db.add(perfil)
    db.commit()
    return perfil


def _red_watermark(db, perfil: Perfil) -> Image:
    buf = io.BytesIO()
    PILImage.new("RGBA", (200, 100), (*RED, 255)).save(buf, format="PNG")
    key = f"perfis/{perfil.id}/{uuid.uuid4()}.png"
    storage.put(key, buf.getvalue(), "image/png", bucket="imagens")
    image = Image(perfil_id=perfil.id, kind=ImageKind.watermark, object_key=key,
                  content_type="image/png", bytes=len(buf.getvalue()), width=200, height=100,
                  sha256="0" * 64)
    db.add(image)
    db.commit()
    return image


def branded_tokens(db, perfil: Perfil) -> dict:
    """Gancho amarelo (2 s), marca d'água vermelha e card azul (1,5 s)."""
    image = _red_watermark(db, perfil)
    kit = default_kit()
    kit = kit.model_copy(update={
        "hook": kit.hook.model_copy(update={"cor_fundo": "#FFE500", "opacidade_fundo": 1.0,
                                            "duracao_s": 2.0}),
        "watermark": kit.watermark.model_copy(update={
            "ligado": True, "tipo": "imagem", "imagem_id": image.id, "opacidade_pct": 100}),
        "end_card": kit.end_card.model_copy(update={"ligado": True, "cor_fundo": "#0000FF",
                                                    "cta": "Segue", "duracao_s": 1.5}),
    })
    return resolve_corte_tokens(db, perfil, kit)


def enqueue(db, perfil: Perfil, video: Path, tokens: dict, *, content_type="video/mp4",
            hook_text="Olha isso", width=1080, height=1920, duration_ms=6000) -> Corte:
    cid = uuid.uuid4()
    key = worker.original_key(perfil.id, cid, content_type)
    size = storage.put_file(key, video, content_type, bucket="videos")
    corte = Corte(
        id=cid, perfil_id=perfil.id, hook_text=hook_text, kit_version=0, kit_tokens=tokens,
        original_filename=video.name, original_key=key, original_content_type=content_type,
        original_bytes=size, duration_ms=duration_ms, width=width, height=height,
        fps=Decimal(30), video_codec="h264", audio_codec="aac", original_sha256="0" * 64,
    )
    db.add(corte)
    db.commit()
    return corte


def _get(corte_id) -> Corte:
    with get_sessionmaker()() as s:
        return s.get(Corte, corte_id)


@pytest.fixture
def hd_fora(tmp_path, monkeypatch):
    """HD sem o sentinela (desmontado)."""
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "hd-fora"))


# ---- processamento completo ----

def test_processa_corte_com_as_tres_camadas(db, tmp_path):
    perfil = _perfil(db)
    tokens = branded_tokens(db, perfil)
    corte = enqueue(db, perfil, make_video(tmp_path / "in.mp4"), tokens)

    started = time.monotonic()
    assert worker.run_once() == "pronto"
    elapsed = time.monotonic() - started

    row = _get(corte.id)
    assert row.status == CorteStatus.pronto and row.progress == 100 and row.attempts == 1
    assert row.result_key == f"perfis/{perfil.id}/cortes/{corte.id}/marcado.mp4"
    assert row.poster_key == f"perfis/{perfil.id}/cortes/{corte.id}/poster.jpg"
    assert row.result_bytes == storage.stat(row.result_key, bucket="videos").size
    assert 0 < row.processing_ms <= elapsed * 1000 + 50
    assert row.finished_at is not None and row.heartbeat_at is None
    # A pasta de trabalho some no fim.
    assert not (worker.work_root() / str(corte.id)).exists()

    # O pôster é o quadro do meio do ORIGINAL (fundo da prévia do kit): cinza, sem camadas.
    poster = PILImage.open(io.BytesIO(storage.get(row.poster_key, bucket="imagens")))
    assert poster.size == (1080, 1920)
    assert close(ImageStat.Stat(poster.convert("RGB")).mean, GRAY)

    out = tmp_path / "marcado.mp4"
    storage.get_to_file(row.result_key, out, bucket="videos")
    kit = worker.kit_render(tokens, tmp_path)
    hook = render.render_hook("Olha isso", kit.hook, 1080, 1920)
    wm = render.render_watermark(kit.watermark, 1080, 1920)
    hh = hook.image.height
    hook_edge = (hook.x + 6, hook.y + hh // 2 - 4, hook.x + 22, hook.y + hh // 2 + 4)
    ww, wh = wm.image.size
    wm_box = (wm.x + 10, wm.y + 10, wm.x + ww - 10, wm.y + wh - 10)
    for t, name in ((0.5, "ini"), (3.0, "meio"), (5.5, "fim")):
        compose.extract_frame(out, t, tmp_path / f"{name}.png")
    ini, meio, fim = (tmp_path / f"{n}.png" for n in ("ini", "meio", "fim"))
    assert close(mean(ini, hook_edge), YELLOW)
    assert close(mean(ini, wm_box), RED)
    assert close(mean(meio, hook_edge), GRAY)
    assert close(mean(meio, wm_box), RED)
    assert close(mean(fim, (0, 0, 200, 200)), BLUE)
    assert close(mean(fim, wm_box), BLUE)


GREEN = (0, 255, 0)


def _fundo_meio_a_meio(db, perfil: Perfil) -> Image:
    """Imagem de fundo quadrada: metade esquerda vermelha, metade direita verde."""
    img = PILImage.new("RGB", (1200, 1200), RED)
    img.paste(GREEN, (600, 0, 1200, 1200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    key = f"perfis/{perfil.id}/{uuid.uuid4()}.png"
    storage.put(key, buf.getvalue(), "image/png", bucket="imagens")
    image = Image(perfil_id=perfil.id, kind=ImageKind.fundo, object_key=key,
                  content_type="image/png", bytes=len(buf.getvalue()), width=1200,
                  height=1200, sha256="0" * 64)
    db.add(image)
    db.commit()
    return image


def _mix(color: tuple[int, int, int], layer: tuple[int, int, int], opacity: float
         ) -> tuple[int, int, int]:
    r, g, b = (round(c * (1 - opacity) + ly * opacity) for c, ly in zip(color, layer,
                                                                        strict=True))
    return r, g, b


def test_fundo_com_imagem_no_gancho_e_no_card_final(db, tmp_path):
    """FR-005a: a imagem (cover) aparece sob a camada de cor, no gancho e no quadro final."""
    perfil = _perfil(db)
    fundo = _fundo_meio_a_meio(db, perfil)
    kit = default_kit()
    kit = kit.model_copy(update={
        "hook": kit.hook.model_copy(update={
            "cor_fundo": "#FFFFFF", "opacidade_fundo": 0.5, "duracao_s": 2.0,
            "fundo_tipo": "imagem", "fundo_imagem_id": fundo.id}),
        "end_card": kit.end_card.model_copy(update={
            "ligado": True, "cor_fundo": "#000000", "cor_texto": "#FFFFFF", "cta": "Segue",
            "duracao_s": 1.5, "fundo_tipo": "imagem", "fundo_imagem_id": fundo.id,
            "opacidade_fundo": 0.4}),
    })
    tokens = resolve_corte_tokens(db, perfil, kit)
    assert tokens["hook"]["fundo_imagem_key"] == fundo.object_key
    assert tokens["end_card"]["fundo_imagem_key"] == fundo.object_key
    corte = enqueue(db, perfil, make_video(tmp_path / "in.mp4"), tokens)
    assert worker.run_once() == "pronto"

    row = _get(corte.id)
    out = tmp_path / "marcado.mp4"
    storage.get_to_file(row.result_key, out, bucket="videos")
    style = worker.kit_render(tokens, tmp_path)
    assert style.hook.bg_image_path is not None and style.end_card.bg_image_path is not None
    hook = render.render_hook("Olha isso", style.hook, 1080, 1920)
    hw, hh = hook.image.size
    # Faixa do padding de cima da caixa (sem texto), nas duas metades.
    left = (hook.x + 30, hook.y + 4, hook.x + hw // 2 - 30, hook.y + 10)
    right = (hook.x + hw // 2 + 30, hook.y + 4, hook.x + hw - 30, hook.y + 10)
    for t, name in ((0.5, "ini"), (5.5, "fim")):
        compose.extract_frame(out, t, tmp_path / f"{name}.png")
    ini, fim = tmp_path / "ini.png", tmp_path / "fim.png"

    white = (255, 255, 255)
    assert close(mean(ini, left), _mix(RED, white, 0.5), tol=25)
    assert close(mean(ini, right), _mix(GREEN, white, 0.5), tol=25)
    # O texto (preto) continua por cima da camada.
    with PILImage.open(ini) as frame:
        box = frame.convert("L").crop((hook.x, hook.y, hook.x + hw, hook.y + hh))
        assert box.getextrema()[0] < 60

    # Quadro final: a imagem cobre o quadro inteiro (cover centralizado: divisa em x = 540)
    # sob a camada preta a 40%; o CTA branco continua por cima.
    black = (0, 0, 0)
    assert close(mean(fim, (40, 100, 400, 400)), _mix(RED, black, 0.4), tol=25)
    assert close(mean(fim, (680, 100, 1040, 400)), _mix(GREEN, black, 0.4), tol=25)
    assert close(mean(fim, (40, 1500, 400, 1800)), _mix(RED, black, 0.4), tol=25)
    with PILImage.open(fim) as frame:
        center = frame.convert("L").crop((0, 800, 1080, 1120))
        assert center.getextrema()[1] > 200


def test_video_corrompido_falha_com_razao(db, tmp_path):
    perfil = _perfil(db)
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"isto nao e video" * 100)
    corte = enqueue(db, perfil, bad, branded_tokens(db, perfil))
    assert worker.run_once() == "falhou"
    row = _get(corte.id)
    assert row.status == CorteStatus.falhou and row.error_code == "corrupted"
    assert row.error_message == "O vídeo está corrompido ou não pôde ser lido"
    assert row.result_key is None
    assert not (worker.work_root() / str(corte.id)).exists()


def test_pouco_espaco_falha_sem_baixar(db, tmp_path, monkeypatch):
    perfil = _perfil(db)
    corte = enqueue(db, perfil, make_video(tmp_path / "in.mp4", seconds=2),
                    branded_tokens(db, perfil), duration_ms=2000)
    monkeypatch.setattr(get_settings(), "data_min_free_gb", 10**6)
    assert worker.run_once() == "falhou"
    row = _get(corte.id)
    assert (row.error_code, row.error_message) == ("low_space", "Pouco espaço no HD de dados")


def test_sem_hd_nao_pega_corte(db, tmp_path, hd_fora):
    perfil = _perfil(db)
    corte = Corte(
        perfil_id=perfil.id, hook_text="x", kit_version=0, kit_tokens={},
        original_filename="v.mp4", original_key=f"perfis/{perfil.id}/{uuid.uuid4()}.mp4",
        original_content_type="video/mp4", original_bytes=10, duration_ms=1000, width=1080,
        height=1920, fps=Decimal(30), video_codec="h264", original_sha256="0" * 64,
    )
    db.add(corte)
    db.commit()
    assert worker.run_once() is None
    row = _get(corte.id)
    assert row.status == CorteStatus.na_fila and row.attempts == 0


def test_parar_o_worker_devolve_a_fila_sem_tentativa(db, tmp_path):
    perfil = _perfil(db)
    corte = enqueue(db, perfil, make_video(tmp_path / "in.mp4", seconds=2),
                    branded_tokens(db, perfil), duration_ms=2000)
    stop = threading.Event()
    stop.set()
    assert worker.run_once(stop) == "na_fila"
    row = _get(corte.id)
    assert row.status == CorteStatus.na_fila and row.attempts == 0
    assert not (worker.work_root() / str(corte.id)).exists()


def test_limpa_sobras_ao_subir():
    sobra = worker.work_root() / str(uuid.uuid4())
    (sobra / "sub").mkdir(parents=True)
    (sobra / "sub" / "x.bin").write_bytes(b"x")
    assert worker.cleanup_workdirs() >= 1
    assert not sobra.exists()
    assert worker.work_root().is_dir()


def test_laco_em_thread_processa_e_requeue(db, tmp_path):
    """O laço de `sociman worker` numa thread: devolve o abandonado à fila e processa os dois."""
    perfil = _perfil(db)
    tokens = branded_tokens(db, perfil)
    abandonado = enqueue(db, perfil, make_video(tmp_path / "a.mp4", seconds=2), tokens,
                         duration_ms=2000)
    novo = enqueue(db, perfil, make_video(tmp_path / "b.mp4", seconds=2), tokens,
                   duration_ms=2000)
    job = queue.claim()
    assert job.id == abandonado.id
    db.execute(text("UPDATE cortes SET heartbeat_at = now() - interval '5 minutes' "
                    "WHERE id = :id"), {"id": abandonado.id})
    db.commit()

    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            states = {_get(c.id).status for c in (abandonado, novo)}
            if states == {CorteStatus.pronto}:
                break
            time.sleep(0.5)
    finally:
        stop.set()
        thread.join(timeout=30)
    assert not thread.is_alive()
    assert _get(abandonado.id).status == CorteStatus.pronto
    assert _get(abandonado.id).attempts == 2
    assert _get(novo.id).status == CorteStatus.pronto


def test_worker_sozinho_resolve_as_fks():
    """`sociman worker` não importa a app: o módulo precisa registrar perfis e users sozinho
    (sem isso o primeiro UPDATE falhava com NoReferencedTableError)."""
    code = ("import sociman_api.cortes.worker\n"
            "from sociman_api.cortes.models import Corte\n"
            "print(sorted(fk.column.table.name for fk in Corte.__table__.foreign_keys))\n")
    out = subprocess.run(["python", "-c", code], capture_output=True, text=True, timeout=60,
                         check=False)
    assert out.returncode == 0, out.stderr
    assert "perfis" in out.stdout and "users" in out.stdout
