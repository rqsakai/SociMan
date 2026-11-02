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

Vídeo guiado (spec 031, R2 e R4), sem mudar o caminho da 011:
- cada trecho (`cmd_trecho`) é reajustado por `setpts` para exatamente o trecho-base, sem cortar
  o fim (o último quadro continua sendo o keyframe de fim); a partir do 2º trecho da posição, o
  1º quadro sai (é o keyframe que fechou o trecho anterior);
- os trechos de uma posição e as posições são juntados por `concat` seco; o cross-fade
  (`crossfade_quadros`) fica previsto e desligado;
- a fala vai para o slot de cada posição (`cmd_fala_no_slot`, com os blocos de
  `tempos.fala_por_slot`) e a mistura continua no `cmd_mixar`/`cmd_acabamento` (−14 LUFS).
"""

import logging
import shutil
import subprocess
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sociman_api.config import get_settings
from sociman_api.geracao.erros import MotorErro
from sociman_api.roteiros.tempos import ATRASO_FALA, BlocoFala

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


# ---- vídeo guiado (spec 031) ----

def quadros_saida(base_s: float) -> int:
    """Os quadros de um trecho-base a 24 fps (5 s → 120)."""
    return round(base_s * FPS)


def cmd_trecho(src: str | Path, dst: str | Path, *, base_s: float, quadros: int,
               primeiro: bool, largura: int, altura: int, extra_quadros: int = 0) -> list[str]:
    """Um trecho com exatamente `base_s` (+ `extra_quadros`, só com cross-fade) a 24 fps.

    `quadros` são os da tomada (na regra do motor: MiniMax 124, Wan 81, LTX 121). Fora do 1º
    trecho, o 1º quadro sai (`select`). Os que ficam são espalhados por `setpts` de modo que o
    último caia no último quadro da saída: o fim não é cortado, só a velocidade muda um pouco
    (124 → 120 quadros, ~3%)."""
    usados = quadros - (0 if primeiro else 1)
    saida = quadros_saida(base_s) + extra_quadros
    if usados < 2 or saida < 2:
        raise ValueError("trecho com menos de 2 quadros")
    passo = (saida - 1) / FPS / (usados - 1)
    corte = "" if primeiro else r"select=gte(n\,1),"
    vf = (f"{corte}setpts=N*{passo:.9f}/TB,"
          f"scale={largura}:{altura}:force_original_aspect_ratio=decrease,"
          f"pad={largura}:{altura}:(ow-iw)/2:(oh-ih)/2,fps={FPS},format=yuv420p,setsar=1")
    return [*_BASE, "-i", str(src), "-vf", vf, "-an", "-frames:v", str(saida), "-c:v",
            "libx264", "-crf", "12", "-preset", "fast", str(dst)]


def cmd_crossfade(partes: Sequence[str | Path], dst: str | Path, *, base_s: float,
                  crossfade_quadros: int) -> list[str]:
    """Os trechos de uma posição com cross-fade de `crossfade_quadros` (cada trecho, menos o
    último, foi feito com esses quadros a mais: o total continua trechos × base)."""
    if len(partes) < 2 or crossfade_quadros <= 0:
        raise ValueError("cross-fade precisa de 2 trechos e de quadros")
    dur = crossfade_quadros / FPS
    entradas = [a for p in partes for a in ("-i", str(p))]
    filtros, atual = [], "[0:v]"
    for i in range(1, len(partes)):
        # O i-ésimo começa a entrar `dur` antes do fim do que já foi juntado.
        offset = i * base_s
        saida = f"[x{i}]" if i + 1 < len(partes) else "[v]"
        filtros.append(f"{atual}[{i}:v]xfade=transition=fade:duration={dur:.6f}:"
                       f"offset={offset:.6f}{saida}")
        atual = saida
    return [*_BASE, *entradas, "-filter_complex", ";".join(filtros), "-map", "[v]", "-an",
            "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p",
            str(dst)]


def cmd_fala_no_slot(src: str | Path, dst: str | Path, blocos: Sequence[BlocoFala],
                     duracoes_s: Sequence[float]) -> list[str]:
    """A narração do guiado, um slot por posição, juntados por `concat`: no slot com fala, o
    bloco cortado da narração contínua, com o seu `atempo`, depois de `ATRASO_FALA` de silêncio
    (`adelay`) e completado com silêncio até o fim do slot (`apad`); no slot sem fala, silêncio.
    O total é exatamente a soma das durações. Sem `loudnorm` aqui: a mistura
    (`cmd_mixar`/`cmd_acabamento`) continua a −14 LUFS.

    Não usa `amix` com `adelay` absoluto: no ffmpeg 7.1, com `atempo` em mais de um ramo, o
    `amix` termina na hora (o arquivo saía com 0,15 s), e o `apad` sem `whole_dur` não para."""
    por_slot = {b.indice: b for b in blocos}
    if len(por_slot) != len(blocos) or any(not 0 <= i < len(duracoes_s) for i in por_slot):
        raise ValueError("um bloco por posição, dentro das posições")
    total_s = sum(duracoes_s)
    n = len(blocos)
    filtros = []
    if n:
        copias = (f",asplit={n}" if n > 1 else "") + "".join(f"[s{i}]" for i in range(n))
        filtros.append(f"[0:a]aresample=48000,aformat=channel_layouts=stereo{copias}")
    slots, k = [], 0
    for i, dur in enumerate(duracoes_s):
        b = por_slot.get(i)
        if b is None:
            filtros.append(f"anullsrc=r=48000:cl=stereo:d={_n(dur)}[z{i}]")
            slots.append(f"[z{i}]")
            continue
        tempo = f",atempo={b.atempo:g}" if b.atempo != 1 else ""
        filtros.append(f"[s{k}]atrim=start={_n(b.inicio_s)}:end={_n(b.fim_s)},"
                       f"asetpts=PTS-STARTPTS{tempo},atrim=duration={_n(b.max_s)},"
                       f"apad=whole_dur={_n(b.max_s)},"
                       f"adelay={round(ATRASO_FALA * 1000)}:all=1[b{i}]")
        slots.append(f"[b{i}]")
        k += 1
    filtros.append(f"{''.join(slots)}concat=n={len(slots)}:v=0:a=1[a]")
    entrada = ["-i", str(src)] if n else []
    return [*_BASE, *entrada, "-filter_complex", ";".join(filtros), "-map", "[a]",
            "-t", _n(total_s), "-c:a", "pcm_s16le", str(dst)]


@dataclass(frozen=True)
class PosicaoGuiada:
    """Uma posição do guiado para a montagem: os arquivos dos trechos, na ordem, e a duração
    fixa (trechos × base)."""
    trechos: Sequence[Path]
    duracao_s: float


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


def contar_quadros(src: Path) -> int:
    """Os quadros de vídeo do arquivo (pelos pacotes do ffprobe, sem decodificar)."""
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                              "-count_packets", "-show_entries", "stream=nb_read_packets",
                              "-of", "csv=p=0", str(src)], capture_output=True,
                             timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise MotorErro("internal", "O ffprobe passou do tempo limite",
                        detalhe=str(src)) from None
    texto = res.stdout.decode().strip().split(",")[0]
    if res.returncode != 0 or not texto.isdigit():
        raise MotorErro("internal", "O ffprobe não conseguiu ler o trecho",
                        detalhe=f"{src}: {res.stderr.decode('utf-8', 'replace')[-500:]}")
    return int(texto)


def montar_posicoes_guiadas(trabalho: Path, posicoes: Sequence[PosicaoGuiada], *,
                            base_s: float, largura: int, altura: int,
                            crossfade_quadros: int = 0) -> list[Path]:
    """Um mp4 por posição (`pos_NN.mp4`), cada um com exatamente `duracao_s`: os trechos
    reajustados (`cmd_trecho`) e juntados. Serve à prévia e ao `upscale_video` do acabamento."""
    saida = []
    for i, pos in enumerate(posicoes):
        n = len(pos.trechos)
        if n < 1 or round(n * base_s, 3) != round(pos.duracao_s, 3):
            raise ValueError(f"a posição {i} tem {n} trechos e {pos.duracao_s:g} s: não fecha "
                             f"com a base de {base_s:g} s")
        partes = []
        for t, src in enumerate(pos.trechos):
            extra = crossfade_quadros if crossfade_quadros and t + 1 < n else 0
            dst = trabalho / f"pos_{i:02d}_t{t}.mp4"
            executar(cmd_trecho(src, dst, base_s=base_s, quadros=contar_quadros(src),
                                primeiro=t == 0, largura=largura, altura=altura,
                                extra_quadros=extra))
            partes.append(dst)
        if n == 1:
            saida.append(partes[0])
        elif crossfade_quadros:
            dst = trabalho / f"pos_{i:02d}.mp4"
            executar(cmd_crossfade(partes, dst, base_s=base_s,
                                   crossfade_quadros=crossfade_quadros))
            saida.append(dst)
        else:
            saida.append(concatenar(trabalho, partes, f"pos_{i:02d}.mp4"))
    return saida


def colocar_fala(trabalho: Path, narracao: Path, blocos: Sequence[BlocoFala],
                 duracoes_s: Sequence[float]) -> Path:
    """A narração contínua (na velocidade do roteiro) posta nos slots: `fala_slot.wav`, com
    exatamente a soma de `duracoes_s` (a duração-alvo)."""
    dst = trabalho / "fala_slot.wav"
    executar(cmd_fala_no_slot(narracao, dst, blocos, duracoes_s))
    return dst


def montar_previa_guiada(trabalho: Path, posicoes: Sequence[PosicaoGuiada],
                         narracao_slot: Path, *, base_s: float, largura: int, altura: int,
                         crossfade_quadros: int = 0) -> Path:
    """`roteiro.montagem` do guiado: os trechos por posição, as posições juntadas e a fala já
    nos slots (`colocar_fala`), a −14 LUFS. A duração é a soma das posições (o alvo)."""
    partes = montar_posicoes_guiadas(trabalho, posicoes, base_s=base_s, largura=largura,
                                     altura=altura, crossfade_quadros=crossfade_quadros)
    mudo = concatenar(trabalho, partes)
    dst = trabalho / "previa.mp4"
    executar(cmd_mixar(mudo, narracao_slot, dst))
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
