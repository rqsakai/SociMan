"""Cifra dos tokens (spec 015, T016, research R4): AES-256-GCM com AAD por linha e campo,
`key_id` para a rotação e nenhuma chave em `repr` ou mensagem."""

import base64
import uuid

import pytest
from pydantic import SecretStr

from sociman_api.config import get_settings
from sociman_api.publicacao import cifra

CHAVE_A = base64.urlsafe_b64encode(b"a" * 32).decode()
CHAVE_B = base64.urlsafe_b64encode(b"b" * 32).decode()


@pytest.fixture
def chaves(monkeypatch):
    def _set(atual: str, anterior: str = "") -> None:
        s = get_settings()
        monkeypatch.setattr(s, "sociman_tokens_key", SecretStr(atual))
        monkeypatch.setattr(s, "sociman_tokens_key_anterior", SecretStr(anterior))

    return _set


def test_cifra_e_decifra_com_aad(chaves):
    chaves(CHAVE_A)
    cid = uuid.uuid4()
    dados, kid = cifra.cifrar("act.segredo", cifra.aad(cid, "access"))
    assert kid == cifra.key_id(b"a" * 32) and len(kid) == 8
    assert b"act.segredo" not in dados
    assert len(dados) > cifra.NONCE_BYTES
    assert cifra.decifrar(dados, cifra.aad(cid, "access"), kid) == "act.segredo"
    # Nonce aleatório: a mesma entrada dá saídas diferentes.
    assert cifra.cifrar("act.segredo", cifra.aad(cid, "access"))[0] != dados


def test_aad_trocado_nao_decifra(chaves):
    chaves(CHAVE_A)
    cid, outra = uuid.uuid4(), uuid.uuid4()
    dados, kid = cifra.cifrar("rft.segredo", cifra.aad(cid, "refresh"))
    for aad in (cifra.aad(outra, "refresh"), cifra.aad(cid, "access")):
        with pytest.raises(cifra.DecifraFalhou):
            cifra.decifrar(dados, aad, kid)


def test_chave_anterior_decifra_e_pede_recifrar(chaves):
    chaves(CHAVE_A)
    cid = uuid.uuid4()
    dados, kid_antiga = cifra.cifrar("act.velho", cifra.aad(cid, "access"))
    chaves(CHAVE_B, anterior=CHAVE_A)  # rotação
    assert cifra.precisa_recifrar(kid_antiga)
    assert cifra.decifrar(dados, cifra.aad(cid, "access"), kid_antiga) == "act.velho"
    novo, kid_nova = cifra.cifrar("act.velho", cifra.aad(cid, "access"))
    assert kid_nova == cifra.key_id_atual() != kid_antiga
    assert not cifra.precisa_recifrar(kid_nova)
    assert cifra.decifrar(novo, cifra.aad(cid, "access")) == "act.velho"  # sem key_id
    chaves(CHAVE_B)  # a anterior saiu do .env
    with pytest.raises(cifra.ChaveDesconhecida):
        cifra.decifrar(dados, cifra.aad(cid, "access"), kid_antiga)


def test_sem_chave_erro_tipado(chaves):
    chaves("")
    assert not cifra.chave_configurada()
    with pytest.raises(cifra.ChaveAusente):
        cifra.cifrar("x", cifra.aad(uuid.uuid4(), "access"))


@pytest.mark.parametrize("ruim", ["curta", base64.urlsafe_b64encode(b"x" * 16).decode(), "%%%"])
def test_chave_invalida_erro_tipado(chaves, ruim):
    chaves(ruim)
    assert not cifra.chave_configurada()
    with pytest.raises(cifra.ChaveInvalida) as exc:
        cifra.cifrar("x", cifra.aad(uuid.uuid4(), "access"))
    assert ruim not in str(exc.value)


def test_chave_nunca_aparece_em_repr_nem_em_mensagens(chaves):
    chaves(CHAVE_A)
    s = get_settings()
    assert CHAVE_A not in repr(s) and CHAVE_A not in str(s.model_dump())
    assert "aaaa" not in repr(cifra._atual())
    cid = uuid.uuid4()
    dados, kid = cifra.cifrar("act.segredo", cifra.aad(cid, "access"))
    with pytest.raises(cifra.CifraErro) as exc:
        cifra.decifrar(dados, cifra.aad(cid, "refresh"), kid)
    assert CHAVE_A not in str(exc.value) and "act.segredo" not in str(exc.value)


def test_campo_de_aad_desconhecido():
    with pytest.raises(ValueError):
        cifra.aad(uuid.uuid4(), "senha")
