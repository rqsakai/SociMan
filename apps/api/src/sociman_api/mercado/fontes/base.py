"""O contrato de um adaptador de fonte (`Protocol FonteMercado`) e os tipos comuns.

O adaptador **não** fala com a rede: recebe os `campos` já normalizados pelo coletor
(`contracts/coletor.md`, "Payloads normalizados"), valida com Pydantic e devolve objetos
tipados que a ingestão grava. Qualquer erro de validação vira item `invalido` com o campo.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from sociman_api.perfis.models import Platform


class CampoInvalido(Exception):
    """Um campo do payload não serve: `campo` é o caminho (`ficha.titulo`, `itens[0].posicao`)."""

    def __init__(self, campo: str, motivo: str = "campos_invalidos"):
        super().__init__(f"{motivo}: {campo}")
        self.campo = campo
        self.motivo = motivo


@dataclass(frozen=True)
class ProdutoRef:
    """A identidade de um produto na rede, extraída de um link (interesse manual, FR-039)."""

    rede: Platform
    mercado: str
    rede_produto_id: str
    url_canonica: str


class FonteMercado(Protocol):
    rede: Platform
    esquema_versao: str
    tipos: tuple[str, ...]

    def validar_chave(self, tipo: str, chave: str) -> bool: ...

    def normalizar(self, tipo: str, campos: dict[str, Any]) -> BaseModel: ...

    def produto_de_url(self, url: str, mercado: str) -> ProdutoRef | None: ...

    def url_canonica(self, url: str) -> str: ...

    def url_tarefa(self, tipo: str, bases: "BasesUrl", *, produto_url: str | None = None,
                   rede_produto_id: str | None = None, rede_categoria_id: str | None = None,
                   ranking_tipo: str | None = None, janela: str | None = None,
                   loja_url: str | None = None, rede_loja_id: str | None = None,
                   pagina: int | None = None) -> str | None:
        """A única URL que o coletor pode abrir para uma tarefa da fila (FR-023); None quando a
        base configurada pelo dono falta (a tarefa não nasce)."""
        ...


@dataclass(frozen=True)
class BasesUrl:
    """Os endereços da rede vêm do `.env` do dono (princípio IX: nenhum literal no servidor)."""

    publica: str = ""
    affiliate: str = ""

    @classmethod
    def das_settings(cls) -> "BasesUrl":
        from sociman_api.config import get_settings

        s = get_settings()
        return cls(publica=s.mercado_url_publica.rstrip("/"),
                   affiliate=s.mercado_url_affiliate.rstrip("/"))


def campo_do_erro(exc: ValidationError) -> str:
    """O primeiro `loc` do Pydantic como caminho legível (`itens[0].posicao`)."""
    erros = exc.errors()
    if not erros:
        return "campos"
    partes: list[str] = []
    for p in erros[0].get("loc", ()):
        if isinstance(p, int):
            partes[-1] = f"{partes[-1]}[{p}]" if partes else f"[{p}]"
        else:
            partes.append(str(p))
    return ".".join(partes) or "campos"
