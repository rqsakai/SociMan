"""Apoio do gerador aos passos de vídeo e à narração da spec 011 (research R2, R3, R5 e R11).

- `pasta_tmp(geracao_id)`: a pasta de trabalho em `${SOCIMAN_DATA_DIR}/work/tmp/roteiros/<id>/`
  (HD, com o sentinela conferido), apagada no fim, com sucesso ou não;
- `Contexto`: o que o gerador oferece ao `Aplicador.executar_video` (baixar do MinIO para a pasta,
  rodar um bloco do ComfyUI, dar andamento, conferir o cancelamento e soltar a GPU). O aplicador
  monta o trabalho (cortar, ampliar, juntar, misturar) e devolve o caminho do mp4 final; quem
  grava o candidato é o gerador (`_gravar_video`);
- `atempo(wav, velocidade)`: a velocidade da narração aplicada depois do shop-tts e antes das
  durações (R5), e `tempos_na_velocidade` divide os tempos do lote pela mesma velocidade.

Sem import de `roteiros/` (a seta é `roteiros → geracao`).
"""

import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sociman_api import datadir, storage
from sociman_api.config import get_settings
from sociman_api.geracao.erros import MotorErro

ATEMPO_TIMEOUT_S = 120
VIDEO_MAX_BYTES = 2 * 1024**3
VIDEO_MAX_S = 600


def raiz_tmp() -> Path:
    return Path(get_settings().data_dir) / "work" / "tmp" / "roteiros"


@contextmanager
def pasta_tmp(geracao_id: uuid.UUID) -> Iterator[Path]:
    """`work/tmp/roteiros/<geracao>/`, criada vazia e apagada no `finally` (R2)."""
    datadir.ensure_writable()
    pasta = raiz_tmp() / str(geracao_id)
    shutil.rmtree(pasta, ignore_errors=True)  # sobra de uma interrupção
    pasta.mkdir(parents=True)
    try:
        yield pasta
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


@dataclass
class Contexto:
    """O que o aplicador de um passo de vídeo pode pedir ao gerador, sem rede própria."""

    pasta: Path
    geracao_id: uuid.UUID
    _bloco: Callable[[str, dict[str, Any], str], bytes] | None
    _andamento: Callable[[int, str], None]
    _checar: Callable[[], None]
    _liberar: Callable[[], None]

    def baixar(self, key: str, bucket: storage.Bucket, nome: str) -> Path:
        """Baixa o objeto do MinIO para `pasta/nome` (só o nome do arquivo, sem subpasta)."""
        destino = self.pasta / Path(nome).name
        storage.get_to_file(key, destino, bucket=bucket)
        return destino

    def rodar_bloco(self, bloco: str, entrada: dict[str, Any], nome: str) -> bytes:
        """Roda um bloco do ComfyUI e devolve o vídeo (só nos passos do motor `comfyui`)."""
        if self._bloco is None:
            raise MotorErro("internal", detalhe="este passo não roda no ComfyUI")
        return self._bloco(bloco, entrada, nome)

    def andamento(self, progresso: int, mensagem: str) -> None:
        self._andamento(progresso, mensagem)

    def checar(self) -> None:
        """Levanta se o gerador parou ou a geração foi cancelada."""
        self._checar()

    def liberar_gpu(self) -> None:
        """`/free` com `unload_models` (o `comfy_free` do fim do acabamento, R11)."""
        self._liberar()


def tempos_na_velocidade(sentencas: list[dict[str, Any]], segundos: float,
                         velocidade: float) -> tuple[list[dict[str, Any]], float]:
    """Os tempos do `/v2/tts_paragraph` divididos pela velocidade (como o `continuous_bounds`).
    `frase` é a posição na lista (0-based, como `roteiro_cenas.frases`); o `index` do serviço
    começa em 1."""
    v = float(velocidade)
    tempos = [{"frase": i, "inicio_s": round(float(s["start"]) / v, 3),
               "fim_s": round(float(s["end"]) / v, 3)}
              for i, s in enumerate(sentencas)]
    return tempos, round(float(segundos) / v, 3)


def atempo(wav: bytes, velocidade: float, *, timeout_s: float = ATEMPO_TIMEOUT_S) -> bytes:
    """`ffmpeg -af atempo=<velocidade>` no wav, em `work/tmp` (HD). 1,0 devolve como veio."""
    v = float(velocidade)
    if abs(v - 1.0) < 1e-6:
        return wav
    if not 0.5 <= v <= 2.0:
        raise MotorErro("entrada_invalida", detalhe=f"velocidade fora do atempo: {v}")
    datadir.ensure_writable(len(wav) * 2)
    base = Path(get_settings().data_dir) / "work" / "tmp"
    with tempfile.TemporaryDirectory(dir=base, prefix="atempo-") as tmp:
        entrada, saida = Path(tmp) / "in.wav", Path(tmp) / "out.wav"
        entrada.write_bytes(wav)
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
               "-protocol_whitelist", "file", "-i", f"file:{entrada}",
               "-af", f"atempo={v:.4f}", "-c:a", "pcm_s16le", f"file:{saida}"]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired:
            raise MotorErro("internal", detalhe="atempo: timeout") from None
        if res.returncode != 0 or not saida.exists():
            raise MotorErro("internal", detalhe="atempo: " +
                            res.stderr.decode("utf-8", "replace")[-500:])
        return saida.read_bytes()
