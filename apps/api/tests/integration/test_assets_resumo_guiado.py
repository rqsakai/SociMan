"""O resumo dos assets para os blocos do "Novo vídeo" (spec 031, FR-003/004): a lista traz a voz
padrão do avatar (`vozId`), o consentimento revogado (`revogado`, 025) e, no cenário, se a
imagem `cena` do cadastro existe (`temCena`), sem abrir cada item."""

# ruff: noqa: F811 — fixtures importadas de `roteiro_helpers`

import uuid

from sqlalchemy import text

from integration.padrao_helpers import cenario, consentimento
from integration.roteiro_helpers import (  # noqa: F401 — fixtures
    _buckets,
    montar_guiado,
    motores,
    owner,
)


def _lista(client, h, perfil_id: str, archived: str = "false") -> dict[str, dict]:
    r = client.get("/api/assets", headers=h, params={"perfilId": perfil_id,
                                                     "archived": archived})
    assert r.status_code == 200, r.text
    return {a["id"]: a for a in r.json()["items"]}


def test_resumo_com_voz_revogado_e_cena(client, db, owner, motores):
    h = owner[1]
    b = montar_guiado(client, h, motores)
    sem_cena = cenario(client, h, b["perfil_id"], name="Sala sem cena")
    itens = _lista(client, h, b["perfil_id"])
    avatar, cen = itens[b["avatar"]["id"]], itens[b["cenario"]["id"]]
    assert (avatar["vozId"], avatar["revogado"], avatar["temCena"]) == (b["voz"]["id"], False,
                                                                        False)
    assert cen["temCena"] is True and cen["vozId"] is None
    assert itens[sem_cena["id"]]["temCena"] is False

    # O avatar de pessoa real com o consentimento revogado (que também é arquivado, 025) aparece
    # marcado na lista dos arquivados.
    db.execute(text("UPDATE assets SET origem = NULL WHERE id = :a"),
               {"a": uuid.UUID(b["avatar"]["id"])})
    db.commit()
    a = client.get(f"/api/assets/{b['avatar']['id']}", headers=h).json()["asset"]
    a = consentimento(client, h, a["id"], a["version"])["asset"]
    r = client.post(f"/api/assets/{a['id']}/consentimento/revogar", headers=h,
                    json={"version": a["version"], "confirmo": True})
    assert r.status_code == 200, r.text
    assert b["avatar"]["id"] not in _lista(client, h, b["perfil_id"])
    assert _lista(client, h, b["perfil_id"], "true")[b["avatar"]["id"]]["revogado"] is True
    detalhe = client.get(f"/api/assets/{b['avatar']['id']}", headers=h).json()["asset"]
    assert detalhe["revogado"] is True and "temCena" in detalhe
