"""cortes.compose com ffmpeg real (T024, SC-004): quadros amostrados e duração igual."""

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageFont, ImageStat

from sociman_api.cortes import compose, render
from sociman_api.cortes.compose import ComposeError
from sociman_api.cortes.render import EndCardStyle, HookStyle, KitRender, Overlay, WatermarkStyle

GRAY = (128, 128, 128)
YELLOW = (255, 229, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args],
                   check=True, timeout=300)


def make_video(path: Path, *, size: str, seconds: float, audio: str | None = "aac",
               vcodec: str = "libx264") -> Path:
    args = ["-f", "lavfi", "-i", f"color=c=0x808080:s={size}:d={seconds}:r=30"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    if vcodec == "libx264":
        args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    else:
        args += ["-c:v", vcodec, "-deadline", "realtime", "-cpu-used", "8", "-b:v", "300k"]
    if audio:
        args += ["-c:a", audio]
    _ffmpeg(*args, str(path))
    return path


def ffprobe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                          "-show_streams", str(path)], capture_output=True, check=True)
    return json.loads(out.stdout)


def duration(info: dict) -> float:
    return float(info["format"]["duration"])


def streams(info: dict, kind: str) -> list[dict]:
    return [s for s in info["streams"] if s["codec_type"] == kind]


@pytest.fixture(scope="module")
def font_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("fonts") / "pillow.ttf"
    path.write_bytes(ImageFont.load_default(20).font_bytes)
    return path


def kit(font_path: Path, logo_path: Path) -> KitRender:
    return KitRender(
        hook=HookStyle(font_path=font_path, text_color="#000000", bg_color="#FFE500",
                       bg_opacity=1, stroke_color="#000000", stroke_width=0, position="topo",
                       size="M", duration_s=2),
        watermark=WatermarkStyle(kind="imagem", position="inf_dir", scale_pct=20,
                                 opacity_pct=100, margin_pct=4, image_path=logo_path),
        end_card=EndCardStyle(cta="Segue", font_path=font_path, text_color="#FFFFFF",
                              bg_color="#0000FF", duration_s=1.5),
    )


def red_logo(tmp_path: Path) -> Path:
    path = tmp_path / "logo.png"
    Image.new("RGBA", (200, 100), (*RED, 255)).save(path)
    return path


def mean(frame: Path, box: tuple[int, int, int, int]) -> tuple[float, ...]:
    with Image.open(frame) as img:
        return tuple(ImageStat.Stat(img.convert("RGB").crop(box)).mean)


def close(color: tuple[float, ...], expected: tuple[int, int, int], tol: float = 20) -> bool:
    return all(abs(c - e) <= tol for c, e in zip(color, expected, strict=True))


def inner(ov: Overlay, size: tuple[int, int], *, margin: int) -> tuple[int, int, int, int]:
    return (ov.x + margin, ov.y + margin, ov.x + size[0] - margin, ov.y + size[1] - margin)


# ---------- filter_complex e linha de comando ----------

def test_build_filter_string():
    overlays = [Overlay(Path("g.png"), 10, 20, 0.0, 5), Overlay(Path("m.png"), 1, 2),
                Overlay(Path("c.png"), 0, 0, 8.5, None)]
    assert compose.build_filter(overlays) == (
        "[0:v][1:v]overlay=x=10:y=20:enable='between(t,0,5)'[v1];"
        "[v1][2:v]overlay=x=1:y=2[v2];"
        "[v2][3:v]overlay=x=0:y=0:enable='gte(t,8.5)'[v3];"
        "[v3]format=yuv420p[vout]"
    )
    assert compose.build_filter([]) == "[0:v]format=yuv420p[vout]"


def test_build_command_audio_e_sem_texto_do_usuario(tmp_path):
    ovs = [Overlay(tmp_path / "gancho.png", 0, 0, 0, 5)]
    aac = compose.build_command(tmp_path / "in.mp4", ovs, tmp_path / "out.mp4",
                                audio_codec="aac")
    assert aac[aac.index("-c:a") + 1] == "copy"
    opus = compose.build_command(tmp_path / "in.webm", ovs, tmp_path / "out.mp4",
                                 audio_codec="opus")
    assert opus[opus.index("-c:a") + 1] == "aac"
    mute = compose.build_command(tmp_path / "in.mp4", ovs, tmp_path / "out.mp4",
                                 audio_codec=None)
    assert "-c:a" not in mute
    assert "+faststart" in aac and "libx264" in aac
    # Só caminhos, números e o filtro montado aqui: nenhum texto livre.
    assert all(a.startswith(("-", "file:", "[")) or a.replace(".", "").isalnum()
               or a in ("pipe:1", "file,pipe", "+faststart", "0:a:0?", "[vout]")
               for a in aac)


