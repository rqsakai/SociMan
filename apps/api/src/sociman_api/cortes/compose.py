"""Composição do corte marcado com um único `ffmpeg -filter_complex` (research R2).

Cada camada é um PNG (render.py) sobreposto com `overlay` e `enable='between(t,…)'`. O vídeo
base não é redimensionado (resolução e fps do original), a saída é sempre MP4 H.264/AAC com
`+faststart`, o áudio é copiado quando já é AAC e recodificado nos outros casos, e vídeo sem
áudio passa. O progresso vem de `-progress pipe:1`; o processo é morto depois do tempo limite.
Na linha de comando só entram caminhos e números: o texto do usuário está dentro dos PNGs.
"""

import os
import subprocess
import tempfile
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from sociman_api.cortes.render import Overlay

COMPOSE_TIMEOUT_S = 600
FRAME_TIMEOUT_S = 60

CORRUPTED = "O vídeo está corrompido ou não pôde ser lido"
TIMEOUT = "Tempo de processamento esgotado"


class ComposeError(Exception):
    """Falha do ffmpeg. `code` é o `error_code` do corte; `detail` (stderr) é só para o log."""

    def __init__(self, code: str, message: str, detail: str = ""):
        super().__init__(message)
        self.code = code  # 'corrupted' | 'timeout'
        self.message = message
        self.detail = detail


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _enable(ov: Overlay) -> str:
    if ov.start_s is None and ov.end_s is None:
        return ""
    if ov.end_s is None:
        return f":enable='gte(t,{_num(ov.start_s or 0)})'"
    return f":enable='between(t,{_num(ov.start_s or 0)},{_num(ov.end_s)})'"


def build_filter(overlays: Sequence[Overlay]) -> str:
    """O `filter_complex`: overlays encadeados na ordem da lista (o último fica por cima)."""
    if not overlays:
        return "[0:v]format=yuv420p[vout]"
    parts, prev = [], "0:v"
    for i, ov in enumerate(overlays, start=1):
        parts.append(f"[{prev}][{i}:v]overlay=x={ov.x}:y={ov.y}{_enable(ov)}[v{i}]")
        prev = f"v{i}"
    parts.append(f"[{prev}]format=yuv420p[vout]")
    return ";".join(parts)


def build_command(src: str | Path, overlays: Sequence[Overlay], dst: str | Path, *,
                  audio_codec: str | None) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats", "-protocol_whitelist", "file,pipe",
           "-i", f"file:{Path(src).resolve()}"]
    for ov in overlays:
        cmd += ["-i", f"file:{Path(ov.path).resolve()}"]
    cmd += ["-filter_complex", build_filter(overlays), "-map", "[vout]", "-map", "0:a:0?",
            "-fps_mode", "passthrough",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    if audio_codec is not None:
        cmd += ["-c:a", "copy"] if audio_codec == "aac" else ["-c:a", "aac", "-b:a", "192k"]
    # Sem metadados do original (GPS e aparelho de celular) nem capítulos.
    cmd += ["-map_metadata", "-1", "-map_chapters", "-1", "-movflags", "+faststart",
            "-f", "mp4", f"file:{Path(dst).resolve()}"]
    return cmd


def _tail(fh, limit: int = 4000) -> str:
    fh.seek(0)
    return fh.read().decode("utf-8", "replace")[-limit:]


def compose(src: str | Path, overlays: Sequence[Overlay], dst: str | Path, *,
            duration_s: float, audio_codec: str | None,
            on_progress: Callable[[int], None] | None = None,
            timeout_s: float = COMPOSE_TIMEOUT_S, workdir: str | Path | None = None) -> None:
    """Gera `dst` com as camadas queimadas; `on_progress(0..100)` a cada mudança de percentual.

    `workdir` vira o `cwd` e o `TMPDIR` do ffmpeg (a pasta do corte no HD, R5).
    Levanta `ComposeError('timeout' | 'corrupted', …)`.
    """
    cmd = build_command(src, overlays, dst, audio_codec=audio_codec)
    env = None
    if workdir is not None:
        env = {**os.environ, "TMPDIR": str(workdir)}
    total_us = max(1.0, duration_s * 1_000_000)
    timed_out = threading.Event()
    last = -1

    with tempfile.TemporaryFile(dir=workdir) as err:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=err, cwd=workdir, env=env)

        def _kill() -> None:
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout_s, _kill)
        timer.start()
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                key, _, value = raw.decode("ascii", "replace").strip().partition("=")
                if key == "out_time_us" and value.lstrip("-").isdigit():
                    pct = int(max(0, min(99, int(value) * 100 / total_us)))
                elif key == "progress" and value == "end":
                    pct = 100
                else:
                    continue
                if pct != last and on_progress is not None:
                    on_progress(pct)
                last = pct
            code = proc.wait()
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
                proc.wait()

        if timed_out.is_set():
            raise ComposeError("timeout", TIMEOUT, _tail(err))
        if code != 0:
            raise ComposeError("corrupted", CORRUPTED, _tail(err))
        if last != 100 and on_progress is not None:
            on_progress(100)


def extract_frame(src: str | Path, t: float, dst: str | Path, *,
                  timeout_s: float = FRAME_TIMEOUT_S) -> None:
    """Um quadro em `t` segundos (o pôster do corte, e a amostragem dos testes)."""
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
           "-protocol_whitelist", "file", "-ss", _num(max(0.0, t)),
           "-i", f"file:{Path(src).resolve()}", "-frames:v", "1", "-map_metadata", "-1",
           f"file:{Path(dst).resolve()}"]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        raise ComposeError("timeout", TIMEOUT) from None
    if res.returncode != 0 or not Path(dst).exists():
        raise ComposeError("corrupted", CORRUPTED, res.stderr.decode("utf-8", "replace")[-4000:])
