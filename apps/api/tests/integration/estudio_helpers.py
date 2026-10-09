"""Dados de teste do AI Studio (spec 029, T002): o perfil, um item da biblioteca da agência pela
rota nova (`item`), as listas com filtros (`listar`) e a semeadura em lote por SQL para o teste de
desempenho (`semear_biblioteca`). Nada chama serviço real."""

import io
import uuid
from collections.abc import Sequence

from PIL import Image as PILImage
from sqlalchemy import text
from sqlalchemy.orm import Session

# Os tipos de asset que entram pelo atalho "um arquivo = um asset".
ATALHO = ("imagem", "sticker", "marca_dagua", "fundo")


def png(size=(600, 600), cor=(30, 120, 200), alpha: int | None = None) -> bytes:
    buf = io.BytesIO()
    if alpha is None:
        PILImage.new("RGB", size, cor).save(buf, format="PNG")
    else:
        PILImage.new("RGBA", size, (*cor, alpha)).save(buf, format="PNG")
    return buf.getvalue()


def perfil(client, h, slug: str) -> str:
    r = client.post("/api/perfis", json={"name": slug.title(), "slug": slug}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["perfil"]["id"]


def item(client, h, tipo: str, perfil_id: str | None, status: int = 201, **kw) -> dict:
    """Cria pela rota da agência: avatar e cenário (`/api/assets`), os tipos do atalho
    (`/api/assets/arquivo`), `produto` (`/api/produtos`) e `voz` (`/api/vozes`)."""
    if tipo in ("avatar", "cenario"):
        corpo = {"tipo": tipo, "name": kw.pop("name", tipo.title()), "perfilId": perfil_id} | kw
        r = client.post("/api/assets", headers=h, json=corpo)
        chave = "asset"
    elif tipo in ATALHO:
        dados = kw.pop("dados", None) or png(alpha=0 if tipo in ("sticker", "marca_dagua")
                                             else None)
        form = {"tipo": tipo, "name": kw.pop("name", tipo), **kw}
        if perfil_id is not None:
            form["perfilId"] = perfil_id
        r = client.post("/api/assets/arquivo", headers=h, data=form,
                        files={"file": ("f.png", dados, "application/octet-stream")})
        chave = "asset"
    elif tipo == "produto":
        form = {"name": kw.pop("name", "shorts_canelado"), **kw}
        if perfil_id is not None:
            form["perfilId"] = perfil_id
        r = client.post("/api/produtos", headers=h, data=form)
        chave = None
    elif tipo == "voz":
        corpo = {"name": kw.pop("name", "Ana vendas"), "origem": "gravacao",
                 "tom": "vendas animada", "perfilId": perfil_id} | kw
        r = client.post("/api/vozes", headers=h, json=corpo)
        chave = None
    else:
        raise ValueError(tipo)
    assert r.status_code == status, r.text
    body = r.json()
    return body[chave] if chave and status == 201 else body


def listar(client, h, rota: str, status: int = 200, **filtros) -> dict:
    """`GET /api/<rota>` com os filtros como query (`perfilId`, `tipo`, `q`…)."""
    r = client.get(f"/api/{rota}", headers=h, params=filtros)
    assert r.status_code == status, r.text
    return r.json()


def itens(lista: dict) -> list[dict]:
    """Os itens de qualquer lista da agência (`items` dos assets, `itens` dos outros)."""
    return lista.get("items", lista.get("itens"))


def ids(lista: dict) -> set[str]:
    return {i["id"] for i in itens(lista)}


def semear_biblioteca(db: Session, n: int, perfis: Sequence[uuid.UUID | None],
                      tipo: str = "imagem") -> None:
    """`n` assets em lote por SQL, distribuídos entre os perfis (None = sem perfil), com
    `updated_at` distintos. Sem arquivos nem versões: só para medir a lista."""
    linhas = [{"id": uuid.uuid4(), "p": perfis[i % len(perfis)], "t": tipo, "n": f"Item {i}",
               "s": i} for i in range(n)]
    db.execute(text(
        "INSERT INTO assets (id, perfil_id, tipo, name, tags, updated_at, created_at) "
        "VALUES (:id, :p, CAST(:t AS asset_tipo), :n, ARRAY['lote'], "
        "now() - make_interval(secs => :s), now())"), linhas)
    db.commit()
