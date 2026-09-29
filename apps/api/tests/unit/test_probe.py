"""cortes.probe com vídeos sintéticos gerados por ffmpeg lavfi (T022, R3)."""

import subprocess
from pathlib import Path

import pytest

from sociman_api.cortes import probe
from sociman_api.cortes.probe import InvalidVideo


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args],
                   check=True, timeout=120)


def make_video(path: Path, *, size: str = "360x640", seconds: float = 1, rate: int = 30,
               audio: str | None = "aac", vcodec: str = "libx264",
               fmt: str | None = None) -> Path:
    args = ["-f", "lavfi", "-i", f"color=c=0x808080:s={size}:d={seconds}:r={rate}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    if vcodec == "libx264":
        args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    else:
        args += ["-c:v", vcodec, "-deadline", "realtime", "-cpu-used", "8", "-b:v", "200k"]
    if audio:
        args += ["-c:a", audio]
    if fmt:
        args += ["-f", fmt]
    _ffmpeg(*args, str(path))
    return path


def _reason(path: Path) -> str:
    with pytest.raises(InvalidVideo) as exc:
        probe.probe(path)
    assert exc.value.status == 400
    assert exc.value.code == "invalid_video"
    return exc.value.message


def test_mp4_com_audio(tmp_path):
    info = probe.probe(make_video(tmp_path / "a.mp4", seconds=2))
    assert info.content_type == "video/mp4"
    assert info.video_codec == "h264"
    assert info.audio_codec == "aac"
    assert (info.width, info.height) == (360, 640)
    assert info.fps == 30.0
    assert abs(info.duration_ms - 2000) <= 50
    assert info.rotation == 0


def test_mp4_sem_audio(tmp_path):
    info = probe.probe(make_video(tmp_path / "a.mp4", audio=None))
    assert info.audio_codec is None


def test_horizontal(tmp_path):
    info = probe.probe(make_video(tmp_path / "a.mp4", size="640x360"))
    assert (info.width, info.height) == (640, 360)


def test_mov_quicktime(tmp_path):
    info = probe.probe(make_video(tmp_path / "a.mov", fmt="mov"))
    assert info.content_type == "video/quicktime"


def test_webm_vp9_opus(tmp_path):
    info = probe.probe(make_video(tmp_path / "a.webm", vcodec="libvpx-vp9", audio="libopus"))
    assert info.content_type == "video/webm"
    assert (info.video_codec, info.audio_codec) == ("vp9", "opus")


def test_rotacao_troca_largura_e_altura(tmp_path):
    src = make_video(tmp_path / "a.mp4", size="640x360")
    rotated = tmp_path / "r.mp4"
    _ffmpeg("-display_rotation", "90", "-i", str(src), "-c", "copy", str(rotated))
    info = probe.probe(rotated)
    assert info.rotation in (90, 270)
    assert (info.width, info.height) == (360, 640)


def test_matroska_que_nao_e_webm(tmp_path):
    assert _reason(make_video(tmp_path / "a.mkv", fmt="matroska")) == probe.NOT_ACCEPTED


def test_texto_com_extensao_mp4(tmp_path):
    fake = tmp_path / "a.mp4"
    fake.write_text("isto não é vídeo\n" * 100)
    assert _reason(fake) == probe.NOT_ACCEPTED


def test_so_audio(tmp_path):
    path = tmp_path / "a.m4a"
    _ffmpeg("-f", "lavfi", "-i", "sine=duration=1", "-c:a", "aac", str(path))
    assert _reason(path) == probe.NOT_ACCEPTED


def test_arquivo_inexistente(tmp_path):
    assert _reason(tmp_path / "nada.mp4") == probe.NOT_ACCEPTED


def test_mais_longo_que_3_minutos(tmp_path):
    path = make_video(tmp_path / "a.mp4", size="240x240", seconds=181, rate=1, audio=None)
    assert _reason(path) == probe.TOO_LONG


def test_exatamente_3_minutos_passa(tmp_path):
    path = make_video(tmp_path / "a.mp4", size="240x240", seconds=180, rate=1, audio=None)
    assert probe.probe(path).duration_ms <= 180_000


@pytest.mark.parametrize("size", ["200x400", "4100x240"])
def test_resolucao_fora_da_faixa(tmp_path, size):
    path = make_video(tmp_path / "a.mp4", size=size, audio=None, rate=1)
    assert _reason(path) == probe.BAD_RESOLUTION


def test_maior_que_o_limite(tmp_path, monkeypatch):
    path = make_video(tmp_path / "a.mp4", audio=None)
    monkeypatch.setattr(probe, "MAX_BYTES", path.stat().st_size - 1)
    assert _reason(path) == probe.TOO_BIG
