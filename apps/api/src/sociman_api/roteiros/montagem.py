"""Comandos ffmpeg da montagem, da narração e do acabamento (research R2, R5 e R11).

Duas camadas:
- **construtores puros** (`cmd_*`): devolvem a linha de comando, sem rodar nada. Na linha só entram
  caminhos e números (nenhum texto do usuário);
- **executores** (`executar`, `pasta_temporaria` e as funções sem `cmd_`): rodam o ffmpeg em
  `${SOCIMAN_DATA_DIR}/work/tmp/roteiros/<geracao>/` (HD) e apagam a pasta no `finally`.

A receita é a do pipeline aprovado (`run_storyboard.concat`, `stage_mix` e `finalizar_hd.py`):
- corte por posição: `scale/pad` para a resolução da cena, `fps=24`, `trim` na duração da posição
  e `-an` (o áudio do modelo é descartado; só a narração entra);
- concat sem recodificar;
- narração: `atempo` (antes das durações, R5) e mistura com `loudnorm=I=-14:TP=-1.5:LRA=11`;
- acabamento: `hqdn3d=0:0:3:3` em cada posição depois do SeedVR2, `lanczos` para 1920 de altura,
  `crop=1080:1920`, `unsharp=3:3:0.3`, `fps=24`, crf 16 e `+faststart`.

Nunca `tpad`/clone: uma tomada mais curta que a posição é recusada antes (`tomada_curta`), e a
posição volta para os clipes.
"""

import logging
import shutil
import subprocess
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from sociman_api.config import get_settings
from sociman_api.geracao.erros import MotorErro

log = logging.getLogger("sociman.gerador")

FPS = 24
OUT_W, OUT_H = 1080, 1920
LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"
DENOISE = "hqdn3d=0:0:3:3"
TIMEOUT_S = 600
_BASE = ("ffmpeg", "-nostdin", "-v", "error", "-y")


def _n(valor: float) -> str:
    return f"{valor:.3f}"


def tomada_curta(duracao_tomada_ms: int, duracao_s: float) -> bool:
    """A tomada não cobre a posição (a montagem não congela quadro nem estica o clipe)."""
    return duracao_tomada_ms < round(duracao_s * 1000)


def cmd_cortar(src: str | Path, dst: str | Path, *, duracao_s: float, largura: int, altura: int,
               inicio_s: float = 0.0) -> list[str]:
    """Uma posição: a tomada do início, na resolução da cena, a 24 fps, sem áudio."""
    vf = (f"scale={largura}:{altura}:force_original_aspect_ratio=decrease,"
          f"pad={largura}:{altura}:(ow-iw)/2:(oh-ih)/2,fps={FPS},"
          f"trim=duration={_n(duracao_s)},setpts=PTS-STARTPTS,format=yuv420p,setsar=1")
    entrada = ["-ss", _n(inicio_s)] if inicio_s > 0 else []
    return [*_BASE, *entrada, "-i", str(src), "-vf", vf, "-an", "-c:v", "libx264", "-crf", "12",
            "-preset", "fast", str(dst)]


def lista_concat(partes: Sequence[str | Path]) -> str:
    """O arquivo do demuxer `concat` (caminhos absolutos, aspas simples escapadas)."""
    linhas = []
    for p in partes:
        caminho = str(Path(p).resolve()).replace("'", "'\\''")
        linhas.append(f"file '{caminho}'\n")
    return "".join(linhas)


