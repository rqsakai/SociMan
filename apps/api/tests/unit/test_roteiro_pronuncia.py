"""Pronúncias e o hash da narração (spec 011, T009, research R10): funções puras."""

import uuid
from decimal import Decimal

from sociman_api.roteiros.pronuncia import aplicar, hash_atual

DIC = {"levinho": "lévinho", "leve": "lévi"}
VOZ, REF = uuid.uuid4(), uuid.uuid4()


def test_palavra_inteira_sem_caixa_e_inicial_preservada():
    assert aplicar("Tecido levinho e leve.", DIC) == "Tecido lévinho e lévi."
    assert aplicar("Levinho! LEVE?", DIC) == "Lévinho! Lévi?"
    # Só a palavra inteira: "levemente" e "relevo" ficam.
    assert aplicar("levemente, relevo, leve-leve", DIC) == "levemente, relevo, lévi-lévi"


def test_comentario_vazio_e_ordem_como_no_servico():
    assert aplicar("leve", {"_doc": "comentário", "leve": "lévi"}) == "lévi"
    assert aplicar("leve", {}) == "leve"
    # Os pares entram na ordem do dicionário, como no `_pron` (um pode reescrever o outro).
    assert aplicar("tá", {"tá": "está", "está": "ésta"}) == "ésta"


def test_caracteres_especiais_da_escrita_sao_literais():
    assert aplicar("o c.a. e o cxa", {"c.a.": "cê-á"}) == "o cê-á e o cxa"


def test_hash_muda_com_o_que_muda_o_audio():
    base = hash_atual(["Tecido levinho."], DIC, VOZ, REF, Decimal("1.08"))
    assert base == hash_atual(["Tecido levinho."], dict(DIC), str(VOZ), str(REF), 1.08)
    assert base == hash_atual(["Tecido levinho."], DIC, VOZ, REF, "1.080")
    assert base != hash_atual(["Tecido levinho!"], DIC, VOZ, REF, 1.08)
    assert base != hash_atual(["Tecido levinho."], {}, VOZ, REF, 1.08)
    assert base != hash_atual(["Tecido levinho."], DIC, uuid.uuid4(), REF, 1.08)
    assert base != hash_atual(["Tecido levinho."], DIC, VOZ, uuid.uuid4(), 1.08)
    assert base != hash_atual(["Tecido levinho."], DIC, VOZ, None, 1.08)
    assert base != hash_atual(["Tecido levinho."], DIC, VOZ, REF, 1.1)


def test_hash_so_olha_a_pronuncia_aplicada():
    # Um par que não aparece nas frases não deixa a narração desatualizada.
    assert (hash_atual(["Oi, gente!"], {}, VOZ, REF, 1.0)
            == hash_atual(["Oi, gente!"], {"levinho": "lévinho"}, VOZ, REF, 1.0))
    # Grafia falada igual = mesmo áudio.
    assert (hash_atual(["lévinho"], {}, VOZ, REF, 1.0)
            == hash_atual(["levinho"], DIC, VOZ, REF, 1.0))
    assert len(hash_atual([], {}, VOZ, None, 1.0)) == 64
