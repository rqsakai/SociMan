"""Cliente da TikTok (spec 015, T018): lista fechada, hosts restritos, `redact` e erros tipados,
sempre contra a TikTok falsa (R18)."""

import logging

import httpx
import pytest

from sociman_api.publicacao import executor, registro
from sociman_api.publicacao.tiktok import cliente
from sociman_api.publicacao.tiktok.cliente import TikTokCliente, redact


def test_pedido_fora_do_allowed_e_recusado(tiktok_fake):
    c = tiktok_fake.client()
    for metodo, caminho in (("DELETE", "/v2/oauth/token/"), ("POST", "/v2/video/upload/"),
                            ("GET", "/v2/post/publish/video/init/"), ("POST", "/v2/user/info/")):
        with pytest.raises(executor.PedidoProibido):
            c.api(metodo, caminho)
    assert tiktok_fake.requests == []  # nada saiu


def test_leitura_da_016_passa_e_o_resto_continua_recusado(tiktok_fake):
    """Spec 016 (R2): só `video/list` e `video/query` entram (`LEITURA_016`)."""
    assert cliente.LEITURA_016 == {("POST", "/v2/video/list/"), ("POST", "/v2/video/query/")}
    assert cliente.ALLOWED == cliente.R21 | cliente.LEITURA_016
    c = tiktok_fake.client()
    access, _ = tiktok_fake.emitir_tokens("open-um")
    c.api("POST", "/v2/video/list/", token=access, json={"max_count": 20})
    c.api("POST", "/v2/video/query/", token=access, json={"filters": {"video_ids": ["1"]}})
    assert [e for _, e, _ in tiktok_fake.requests] == ["video_list", "video_query"]
    for metodo, caminho in (("GET", "/v2/video/list/"), ("POST", "/v2/video/upload/"),
                            ("POST", "/v2/video/delete/"), ("POST", "/v2/research/video/query/")):
        with pytest.raises(executor.PedidoProibido):
            c.api(metodo, caminho, token=access)
    assert len(tiktok_fake.requests) == 2


@pytest.mark.parametrize("url", [
    "https://evil.example.com/upload/?upload_token=x",
    "http://open-upload.tiktokapis.com/upload/",  # sem https
    "https://tiktokapis.com.evil.com/upload/",
    "https://open-upload.tiktokapis.co/upload/",
])
def test_put_de_parte_para_outro_host_e_recusado(tiktok_fake, url):
    with pytest.raises(executor.PedidoProibido) as exc:
        tiktok_fake.client().put_parte(url, b"abc", 0, 3)
    assert "upload_token" not in str(exc.value)
    assert tiktok_fake.pedidos("put") == []


def test_put_em_host_extra_so_quando_configurado():
    vistos = []
    transport = httpx.MockTransport(lambda r: vistos.append(r.url.host) or httpx.Response(201))
    with pytest.raises(executor.PedidoProibido):
        TikTokCliente(transport=transport).put_parte("http://fakes:8000/up", b"a", 0, 1)
    TikTokCliente(transport=transport, hosts_extras=["fakes"]).put_parte(
        "http://fakes:8000/up", b"a", 0, 1)
    assert vistos == ["fakes"]


def test_avatar_so_da_cdn_e_so_imagem(tiktok_fake):
    c = tiktok_fake.client()
    dados, tipo = c.get_avatar("https://p16-sign.tiktokcdn-us.com/a.jpeg")
    assert tipo == "image/png" and dados.startswith(b"\x89PNG")
    with pytest.raises(executor.PedidoProibido):
        c.get_avatar("https://example.com/a.jpeg")
    texto = httpx.MockTransport(lambda r: httpx.Response(200, text="<html>",
                                                         headers={"content-type": "text/html"}))
    with pytest.raises(executor.RecusaRede):
        TikTokCliente(transport=texto).get_avatar("https://x.tiktokcdn.com/a")
    grande = httpx.MockTransport(lambda r: httpx.Response(
        200, content=b"x" * (cliente.AVATAR_MAX_BYTES + 1), headers={"content-type": "image/png"}))
    with pytest.raises(executor.RecusaRede, match="1 MB"):
        TikTokCliente(transport=grande).get_avatar("https://x.tiktokcdn.com/a")


