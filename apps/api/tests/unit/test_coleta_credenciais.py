"""T011 (FR-024): formato do token `scol_`, hash estável, repr mascarado e o `check:secrets`
acusando um token de exemplo (montado em tempo de execução, nunca um literal)."""

import hashlib
import re

from sociman_api.coleta import credenciais


def test_formato_e_hash():
    token, token_id, hash_ = credenciais.gerar()
    assert credenciais.FORMATO.match(token)
    assert credenciais.token_id_de(token) == token_id and len(token_id) == 8
    assert hash_ == hashlib.sha256(token.encode()).digest()
    assert credenciais.conferir(token, hash_)
    assert not credenciais.conferir(token[:-1] + ("a" if token[-1] != "a" else "b"), hash_)
    assert credenciais.e_token(token) and not credenciais.e_token("smcp_x") \
        and not credenciais.e_token(None)


def test_repr_nunca_mostra_o_segredo():
    token, _, _ = credenciais.gerar()
    assert "scol_***" in repr(token) and token[6:] not in repr(token)
    assert str(token) == token  # a `str` continua utilizável como credencial


def test_token_id_de_formato_errado_e_none():
    assert credenciais.token_id_de("scol_curto") is None
    assert credenciais.token_id_de("smcp_" + "a" * 8 + "_" + "b" * 43) is None


def test_padrao_do_check_secrets_casa_com_o_token():
    """O padrão do `scripts/check-secrets.mjs` (`scol_[a-z2-7]{8}_[A-Za-z0-9_-]{43}`) casa com um
    token sintético e não com um de segredo curto. O `.mjs` tem o mesmo autoteste em JS; aqui a
    regex é a mesma, em Python (o container da API não tem o repo nem o node)."""
    padrao = re.compile(r"\bscol_[a-z2-7]{8}_[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])")
    token, _, _ = credenciais.gerar()
    assert padrao.search(f"x {token} y")
    assert not padrao.search(f"x {token[:-1]} y")
    assert not padrao.search("x " + token.replace("scol_", "smcp_") + " y")
