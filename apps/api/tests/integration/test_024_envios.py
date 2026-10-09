"""Contagem de clipes por geração (spec 024, US5, T038; FR-018, FR-019, R8).

Os cortes entram direto pelo modelo, como em `test_cortes_revisao.py`.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from integration import envios_helpers
from sociman_api.cortes.models import Corte, CorteOrigem, CorteStatus
from sociman_api.db import get_sessionmaker
from sociman_api.envios.models import Envio, EnvioOrigem

# Fixtures compartilhadas (atribuídas, e não importadas, para o ruff não acusar F811).
member = envios_helpers.member
owner = envios_helpers.owner
perfil = envios_helpers.perfil


def _envio(perfil_id: str) -> uuid.UUID:
    with get_sessionmaker()() as s:
        e = Envio(perfil_id=uuid.UUID(perfil_id), origem=EnvioOrigem.avulso_link,
                  source_url=f"https://vimeo.com/{uuid.uuid4().int % 10**8}",
                  source_title="Palestra")
        s.add(e)
        s.commit()
        return e.id


def _corte(perfil_id: str, envio_id: uuid.UUID, idx: int, status: CorteStatus,
           arquivado: bool = False) -> str:
    with get_sessionmaker()() as s:
        cid = uuid.uuid4()
        revisao = status == CorteStatus.revisao
        c = Corte(id=cid, perfil_id=uuid.UUID(perfil_id), hook_text="Olha isso", status=status,
                  kit_version=None if revisao else 0, kit_tokens=None if revisao else {},
                  origem=CorteOrigem.openshorts, envio_id=envio_id, clip_index=idx,
                  original_filename=f"clipe-{idx + 1}.mp4",
                  original_key=f"perfis/{perfil_id}/cortes/{cid}/original.mp4",
                  original_content_type="video/mp4", original_bytes=1000, duration_ms=20_000,
                  width=1080, height=1920, fps=Decimal(30), video_codec="h264",
                  audio_codec="aac", original_sha256="0" * 64,
                  result_key=f"perfis/{perfil_id}/cortes/{cid}/final.mp4"
                  if status == CorteStatus.pronto else None,
                  error_message="Falhou" if status == CorteStatus.falhou else None,
                  archived_at=datetime.now(UTC) if arquivado else None)
        s.add(c)
        s.commit()
        return str(cid)


def _geracao_completa(perfil_id: str) -> tuple[uuid.UUID, list[str]]:
    envio_id = _envio(perfil_id)
    estados = [CorteStatus.revisao, CorteStatus.revisao, CorteStatus.pronto, CorteStatus.pronto,
               CorteStatus.na_fila, CorteStatus.falhou]
    ids = [_corte(perfil_id, envio_id, i, st) for i, st in enumerate(estados)]
    ids.append(_corte(perfil_id, envio_id, len(estados), CorteStatus.revisao, arquivado=True))
    return envio_id, ids


def _da_lista(client, h, perfil_id: str, envio_id: uuid.UUID) -> dict:
    r = client.get("/api/envios", params={"perfilId": perfil_id}, headers=h)
    assert r.status_code == 200, r.text
    return next(e for e in r.json()["items"] if e["id"] == str(envio_id))


def test_contagens_por_estado(client, member, perfil):
    envio_id, _ = _geracao_completa(perfil["id"])
    esperado = {"aceitos": 3, "pendentes": 2, "falhou": 1, "arquivados": 1}
    assert _da_lista(client, member[1], perfil["id"], envio_id)["cortesResumo"] == esperado
    r = client.get(f"/api/envios/{envio_id}", headers=member[1])
    assert r.status_code == 200, r.text
    assert r.json()["envio"]["cortesResumo"] == esperado


def test_geracao_sem_cortes_e_null(client, member, perfil):
    envio_id = _envio(perfil["id"])
    assert _da_lista(client, member[1], perfil["id"], envio_id)["cortesResumo"] is None
    r = client.get(f"/api/envios/{envio_id}", headers=member[1])
    assert r.json()["envio"]["cortesResumo"] is None


def test_arquivar_muda_a_contagem(client, member, perfil):
    envio_id, ids = _geracao_completa(perfil["id"])
    h = member[1]
    corte = client.get(f"/api/cortes/{ids[0]}", headers=h).json()["corte"]  # um pendente
    r = client.post(f"/api/cortes/{ids[0]}/archive", json={"version": corte["version"]}, headers=h)
    assert r.status_code == 200, r.text
    assert _da_lista(client, h, perfil["id"], envio_id)["cortesResumo"] == {
        "aceitos": 3, "pendentes": 1, "falhou": 1, "arquivados": 2}


def test_contagens_separadas_por_geracao(client, member, perfil):
    a, _ = _geracao_completa(perfil["id"])
    b = _envio(perfil["id"])
    _corte(perfil["id"], b, 0, CorteStatus.processando)
    h = member[1]
    assert _da_lista(client, h, perfil["id"], a)["cortesResumo"]["aceitos"] == 3
    assert _da_lista(client, h, perfil["id"], b)["cortesResumo"] == {
        "aceitos": 1, "pendentes": 0, "falhou": 0, "arquivados": 0}