def test_redact_troca_os_segredos():
    texto = (
        "https://open-upload.tiktokapis.com/upload/?upload_id=1&upload_token=SEGREDO1 "
        "code=SEGREDO2&code_verifier=SEGREDO3 client_secret=SEGREDO4 "
        '{"access_token": "SEGREDO5", "refresh_token": "SEGREDO6"} '
        "{'client_secret': 'SEGREDO7'} error_code=mantido"
    )
    limpo = redact(texto)
    assert "SEGREDO" not in limpo
    assert "upload_token=***" in limpo and '"access_token": "***"' in limpo
    assert "error_code=mantido" in limpo


def test_erros_tipados(tiktok_fake):
    c = tiktok_fake.client()
    tiktok_fake.falhar_proximo("status", "conexao")
    with pytest.raises(executor.ConexaoIndisponivel):
        c.api("POST", "/v2/post/publish/status/fetch/", token="x", json={})
    tiktok_fake.falhar_proximo("status", "timeout")
    with pytest.raises(executor.SemResposta):
        c.api("POST", "/v2/post/publish/status/fetch/", token="x", json={})
    tiktok_fake.falhar_proximo("status", "5xx")
    with pytest.raises(executor.ConexaoIndisponivel):
        c.api("POST", "/v2/post/publish/status/fetch/", token="x", json={})
    with pytest.raises(executor.RecusaRede) as exc:  # token desconhecido
        c.api("POST", "/v2/post/publish/status/fetch/", token="x", json={})
    assert exc.value.codigo == "access_token_invalid"
    with pytest.raises(executor.ConexaoPerdida):  # refresh desconhecido → invalid_grant
        c.api("POST", "/v2/oauth/token/", data={"grant_type": "refresh_token",
                                                 "refresh_token": "rft.velho"})
    # Os erros do cliente são os genéricos que a trilha e as conexões importam do registro.
    assert issubclass(cliente.ConexaoPerdida, registro.ConexaoPerdida)
    assert issubclass(cliente.SemResposta, registro.TikTokErro)


def test_fluxo_no_fake_rotacao_e_partes(tiktok_fake, caplog):
    caplog.set_level(logging.DEBUG)
    c = tiktok_fake.client()
    tiktok_fake.usuario("cod-1", "atavernanerd", verifier="v" * 64)
    tok = c.api("POST", "/v2/oauth/token/", data={"grant_type": "authorization_code",
                                                   "code": "cod-1", "code_verifier": "v" * 64})
    novo = c.api("POST", "/v2/oauth/token/", data={"grant_type": "refresh_token",
                                                    "refresh_token": tok["refresh_token"]})
    assert novo["refresh_token"] != tok["refresh_token"]
    with pytest.raises(executor.ConexaoPerdida):  # o refresh antigo foi gasto (rotação)
        c.api("POST", "/v2/oauth/token/", data={"grant_type": "refresh_token",
                                                 "refresh_token": tok["refresh_token"]})
    info = c.api("GET", "/v2/user/info/", token=novo["access_token"],
                 params={"fields": "open_id,username"})
    assert info["data"]["user"]["username"] == "atavernanerd"

    video = b"0123456789"
    init = c.api("POST", cliente.INIT_INBOX, token=novo["access_token"], json={
        "source_info": {"source": "FILE_UPLOAD", "video_size": 10, "chunk_size": 5,
                        "total_chunk_count": 2}})["data"]  # total = floor(10/5)
    c.put_parte(init["upload_url"], video[:5], 0, 10)
    c.put_parte(init["upload_url"], video[:5], 0, 10)  # a mesma parte de novo: repetível
    c.put_parte(init["upload_url"], video[5:], 5, 10)
    estados = [c.api("POST", "/v2/post/publish/status/fetch/", token=novo["access_token"],
                     json={"publish_id": init["publish_id"]})["data"]["status"]
               for _ in range(3)]
    assert estados == ["PROCESSING_UPLOAD", "PROCESSING_UPLOAD", "SEND_TO_USER_INBOX"]
    assert tiktok_fake.inits == 1
    assert tiktok_fake.pedidos("inbox_init")[0]["post_info"] is None
    assert [d["content_range"] for d in tiktok_fake.pedidos("put")] == [
        "bytes 0-4/10", "bytes 0-4/10", "bytes 5-9/10"]
    # Nenhum segredo no log (só método, caminho e status).
    for segredo in (tok["access_token"], tok["refresh_token"], novo["access_token"],
                    init["upload_url"], "upload_token", "v" * 64):
        assert segredo not in caplog.text
