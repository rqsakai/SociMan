"""Cliente do OpenShorts (T045; R6, princípio I). `test_openshorts.py` é da exportação da 004."""

import json

import httpx
import pytest

from sociman_api.envios import openshorts
from sociman_api.envios.openshorts import (
    ALLOWED,
    OpenShortsClient,
    OpenShortsFora,
    OpenShortsNaoEncontrado,
    OpenShortsOcupado,
    OpenShortsRecusou,
    corpo_process,
)

BASE = "http://openshorts.test"
PROIBIDOS = ("/api/social", "/api/thumbnail/publish", "/api/saasshorts/post")


class Gravador:
    def __init__(self, status: int = 200, body: dict | None = None):
        self.requests: list[httpx.Request] = []
        self.status = status
        self.body = body

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        path = request.url.path
        if self.body is not None:
            return httpx.Response(self.status, json=self.body)
        if path == "/api/uploads":
            return httpx.Response(200, json={"upload_id": "u1", "upload_url": "http://x/y"})
        if path == "/api/subtitle":
            return httpx.Response(200, json={"new_video_url": "/videos/j/sub.mp4"})
        if path.startswith("/videos/"):
            return httpx.Response(200, content=b"video")
        return httpx.Response(200, json={"job_id": "j", "status": "queued", "captions": []})


def _client(handler) -> OpenShortsClient:
    return OpenShortsClient(base_url=BASE, transport=httpx.MockTransport(handler))


def test_so_chama_a_lista_fechada(tmp_path):
    g = Gravador()
    c = _client(g)
    assert c.health() is True
    c.process({"url": "https://youtu.be/x"})
    assert c.reserve_upload("fonte.mp4") == "u1"
    c.put_upload("u1", iter([b"ab", b"cd"]), 4)
    c.status("j")
    assert c.subtitle("j", 0, {"font_name": "Anton"}, "a_clip_1.mp4") == "/videos/j/sub.mp4"
    c.transcript("j", 2)
    assert c.download("/videos/j/a_clip_1.mp4", tmp_path / "c.mp4") == 5

    feitos = [(r.method, r.url.path) for r in g.requests]
    assert feitos == [
        ("GET", "/health"), ("POST", "/api/process"), ("POST", "/api/uploads"),
        ("PUT", "/api/uploads/u1"), ("GET", "/api/status/j"), ("POST", "/api/subtitle"),
        ("GET", "/api/clip/j/2/transcript"), ("GET", "/videos/j/a_clip_1.mp4"),
    ]
    for method, path in feitos:
        assert openshorts._allowed(method, path)
    assert g.requests[3].content == b"abcd"
    body = json.loads(g.requests[5].content)
    assert body == {"font_name": "Anton", "job_id": "j", "clip_index": 0,
                    "input_filename": "a_clip_1.mp4"}
    # o PUT vai para o OPENSHORTS_URL, nunca para o upload_url devolvido
    assert all(r.url.host == "openshorts.test" for r in g.requests)


def test_lista_nao_tem_rotas_de_publicacao():
    for _method, prefix in ALLOWED:
        assert not any(p.startswith(prefix) or prefix.startswith(p) for p in PROIBIDOS)
    for path in PROIBIDOS + ("/api/social/post", "/api/hook", "/api/edit"):
        assert not openshorts._allowed("POST", path)
    assert not openshorts._allowed("DELETE", "/api/uploads/u1")


def test_request_fora_da_lista_e_recusado():
    c = _client(Gravador())
    with pytest.raises(ValueError):
        c._request("POST", "/api/social/post", "x")
    with pytest.raises(ValueError):
        c._request("POST", "/api/thumbnail/publish", "x")


@pytest.mark.parametrize("url", [
    "/api/status/j", "/videos/../api/social/post", "/videos/j/../../x", "https://evil.com/videos/j/a.mp4",
    "/videosx/j/a.mp4", "file:///etc/passwd", "/videos/",
])
def test_download_recusa_fora_de_videos(tmp_path, url):
    g = Gravador()
    with pytest.raises(ValueError):
        _client(g).download(url, tmp_path / "x.mp4")
    assert g.requests == []


def test_download_aceita_url_absoluta_do_proprio_openshorts(tmp_path, monkeypatch):
    from sociman_api.config import get_settings

    monkeypatch.setattr(get_settings(), "openshorts_url", BASE)
    g = Gravador()
    assert _client(g).download(f"{BASE}/videos/j/a.mp4", tmp_path / "x.mp4") == 5


@pytest.mark.parametrize(("status", "exc"), [
    (500, OpenShortsFora), (503, OpenShortsFora), (429, OpenShortsOcupado),
    (404, OpenShortsNaoEncontrado), (400, OpenShortsRecusou), (403, OpenShortsRecusou),
])
def test_erros_tipados(status, exc):
    c = _client(Gravador(status, {"detail": "motivo do gerador"}))
    with pytest.raises(exc) as info:
        c.status("j")
    assert info.value.status == status and info.value.detail == "motivo do gerador"


def test_conexao_recusada_vira_fora():
    def handler(request):
        raise httpx.ConnectError("recusada", request=request)

    c = _client(handler)
    with pytest.raises(OpenShortsFora):
        c.process({"url": "x"})
    assert c.health() is False


CONFIG = {"clip_min_s": 15, "clip_max_s": 60, "quantidade": None, "layout": "auto",
          "formato": "vertical", "legenda": "kit", "marca_automatica": False}


def test_corpo_do_process():
    assert corpo_process(CONFIG, url="https://www.youtube.com/watch?v=abc") == {
        "url": "https://www.youtube.com/watch?v=abc", "acknowledged": True, "auto_hook": False,
        "captions": False, "layouts": ["auto"], "output_format": "vertical",
        "clip_min_seconds": 15, "clip_max_seconds": 60,
    }
    body = corpo_process(CONFIG | {"legenda": "gerador", "quantidade": 6, "layout": "split",
                                   "formato": "square"}, upload_id="u1", force_low_quality=True)
    assert body["upload_id"] == "u1" and "url" not in body
    assert body["captions"] is True and body["target_clips"] == 6
    assert body["layouts"] == ["split"] and body["output_format"] == "square"
    assert body["force_low_quality"] is True and body["auto_hook"] is False
    assert corpo_process(CONFIG | {"legenda": "nenhuma"}, url="u")["captions"] is False
    with pytest.raises(ValueError):
        corpo_process(CONFIG)