# ---------- composição real (SC-004) ----------

def test_compose_camadas_por_amostragem(tmp_path, font_path):
    src = make_video(tmp_path / "in.mp4", size="1080x1920", seconds=6)
    work = tmp_path / "work"
    work.mkdir()
    overlays = render.render_layers(work, hook_text="Olha isso", kit=kit(font_path,
                                    red_logo(tmp_path)), width=1080, height=1920,
                                    duration_s=6)
    gancho, marca, _card = overlays
    sizes = {}
    for ov in overlays:
        with Image.open(ov.path) as img:
            sizes[ov.path.name] = img.size

    progress: list[int] = []
    out = tmp_path / "marcado.mp4"
    compose.compose(src, overlays, out, duration_s=6, audio_codec="aac",
                    on_progress=progress.append, workdir=work)

    assert progress and progress[-1] == 100
    assert progress == sorted(progress)

    _, gh = sizes["gancho.png"]
    hook_edge = (gancho.x + 6, gancho.y + gh // 2 - 4, gancho.x + 22, gancho.y + gh // 2 + 4)
    wm_box = inner(marca, sizes["marca.png"], margin=10)

    for t, name in ((0.5, "ini"), (3.0, "meio"), (5.5, "fim")):
        compose.extract_frame(out, t, tmp_path / f"{name}.png")

    ini, meio, fim = (tmp_path / f"{n}.png" for n in ("ini", "meio", "fim"))
    # t = 0,5 s: gancho amarelo e marca vermelha; fora das camadas continua cinza.
    assert close(mean(ini, hook_edge), YELLOW)
    assert close(mean(ini, wm_box), RED)
    assert close(mean(ini, (20, 900, 200, 1000)), GRAY)
    # Meio: o gancho sumiu, a marca continua.
    assert close(mean(meio, hook_edge), GRAY)
    assert close(mean(meio, wm_box), RED)
    # Últimos 1,5 s: o card cobre tudo, inclusive a marca d'água.
    assert close(mean(fim, (0, 0, 200, 200)), BLUE)
    assert close(mean(fim, wm_box), BLUE)
    assert close(mean(fim, hook_edge), BLUE)

    src_info, out_info = ffprobe(src), ffprobe(out)
    assert abs(duration(out_info) - duration(src_info)) < 0.1
    (v,) = streams(out_info, "video")
    assert (v["codec_name"], v["width"], v["height"]) == ("h264", 1080, 1920)
    assert v["pix_fmt"] == "yuv420p"
    assert [a["codec_name"] for a in streams(out_info, "audio")] == ["aac"]
    # +faststart: o moov vem antes do mdat.
    head = out.read_bytes()[:4096]
    assert b"moov" in head


def test_compose_horizontal_sem_audio(tmp_path, font_path):
    src = make_video(tmp_path / "in.mp4", size="1920x1080", seconds=3, audio=None)
    overlays = render.render_layers(tmp_path, hook_text="Oi", kit=kit(font_path,
                                    red_logo(tmp_path)), width=1920, height=1080,
                                    duration_s=3)
    out = tmp_path / "out.mp4"
    compose.compose(src, overlays, out, duration_s=3, audio_codec=None)
    info = ffprobe(out)
    (v,) = streams(info, "video")
    assert (v["width"], v["height"]) == (1920, 1080)
    assert streams(info, "audio") == []
    assert abs(duration(info) - duration(ffprobe(src))) < 0.1


def test_compose_webm_opus_vira_aac(tmp_path):
    src = make_video(tmp_path / "in.webm", size="360x640", seconds=2, audio="libopus",
                     vcodec="libvpx-vp9")
    out = tmp_path / "out.mp4"
    compose.compose(src, [], out, duration_s=2, audio_codec="opus")
    info = ffprobe(out)
    assert info["format"]["format_name"].startswith("mov,mp4")
    assert [a["codec_name"] for a in streams(info, "audio")] == ["aac"]
    assert abs(duration(info) - 2) < 0.1


def test_compose_arquivo_corrompido(tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"lixo" * 1000)
    with pytest.raises(ComposeError) as exc:
        compose.compose(src, [], tmp_path / "out.mp4", duration_s=1, audio_codec=None)
    assert exc.value.code == "corrupted"
    assert exc.value.message == compose.CORRUPTED


def test_compose_tempo_limite(tmp_path):
    src = make_video(tmp_path / "in.mp4", size="1080x1920", seconds=5, audio=None)
    with pytest.raises(ComposeError) as exc:
        compose.compose(src, [], tmp_path / "out.mp4", duration_s=5, audio_codec=None,
                        timeout_s=0.05)
    assert exc.value.code == "timeout"
    assert exc.value.message == compose.TIMEOUT
