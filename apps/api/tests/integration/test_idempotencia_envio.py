"""Idempotência do envio (spec 015, T042, SC-003; research R8): a trilha "cai" depois de cada
commit e antes de cada chamada à rede, reinicia e segue. No registro da TikTok falsa, cada
destino tem **exatamente um init** (e um rascunho), ou a tentativa fica `incerta` (destino
`falhou` com `falha_incerta`) quando o corte foi entre o init e a resposta. O init nunca é
repetido sem um humano."""

import pytest
from sqlalchemy import text

from integration import publicacao_helpers as ph
from sociman_api.db import get_engine
from sociman_api.perfis.models import Platform
from sociman_api.postagem.models import DestinoEstado
from sociman_api.publicacao import registro, trilha
from sociman_api.publicacao.models import TentativaFase

# Fixtures do apoio (o pytest as acha pelo nome no módulo).
app_tiktok = ph.app_tiktok
cena = ph.cena


class Queda(Exception):
    """O processo do agendador morreu aqui."""


def _partes_pequenas(monkeypatch) -> None:
    monkeypatch.setattr(trilha, "CHUNK", 1024)
    monkeypatch.setattr(trilha, "INTEIRO_ATE", 1024)


def _reiniciar_e_terminar(cena, voltas: int = 8) -> None:
    cena.db.rollback()
    cena.db.expire_all()
    cena.rodar(voltas)


def _conferir(cena, destino_id) -> None:
    destino = cena.destino(destino_id)
    ts = cena.tentativas(destino_id)
    assert len(cena.fake.envios) <= 1, "dois envios criados na rede para o mesmo destino"
    assert cena.fake.inits <= 1, "o init foi repetido sem um humano"
    assert len(ts) == 1
    if destino.estado == DestinoEstado.rascunho_criado:
        assert cena.fake.inits == 1 and ts[0].fase == TentativaFase.entregue
        envio = next(iter(cena.fake.envios.values()))
        assert envio.completo  # o vídeo chegou inteiro
    else:
        assert destino.estado == DestinoEstado.falhou and destino.falha_incerta, \
            (destino.estado, ts[0].fase, ts[0].codigo_rede)
        assert ts[0].fase == TentativaFase.incerta


@pytest.mark.parametrize("n", range(1, 12))
def test_queda_depois_de_cada_commit(cena, monkeypatch, n):
    _partes_pequenas(monkeypatch)
    d = cena.agendado(tamanho=3000)  # 3 partes
    original = cena.db.commit
    commits = {"n": 0}

    def commit_e_cair():
        original()
        commits["n"] += 1
        if commits["n"] == n:
            raise Queda(f"queda depois do commit {n}")

    cena.db.commit = commit_e_cair
    try:
        cena.rodar(6)
    except Queda:
        pass
    cena.db.commit = original
    _reiniciar_e_terminar(cena)
    _conferir(cena, d["id"])


@pytest.mark.parametrize("n", range(1, 8))
def test_queda_antes_de_cada_chamada(cena, monkeypatch, n):
    _partes_pequenas(monkeypatch)
    d = cena.agendado(tamanho=3000)
    classe = type(registro.executor_para(Platform.tiktok))
    originais = {nome: getattr(classe, nome) for nome in ("iniciar", "enviar_parte",
                                                          "consultar")}
    chamadas = {"n": 0}

    def cair_antes(nome):
        def wrapper(self, *args, **kwargs):
            chamadas["n"] += 1
            if chamadas["n"] == n:
                raise Queda(f"queda antes de {nome}")
            return originais[nome](self, *args, **kwargs)

        return wrapper

    for nome in originais:
        monkeypatch.setattr(classe, nome, cair_antes(nome))
    try:
        cena.rodar(6)
    except Queda:
        pass
    for nome, original in originais.items():
        monkeypatch.setattr(classe, nome, original)
    _reiniciar_e_terminar(cena)
    _conferir(cena, d["id"])


def test_resposta_do_init_perdida_vira_incerta_e_nao_repete(cena):
    d = cena.agendado()
    cena.fake.falhar_proximo("inbox_init", "timeout_depois")  # a TikTok criou; a resposta sumiu
    cena.rodar(5)
    destino = cena.destino(d["id"])
    t = cena.tentativas(d["id"])[0]
    assert cena.fake.inits == 1 and len(cena.fake.envios) == 1
    assert t.fase == TentativaFase.incerta and t.publish_id is None
    assert destino.estado == DestinoEstado.falhou and destino.falha_incerta
    assert t.details["acao"] == "tentar_de_novo_conferido"


def test_parte_em_voo_reenviada_inteira(cena, monkeypatch):
    _partes_pequenas(monkeypatch)
    d = cena.agendado(tamanho=3000)
    cena.fake.falhar_proximo("put", "timeout")  # a 1ª parte saiu e a resposta não veio
    monkeypatch.setattr(registro.executor_para(Platform.tiktok), "recuos_parte", ())
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert t.fase == TentativaFase.enviando_partes and t.partes_enviadas == 0
    cena.rodar(5)
    ranges = [p["content_range"] for p in cena.fake.pedidos("put")]
    assert ranges[:2] == ["bytes 0-1023/3000", "bytes 0-1023/3000"]  # a mesma, inteira
    assert cena.destino(d["id"]).estado == DestinoEstado.rascunho_criado
    assert cena.fake.inits == 1


def test_link_vencido_na_retomada_recusa(cena, monkeypatch):
    _partes_pequenas(monkeypatch)
    d = cena.agendado(tamanho=3000)
    cena.fake.falhar_sempre["put"] = "5xx"
    monkeypatch.setattr(registro.executor_para(Platform.tiktok), "recuos_parte", ())
    cena.rodar()
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE publicacao_tentativas "
                          "SET upload_url_expira_em = now() - interval '1 minute'"))
    del cena.fake.falhar_sempre["put"]
    cena.rodar()
    t = cena.tentativas(d["id"])[0]
    assert t.fase == TentativaFase.recusada and t.codigo_rede == "upload_url_expirou"
    destino = cena.destino(d["id"])
    assert destino.estado == DestinoEstado.falhou and not destino.falha_incerta
    assert cena.fake.inits == 1