def cmd_concat(lista: str | Path, dst: str | Path) -> list[str]:
    """Junta as posições já cortadas pelo mesmo comando (mesmo codec): sem recodificar."""
    return [*_BASE, "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(dst)]


def cmd_atempo(src: str | Path, dst: str | Path, velocidade: float) -> list[str]:
    """A narração na velocidade final (tom preservado), em WAV."""
    if not 0.5 <= velocidade <= 2.0:
        raise ValueError("velocidade fora do atempo (0,5 a 2,0)")
    return [*_BASE, "-i", str(src), "-af", f"atempo={velocidade:g}", "-c:a", "pcm_s16le",
            str(dst)]


def _audio(entrada: int) -> str:
    return f"[{entrada}:a]aresample=48000,aformat=channel_layouts=stereo,apad,{LOUDNORM}[a]"


def cmd_mixar(video: str | Path, narracao: str | Path, dst: str | Path) -> list[str]:
    """A prévia: o vídeo mudo como está e a narração a −14 LUFS (o fim é o do vídeo)."""
    return [*_BASE, "-i", str(video), "-i", str(narracao), "-filter_complex", _audio(1),
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(dst)]


def cmd_denoise(src: str | Path, dst: str | Path) -> list[str]:
    """Depois do SeedVR2, por posição: tira a cintilação a cada 4 quadros."""
    return [*_BASE, "-i", str(src), "-vf", DENOISE, "-an", "-c:v", "libx264", "-crf", "14",
            "-preset", "fast", str(dst)]


def cmd_acabamento(video: str | Path, narracao: str | Path, dst: str | Path, *, largura: int,
                   altura: int) -> list[str]:
    """O HD final: 1080×1920 a 24 fps (sem interpolação) e a narração a −14 LUFS."""
    escala_w = round(OUT_H * largura / altura) // 2 * 2
    if escala_w < OUT_W:
        raise ValueError(f"resolução {largura}×{altura} mais estreita que 9:16")
    vf = (f"[0:v]scale={escala_w}:{OUT_H}:flags=lanczos,crop={OUT_W}:{OUT_H},unsharp=3:3:0.3,"
          f"fps={FPS}[v]")
    return [*_BASE, "-i", str(video), "-i", str(narracao), "-filter_complex",
            f"{vf};{_audio(1)}", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "16",
            "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(dst)]


# ---- executores ----

def pasta(geracao_id: uuid.UUID) -> Path:
    return Path(get_settings().data_dir) / "work" / "tmp" / "roteiros" / str(geracao_id)


@contextmanager
def pasta_temporaria(geracao_id: uuid.UUID) -> Iterator[Path]:
    """A pasta de trabalho da geração no HD, apagada no fim, com sucesso ou erro."""
    p = pasta(geracao_id)
    shutil.rmtree(p, ignore_errors=True)  # sobra de uma volta interrompida
    p.mkdir(parents=True)
    try:
        yield p
    finally:
        shutil.rmtree(p, ignore_errors=True)


def executar(cmd: Sequence[str], *, timeout_s: float = TIMEOUT_S) -> None:
    """Roda um comando dos construtores. Falha ou tempo esgotado → `MotorErro("internal")`, com
    o stderr só no log."""
    try:
        res = subprocess.run(list(cmd), capture_output=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        raise MotorErro("internal", "O ffmpeg passou do tempo limite",
                        detalhe=f"{cmd[-1]}: {timeout_s:.0f} s") from None
    if res.returncode != 0:
        erro = res.stderr.decode("utf-8", "replace")[-2000:]
        log.warning("ffmpeg saiu com %s: %s", res.returncode, erro)
        raise MotorErro("internal", "O ffmpeg não conseguiu montar o vídeo",
                        detalhe=f"{cmd[-1]}: {res.returncode} {erro}")


def aplicar_atempo(src: Path, dst: Path, velocidade: float) -> Path:
    executar(cmd_atempo(src, dst, velocidade))
    return dst


def cortar_posicoes(trabalho: Path, tomadas: Sequence[tuple[Path, float]], *, largura: int,
                    altura: int) -> list[Path]:
    """`tomadas` = (arquivo, duração da posição em s), na ordem das posições."""
    partes = []
    for i, (src, duracao_s) in enumerate(tomadas):
        dst = trabalho / f"pos_{i:02d}.mp4"
        executar(cmd_cortar(src, dst, duracao_s=duracao_s, largura=largura, altura=altura))
        partes.append(dst)
    return partes


def concatenar(trabalho: Path, partes: Sequence[Path], nome: str = "mudo.mp4") -> Path:
    lista = trabalho / f"{Path(nome).stem}.txt"
    lista.write_text(lista_concat(partes))
    dst = trabalho / nome
    executar(cmd_concat(lista, dst))
    return dst


def montar_previa(trabalho: Path, tomadas: Sequence[tuple[Path, float]], narracao: Path, *,
                  largura: int, altura: int) -> Path:
    """`roteiro.montagem`: corta, junta e mistura a narração (já na velocidade final)."""
    mudo = concatenar(trabalho, cortar_posicoes(trabalho, tomadas, largura=largura,
                                                altura=altura))
    dst = trabalho / "previa.mp4"
    executar(cmd_mixar(mudo, narracao, dst))
    return dst


def tirar_cintilacao(trabalho: Path, ampliadas: Sequence[Path]) -> list[Path]:
    """`roteiro.acabamento`, depois do `upscale_video` de cada posição."""
    saida = []
    for i, src in enumerate(ampliadas):
        dst = trabalho / f"hd_{i:02d}.mp4"
        executar(cmd_denoise(src, dst))
        saida.append(dst)
    return saida


def acabar(trabalho: Path, posicoes_hd: Sequence[Path], narracao: Path, *, largura: int,
           altura: int) -> Path:
    """Junta as posições ampliadas e entrega o 1080×1920 com a narração."""
    junto = concatenar(trabalho, posicoes_hd, "junto_hd.mp4")
    dst = trabalho / "final.mp4"
    executar(cmd_acabamento(junto, narracao, dst, largura=largura, altura=altura),
             timeout_s=TIMEOUT_S * 2)
    return dst
