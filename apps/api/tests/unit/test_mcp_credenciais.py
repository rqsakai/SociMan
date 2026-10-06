"""T007 (R4): formato, hash e verificação em tempo constante da credencial MCP (sem banco: a
sessão é um dublê com `scalar`)."""

import hashlib
import hmac
from datetime import UTC, datetime

from sociman_api.mcp import credenciais
from sociman_api.mcp.models import McpCliente, McpEscopo


class _Sessao:
    def __init__(self, cliente: McpCliente | None):
        self.cliente = cliente
        self.consultas = 0

    def scalar(self, _stmt):
        self.consultas += 1
        return self.cliente


def _cliente(token: str) -> McpCliente:
    return McpCliente(nome="Caçador", escopo=McpEscopo.leitura,
                      token_id=credenciais.token_id_de(token),
                      token_hash=credenciais.hash_token(token),
                      token_emitido_em=datetime.now(UTC))


def test_formato():
    token, token_id, hash_ = credenciais.gerar()
    assert credenciais.FORMATO.match(token)
    assert token.startswith(f"smcp_{token_id}_") and len(token) == 5 + 8 + 1 + 43
    assert hash_ == hashlib.sha256(token.encode()).digest() and len(hash_) == 32


def test_token_id_unico():
    assert len({credenciais.novo_token_id() for _ in range(500)}) == 500


def test_verificar_confere():
    token, _, _ = credenciais.gerar()
    cliente = _cliente(token)
    assert credenciais.verificar(_Sessao(cliente), token) is cliente


def test_segredo_errado_recusado():
    token, _, _ = credenciais.gerar()
    outro = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert credenciais.verificar(_Sessao(_cliente(token)), outro) is None


def test_malformado_e_inexistente_pelo_mesmo_caminho(monkeypatch):
    chamadas = []
    original = hmac.compare_digest

    def espiao(a, b):
        chamadas.append((len(a), len(b)))
        return original(a, b)

    monkeypatch.setattr(credenciais.hmac, "compare_digest", espiao)
    token, _, _ = credenciais.gerar()
    assert credenciais.verificar(_Sessao(None), token) is None  # <id> inexistente
    assert credenciais.verificar(_Sessao(None), "smcp_curto") is None  # malformado
    assert credenciais.verificar(_Sessao(None), "Bearer qualquer") is None
    assert chamadas == [(32, 32)] * 3  # sempre compara (hash fictício)


def test_repr_sem_token_nem_hash():
    token, _, _ = credenciais.gerar()
    cliente = _cliente(token)
    texto = repr(cliente) + str(cliente)
    segredo = token.rsplit("_", 1)[1]
    assert segredo not in texto and cliente.token_hash.hex() not in texto
    assert "token_hash" not in texto
