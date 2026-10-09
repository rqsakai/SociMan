"""Download de imagens dentro do próprio navegador (FR-020; contracts/coletor.md, "Imagens").

Este é o **único** módulo do coletor onde `request` aparece: `pagina.request.get(url)` baixa, com
os cookies do perfil, só URLs de imagem que a **própria página carregou** (vistas pela
interceptação `response` com `Content-Type: image/*` e host em `IMAGENS_HOSTS`). Sem
redimensionar; sha256 local; arquivos > 5 MB descartados (`imagem_grande`); cache por sha na
rodada; nada em disco.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sociman_coletor import log
from sociman_coletor.privacidade import url_sem_query
from sociman_coletor.redes.base import ImagemRef

IMAGEM_BYTES_MAX = 5 * 1024 * 1024
LOTE_BYTES_MAX = 50 * 1024 * 1024
TIMEOUT_DOWNLOAD_MS = 30_000


@dataclass
class Imagem:
    sha256: str
    conteudo: bytes
    content_type: str
    url: str
    origem: str = "produto"
    tarefa_id: str | None = None


@dataclass
class ResultadoDownload:
    novas: list[Imagem] = field(default_factory=list)  # a enviar (sha ainda não visto)
    mapa: dict[str, str] = field(default_factory=dict)  # url → sha (novas e já em cache)
    descartadas: dict[str, int] = field(default_factory=dict)  # motivo → contagem


class Baixador:
    """Vive uma rodada: guarda as URLs de imagem que a página carregou e o cache de shas."""

    def __init__(self, rede: Any, pagina: Any = None):
        self._rede = rede
        self._pagina = pagina
        self._vistas: dict[str, str] = {}  # url sem query → content-type
        self.cache: set[str] = set()  # shas já enviados (aceitos ou repetidos) na rodada
        self._log = log.obter("imagens")

    def ligar(self, pagina: Any) -> None:
        self._pagina = pagina

    def registrar_resposta(self, resposta: Any) -> None:
        """Chamado pelo `page.on("response")`: anota as imagens que a página carregou."""
        try:
            url = resposta.url
            ct = (resposta.headers or {}).get("content-type", "")
        except Exception:  # noqa: BLE001 - resposta já fechada
            return
        if ct.lower().startswith("image/") and self._rede.host_de_imagem(url):
            self._vistas[url_sem_query(url)] = ct.split(";")[0].strip()

    def nova_pagina(self) -> None:
        self._vistas.clear()

    def foi_carregada(self, url: str) -> bool:
        return url_sem_query(url) in self._vistas

    def lembrar(self, shas: Iterable[str]) -> None:
        self.cache.update(shas)

    def baixar(
        self, refs: Iterable[ImagemRef], maximo: int, tarefa_id: str | None = None
    ) -> ResultadoDownload:
        """Baixa até `maximo` imagens **novas** (as já em cache não contam nem são baixadas de
        novo quando a URL já foi vista nesta rodada com o mesmo sha)."""
        saida = ResultadoDownload()
        if self._pagina is None or maximo <= 0:
            if maximo <= 0:
                saida.descartadas["orcamento"] = sum(1 for _ in refs)
            return saida
        total_bytes = 0
        for ref in refs:
            if len(saida.novas) >= maximo:
                saida.descartadas["orcamento"] = saida.descartadas.get("orcamento", 0) + 1
                continue
            if ref.url in saida.mapa:
                continue
            if not self._rede.host_de_imagem(ref.url) or not self.foi_carregada(ref.url):
                saida.descartadas["nao_carregada"] = saida.descartadas.get("nao_carregada", 0) + 1
                continue
            try:
                resposta = self._pagina.request.get(ref.url, timeout=TIMEOUT_DOWNLOAD_MS)
                if not resposta.ok:
                    saida.descartadas["http"] = saida.descartadas.get("http", 0) + 1
                    continue
                corpo = resposta.body()
                ct = (resposta.headers or {}).get("content-type", "").split(";")[0].strip()
            except Exception:  # noqa: BLE001 - uma imagem a menos; o item vai mesmo assim
                saida.descartadas["falha"] = saida.descartadas.get("falha", 0) + 1
                continue
            if len(corpo) > IMAGEM_BYTES_MAX:
                saida.descartadas["imagem_grande"] = saida.descartadas.get("imagem_grande", 0) + 1
                continue
            if total_bytes + len(corpo) > LOTE_BYTES_MAX:
                saida.descartadas["lote_cheio"] = saida.descartadas.get("lote_cheio", 0) + 1
                continue
            if not ct.startswith("image/"):
                ct = self._vistas.get(url_sem_query(ref.url), "application/octet-stream")
            sha = hashlib.sha256(corpo).hexdigest()
            saida.mapa[ref.url] = sha
            if sha in self.cache or any(n.sha256 == sha for n in saida.novas):
                continue
            total_bytes += len(corpo)
            saida.novas.append(Imagem(sha, corpo, ct, ref.url, ref.origem, tarefa_id))
        if saida.descartadas:
            self._log.info("imagens descartadas: %s", dict(saida.descartadas))
        return saida
