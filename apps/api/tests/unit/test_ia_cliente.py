"""IaClient com o Claude falso (spec 008, T012, R8). Nenhuma chamada real."""

from decimal import Decimal

from fakes.anthropic_fake import CHAVE_TESTE, anthropic_fake, itens, mensagem, texto  # noqa: F401

from sociman_api.ia import cliente as cliente_mod
from sociman_api.ia.contexto import Contexto, PerfilBloco
from sociman_api.ia.prompt import montar_system, montar_user
from sociman_api.ia.saida import NADA, Excluir
from sociman_api.ia.tipos import TIPOS

CTX = Contexto(perfil=PerfilBloco(nome="Achadinhos"))


def _gerar(fake, tid, valor=None, excluir=NADA, **kw):
    tipo = TIPOS[tid]
    system = montar_system(tipo, tipo.padrao, CTX)
    return fake.ia_client(**kw).gerar(
        tipo, system, lambda erro: montar_user(tipo, CTX, valor or {}, "", erro_anterior=erro),
        excluir)


def test_pedido_sem_tools_com_schema_do_formato_e_fallback(anthropic_fake):  # noqa: F811
    res = _gerar(anthropic_fake, "perfil.bio")
    assert res.erro_code is None and res.validada.proposta == {"texto": "Texto proposto pela IA."}
    [req] = anthropic_fake.requests
    assert "server-side-fallback-2026-07-01" in req.headers["anthropic-beta"]
    body = anthropic_fake.bodies[0]
    assert "tools" not in body and "temperature" not in body and "thinking" not in body
    assert body["max_tokens"] == 2000 and body["fallbacks"] == "default"
    assert body["output_config"]["effort"] == "low"
    assert set(body["output_config"]["format"]["schema"]["properties"]) == {
        "proposta", "explicacao", "avisos"}
    assert CHAVE_TESTE not in repr(anthropic_fake.ia_client())


def test_cada_formato_pede_o_seu_schema(anthropic_fake):  # noqa: F811
    esperado = {"kit.bordoes": {"itens", "explicacao", "avisos"},
                "postagem.hashtags": {"itens", "explicacao", "avisos"},
                "postagem.textos": {"titulo", "descricao", "hashtags", "explicacao", "avisos"}}
    for tid, props in esperado.items():
        res = _gerar(anthropic_fake, tid)
        assert res.erro_code is None, (tid, res)
        schema = anthropic_fake.bodies[-1]["output_config"]["format"]["schema"]
        assert set(schema["properties"]) == props


def test_segunda_tentativa_com_o_erro_e_depois_excede(anthropic_fake):  # noqa: F811
    anthropic_fake.responder(texto("a" * 150), texto("b" * 140))
    res = _gerar(anthropic_fake, "postagem.titulo")
    assert len(anthropic_fake.requests) == 2
    assert "recusada pela validação" in anthropic_fake.bodies[1]["messages"][0]["content"]
    assert res.validada.excede and res.validada.proposta["texto"] == "b" * 140


def test_segunda_tentativa_corrige(anthropic_fake):  # noqa: F811
    anthropic_fake.responder(texto("a" * 150), texto("Título bom"))
    res = _gerar(anthropic_fake, "postagem.titulo")
    assert not res.validada.excede and res.validada.proposta["texto"] == "Título bom"


def test_sem_segunda_tentativa_se_a_primeira_demorou(anthropic_fake, monkeypatch):  # noqa: F811
    monkeypatch.setattr(cliente_mod, "SEGUNDA_TENTATIVA_ATE_S", -1.0)
    anthropic_fake.responder(texto("a" * 150))
    res = _gerar(anthropic_fake, "postagem.titulo")
    assert len(anthropic_fake.requests) == 1 and res.validada.excede


def test_sugestoes_repetidas_duas_vezes_viram_invalid(anthropic_fake):  # noqa: F811
    anthropic_fake.responder(itens("Olha isso!"), itens("olha isso!"))
    res = _gerar(anthropic_fake, "kit.bordoes", {"itens": ["Olha isso!"]},
                 Excluir(atuais=("Olha isso!",)))
    assert res.erro_code == "invalid" and res.validada is None


def test_json_invalido_duas_vezes(anthropic_fake):  # noqa: F811
    anthropic_fake.responder(mensagem({"x": 1}), mensagem({"y": 2}))
    res = _gerar(anthropic_fake, "perfil.bio")
    assert res.erro_code == "invalid"


def test_timeout_recusa_e_erros_http(anthropic_fake):  # noqa: F811
    anthropic_fake.responder("timeout")
    assert _gerar(anthropic_fake, "perfil.bio").erro_code == "timeout"
    anthropic_fake.responder("recusa")
    assert _gerar(anthropic_fake, "perfil.bio").erro_code == "refusal"
    for status in (401, 429):
        anthropic_fake.responder((status, {"type": "error", "error": {
            "type": "x", "message": "x"}}))
        res = _gerar(anthropic_fake, "perfil.bio")
        assert (res.erro_code, res.erro_status) == ("api_error", status)


def test_soma_de_uso_com_cache_e_fallback(anthropic_fake):  # noqa: F811
    usage1 = {"input_tokens": 100, "output_tokens": 200, "cache_read_input_tokens": 0,
              "cache_creation_input_tokens": 2000}
    usage2 = {"input_tokens": 1000, "output_tokens": 300, "cache_read_input_tokens": 2000,
              "cache_creation_input_tokens": 0, "iterations": [
                  {"type": "message", "input_tokens": 500, "output_tokens": 0,
                   "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0},
                  {"type": "fallback_message", "model": "claude-opus-5-5", "input_tokens": 500,
                   "output_tokens": 300, "cache_read_input_tokens": 1000,
                   "cache_creation_input_tokens": 0}]}
    anthropic_fake.responder(texto("a" * 150, usage=usage1),
                             texto("Ok", usage=usage2, model="claude-opus-5-5"))
    res = _gerar(anthropic_fake, "postagem.titulo")
    u = res.uso
    assert (u.input_tokens, u.output_tokens) == (1100, 500)
    assert (u.cache_read_tokens, u.cache_creation_tokens) == (2000, 2000)
    assert u.model_servido == "claude-opus-5-5"
    # 1ª: 100×2 + 200×10 + 2000×2,5 = 7.200; 2ª: sonnet 500×2 + 1000×0,2 = 1.200;
    # opus 500×4 + 300×20 + 1000×0,2 = 8.200 → 16.600 por milhão
    assert u.custo_usd == Decimal("0.016600")


def test_base_url_da_config(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-de-teste")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://openshorts-fake:8000")
    from sociman_api.config import get_settings

    get_settings.cache_clear()
    try:
        c = cliente_mod.get_ia_client()
        assert str(c._client.base_url).startswith("http://openshorts-fake:8000")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        get_settings.cache_clear()
        assert cliente_mod.get_ia_client() is None
    finally:
        get_settings.cache_clear()
