"""TikTok falsa (spec 015, T020, research R18): `httpx.MockTransport` com estado.

Simula o Login Kit e a Content Posting API, com as respostas de `tests/fixtures/tiktok/*.json`
(nenhum token real). Uso:

    def test_x(tiktok_fake):  # fixture do conftest
        tiktok_fake.usuario("codigo-1", "atavernanerd")        # o que o login devolve
        cliente = tiktok_fake.client()                         # TikTokCliente com o fake
        # ou registro.get_cliente(transport=tiktok_fake.transport)

O que existe:
- troca de código (com PKCE opcional: o `code_verifier` é conferido), refresh **com rotação**
  (o refresh usado vira `invalid_grant`), revogação, `user/info` (`username` configurável, ou
  None) e `creator_info`;
- init de inbox e direto (registra se veio `post_info`), PUT de partes (confere
  `Content-Range`, ordem e tamanho) e `status/fetch` com `passos_status` consultas até
  `SEND_TO_USER_INBOX` ou `PUBLISH_COMPLETE`;
- falhas: `falhar_proximo(endpoint, falha)` ou `falhar_sempre[endpoint] = falha`, com `falha`
  = "timeout" (sai sem resposta), "timeout_depois" (processa e não responde), "conexao"
  (não chega), "5xx", ou um código da TikTok (`spam_risk_too_many_pending_share`,
  `rate_limit_exceeded`, `access_token_invalid`,
  `unaudited_client_can_only_post_to_private_accounts`, …). `fail_reason` faz o próximo
  `status/fetch` devolver `FAILED` com esse motivo.

`requests` registra (método, endpoint, detalhes sem segredo) de tudo, para os guardas e o SC-003.
Endpoints: "token", "revoke", "user_info", "creator_info", "inbox_init", "video_init", "status",
"put", "avatar", "video_list" e "video_query".

Spec 016 (T017, research R17), só leitura:
- `user_info` devolve os campos de stats quando pedidos no `fields` (`seguidores(handle, n)`;
  sem configurar, 0 seguidores e `video_count` = vídeos públicos);
- `video_list`: cursor em ms (devolve os criados **antes** dele), `max_count` ≤ 20, `has_more`, só
  os públicos da conta do token, do mais novo ao mais antigo;
- `video_query`: até 20 ids, só os vídeos públicos **da conta do token**;
- os campos do vídeo vêm só os pedidos no `fields` (o `id` vem como número JSON, como na TikTok);
- controles: `video(handle, id, criado_em, duracao, legenda, publico=True)`,
  `contadores(id, views=…, likes=…)` (aceita cair), `tornar_privado(id)`/`tornar_publico(id)`,
  `publicar_rascunho(publish_id, post_id)` (o próximo `status` devolve `PUBLISH_COMPLETE` com
  `publicaly_available_post_id`, mesmo para um `publish_id` que não saiu deste fake) e
  `rascunho_na_caixa(publish_id)` (`SEND_TO_USER_INBOX` para um `publish_id` semeado no banco);
- escopos: um usuário registrado por `usuario(..., escopos=…)` sem `video.list` (ou sem
  `user.info.stats`, ao pedir stats) recebe `scope_not_authorized`; tokens semeados por
  `emitir_tokens` sem usuário registrado leem à vontade. `ESCOPOS_016` tem os 6 escopos.
"""

import copy
import itertools
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from sociman_api.publicacao.tiktok.cliente import TikTokCliente

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tiktok"
UPLOAD_HOST = "open-upload.tiktokapis.com"
AVATAR_URL = "https://p16-sign.tiktokcdn-us.com/fake-avatar.jpeg"
ESCOPOS = "user.info.basic,user.info.profile,video.upload,video.publish"
ESCOPOS_016 = f"{ESCOPOS},user.info.stats,video.list"  # spec 016: com as métricas
CAMPOS_STATS = ("follower_count", "following_count", "likes_count", "video_count")
MAX_VIDEOS = 20
# PNG 1×1 válido (para o avatar).
AVATAR_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d4944415478da63f8cfc0f01f0005000201a5f8b0e10000000049454e44ae426082")

CAMINHOS = {
    ("POST", "/v2/oauth/token/"): "token",
    ("POST", "/v2/oauth/revoke/"): "revoke",
    ("GET", "/v2/user/info/"): "user_info",
    ("POST", "/v2/post/publish/creator_info/query/"): "creator_info",
    ("POST", "/v2/post/publish/inbox/video/init/"): "inbox_init",
    ("POST", "/v2/post/publish/video/init/"): "video_init",
    ("POST", "/v2/post/publish/status/fetch/"): "status",
    ("POST", "/v2/video/list/"): "video_list",  # spec 016
    ("POST", "/v2/video/query/"): "video_query",  # spec 016
}
HTTP_DOS_CODIGOS = {
    "access_token_invalid": 401,
    "scope_not_authorized": 401,
    "rate_limit_exceeded": 429,
    "invalid_params": 400,
    "spam_risk_too_many_pending_share": 403,
    "spam_risk_too_many_posts": 403,
    "spam_risk_user_banned_from_posting": 403,
    "unaudited_client_can_only_post_to_private_accounts": 403,
    "privacy_level_option_mismatch": 400,
    "internal_error": 500,
}


def fixture(nome: str) -> dict[str, Any]:
    return json.loads((FIXTURES / nome).read_text())


def _regra_partes_ok(size: int, chunk: int, total: int) -> bool:
    """Regra da TikTok real (sem os limites de 5–64 MB, para os testes usarem partes pequenas):
    total = floor(size/chunk); com 1 parte, chunk == size (o bug do sandbox em 2026-09-29)."""
    if total == 1:
        return chunk == size
    return total == size // chunk


@dataclass
class Usuario:
    username: str | None
    open_id: str
    display_name: str = "Apelido de teste"
    escopos: str = ESCOPOS
    verifier: str | None = None  # PKCE: o `code_verifier` esperado na troca
    avatar_url: str | None = AVATAR_URL


@dataclass
class Envio:
    publish_id: str
    open_id: str
    direto: bool
    video_size: int
    chunk_size: int
    total_chunk_count: int
    upload_token: str
    post_info: dict[str, Any] | None
    recebidos: int = 0
    partes: list[tuple[int, int]] = field(default_factory=list)
    consultas: int = 0
    fail_reason: str | None = None

    @property
    def completo(self) -> bool:
        return self.recebidos == self.video_size


@dataclass
class VideoFake:
    """Um post da conta `handle` (spec 016)."""

    handle: str
    id: str
    criado_em: datetime
    duracao: int = 30
    legenda: str = ""
    titulo: str = ""
    publico: bool = True
    views: int | None = 0
    likes: int | None = 0
    comments: int | None = 0
    shares: int | None = 0
    largura: int = 1080
    altura: int = 1920

    @property
    def criado_ms(self) -> int:
        return int(self.criado_em.timestamp() * 1000)

    def json(self, campos: list[str]) -> dict[str, Any]:
        completo = {
            "id": int(self.id) if self.id.isdigit() else self.id,
            "create_time": int(self.criado_em.timestamp()),
            "share_url": f"https://www.tiktok.com/@{self.handle}/video/{self.id}",
            "video_description": self.legenda, "title": self.titulo,
            "duration": self.duracao, "width": self.largura, "height": self.altura,
            "view_count": self.views, "like_count": self.likes,
            "comment_count": self.comments, "share_count": self.shares,
            "cover_image_url": "https://p16-sign.tiktokcdn-us.com/capa.jpeg",
            "embed_html": "<blockquote></blockquote>",
        }
        # A TikTok omite o contador que não tem: None aqui = campo ausente.
        return {c: completo[c] for c in campos if c in completo and completo[c] is not None}


class TikTokFake:
    def __init__(self) -> None:
        self.usuarios: dict[str, Usuario] = {}  # code → usuário (o code é de uso único)
        self.por_open_id: dict[str, Usuario] = {}
        self.access: dict[str, str] = {}  # access_token → open_id
        self.refresh: dict[str, str] = {}  # refresh_token válido → open_id
        self.usados: set[str] = set()  # refresh já gastos (rotação)
        self.revogados: list[str] = []  # open_ids revogados
        self.envios: dict[str, Envio] = {}
        self.upload_tokens: dict[str, str] = {}  # upload_token → publish_id
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.passos_status = 2  # consultas em PROCESSING_UPLOAD antes do estado final
        self.expires_in = 86400
        self.refresh_expires_in = 31536000
        self.criador: dict[str, Any] = fixture("creator_info.json")["data"]
        self._falhas: dict[str, list[str]] = {}
        self.falhar_sempre: dict[str, str] = {}
        self.fail_reason_proximo: str | None = None
        # Spec 016: vídeos e stats por conta, e o destino dos rascunhos (publish_id → post_id).
        self.videos: dict[str, VideoFake] = {}
        self.stats: dict[str, dict[str, int]] = {}
        self.rascunhos: dict[str, str | None] = {}
        self._seq = itertools.count(1)
        self.transport = httpx.MockTransport(self._handle)

    # ---- dados ----

    def usuario(self, code: str, username: str | None, *, open_id: str | None = None,
                display_name: str = "Apelido de teste", escopos: str = ESCOPOS,
                verifier: str | None = None, avatar_url: str | None = AVATAR_URL) -> Usuario:
        """O que a TikTok devolve quando o navegador volta com este `code`."""
        u = Usuario(username=username, open_id=open_id or f"open-{username or code}",
                    display_name=display_name, escopos=escopos, verifier=verifier,
                    avatar_url=avatar_url)
        self.usuarios[code] = u
        self.por_open_id[u.open_id] = u
        return u

    def emitir_tokens(self, open_id: str) -> tuple[str, str]:
        """Tokens válidos para um `open_id` (semear credenciais sem passar pelo login)."""
        n = next(self._seq)
        access, refresh = f"act.fake-{n}-{secrets.token_hex(4)}", f"rft.fake-{n}-{secrets.token_hex(4)}"
        self.access[access] = open_id
        self.refresh[refresh] = open_id
        return access, refresh

    def falhar_proximo(self, endpoint: str, falha: str) -> None:
        self._falhas.setdefault(endpoint, []).append(falha)

    def pedidos(self, endpoint: str) -> list[dict[str, Any]]:
        return [d for _, e, d in self.requests if e == endpoint]

    @property
    def inits(self) -> int:
        return len(self.pedidos("inbox_init")) + len(self.pedidos("video_init"))

    def client(self) -> TikTokCliente:
        return TikTokCliente(transport=self.transport)

    # ---- controles da spec 016 ----

    def video(self, handle: str, id: str | int, criado_em: datetime, duracao: int = 30,
              legenda: str = "", publico: bool = True, **extra: Any) -> VideoFake:
        v = VideoFake(handle=handle, id=str(id), criado_em=criado_em, duracao=duracao,
                      legenda=legenda, publico=publico, **extra)
        self.videos[v.id] = v
        return v

    def contadores(self, id: str | int, **valores: int | None) -> None:
        """`views`, `likes`, `comments`, `shares` (podem cair; None = a TikTok omite)."""
        v = self.videos[str(id)]
        for nome, valor in valores.items():
            if nome not in ("views", "likes", "comments", "shares"):
                raise ValueError(nome)
            setattr(v, nome, valor)

    def tornar_privado(self, id: str | int) -> None:
        self.videos[str(id)].publico = False

    def tornar_publico(self, id: str | int) -> None:
        self.videos[str(id)].publico = True

    def seguidores(self, handle: str, n: int, *, seguindo: int = 0, curtidas: int = 0,
                   videos: int | None = None) -> None:
        self.stats[handle] = {"follower_count": n, "following_count": seguindo,
                              "likes_count": curtidas}
        if videos is not None:
            self.stats[handle]["video_count"] = videos

    def rascunho_na_caixa(self, publish_id: str) -> None:
        """Um `publish_id` (semeado no banco) que está na caixa do app: `SEND_TO_USER_INBOX`."""
        self.rascunhos.setdefault(publish_id, None)

    def publicar_rascunho(self, publish_id: str, post_id: str | int) -> None:
        """O dono finalizou o rascunho no app: o `status` passa a `PUBLISH_COMPLETE`."""
        self.rascunhos[publish_id] = str(post_id)

    # ---- respostas ----

    @staticmethod
    def _json(dados: dict[str, Any], status: int = 200) -> httpx.Response:
        return httpx.Response(status, json=dados)

    def _erro(self, codigo: str) -> httpx.Response:
        dados = fixture("error.json")
        dados["error"]["code"] = codigo
        return self._json(dados, HTTP_DOS_CODIGOS.get(codigo, 400))

    def _falha(self, endpoint: str, request: httpx.Request) -> str | None:
        fila = self._falhas.get(endpoint)
        falha = fila.pop(0) if fila else self.falhar_sempre.get(endpoint)
        if falha == "timeout":
            raise httpx.ReadTimeout("fake: sem resposta", request=request)
        if falha == "conexao":
            raise httpx.ConnectError("fake: conexão recusada", request=request)
        return falha

    def _token_de(self, request: httpx.Request) -> str | None:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        return self.access.get(token)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        url = urlsplit(str(request.url))
        if request.method == "PUT" and url.hostname == UPLOAD_HOST:
            return self._put(request, url)
        if request.method == "GET" and (url.hostname or "").endswith("tiktokcdn-us.com"):
            self.requests.append(("GET", "avatar", {}))
            return httpx.Response(200, content=AVATAR_PNG, headers={"content-type": "image/png"})
        endpoint = CAMINHOS.get((request.method, url.path))
        if endpoint is None:
            self.requests.append((request.method, "desconhecido", {"path": url.path}))
            return self._erro("invalid_params")
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()} \
            if endpoint in ("token", "revoke") else {}
        corpo = json.loads(request.content or b"{}") if endpoint not in (
            "token", "revoke", "user_info") else {}
        detalhe: dict[str, Any] = {}
        if endpoint == "token":
            detalhe = {"grant_type": form.get("grant_type"),
                       "pkce": "code_verifier" in form,
                       "redirect_uri": form.get("redirect_uri")}
        elif endpoint in ("inbox_init", "video_init"):
            detalhe = {"post_info": corpo.get("post_info"),
                       "source_info": corpo.get("source_info")}
        elif endpoint == "status":
            detalhe = {"publish_id": corpo.get("publish_id")}
        elif endpoint in ("user_info", "video_list", "video_query"):
            detalhe = {"fields": _campos(url.query)}
            if endpoint == "video_list":
                detalhe.update(cursor=corpo.get("cursor"), max_count=corpo.get("max_count"))
            elif endpoint == "video_query":
                detalhe["ids"] = list((corpo.get("filters") or {}).get("video_ids") or [])
        self.requests.append((request.method, endpoint, detalhe))

        falha = self._falha(endpoint, request)
        if falha == "5xx":
            return httpx.Response(503, json={"error": {"code": "internal_error", "message": ""}})
        if falha and falha != "timeout_depois":
            return self._erro(falha)
        resposta = getattr(self, f"_{endpoint}")(request, form, corpo)
        if falha == "timeout_depois":  # a TikTok processou, a resposta se perdeu
            raise httpx.ReadTimeout("fake: resposta perdida", request=request)
        return resposta

    # ---- OAuth ----

    def _novos_tokens(self, open_id: str, escopos: str) -> httpx.Response:
        access, refresh = self.emitir_tokens(open_id)
        dados = fixture("token.json")
        dados.update(access_token=access, refresh_token=refresh, open_id=open_id, scope=escopos,
                     expires_in=self.expires_in, refresh_expires_in=self.refresh_expires_in)
        return self._json(dados)

    def _token(self, request, form, corpo) -> httpx.Response:
        if form.get("grant_type") == "authorization_code":
            u = self.usuarios.pop(form.get("code", ""), None)
            if u is None or (u.verifier is not None
                             and form.get("code_verifier") != u.verifier):
                return self._json(fixture("token_error.json"), 400)
            return self._novos_tokens(u.open_id, u.escopos)
        if form.get("grant_type") == "refresh_token":
            refresh = form.get("refresh_token", "")
            open_id = self.refresh.pop(refresh, None)
            if open_id is None or open_id in self.revogados:
                return self._json(fixture("token_error.json"), 400)
            self.usados.add(refresh)
            escopos = self._usuario_de(open_id).escopos
            return self._novos_tokens(open_id, escopos)
        return self._json(fixture("token_error.json"), 400)

    def _revoke(self, request, form, corpo) -> httpx.Response:
        open_id = self.access.pop(form.get("token", ""), None)
        if open_id:
            self.revogados.append(open_id)
            self.refresh = {k: v for k, v in self.refresh.items() if v != open_id}
        return self._json({})

    def _usuario_de(self, open_id: str) -> Usuario:
        return self.por_open_id.get(open_id) or Usuario(username=open_id.removeprefix("open-"),
                                                         open_id=open_id)

    def _user_info(self, request, form, corpo) -> httpx.Response:
        open_id = self._token_de(request)
        if open_id is None:
            return self._erro("access_token_invalid")
        u = self._usuario_de(open_id)
        dados = fixture("user_info.json")
        dados["data"]["user"].update(open_id=open_id, username=u.username,
                                     display_name=u.display_name, avatar_url=u.avatar_url)
        if u.username is None:
            dados["data"]["user"].pop("username")
        pedidos = [c for c in _campos(urlsplit(str(request.url)).query) if c in CAMPOS_STATS]
        if pedidos:  # spec 016
            if not self._tem_escopo(open_id, "user.info.stats"):
                return self._erro("scope_not_authorized")
            handle = u.username or ""
            stats = {"follower_count": 0, "following_count": 0, "likes_count": 0,
                     "video_count": sum(1 for v in self.videos.values()
                                        if v.handle == handle and v.publico),
                     **self.stats.get(handle, {})}
            dados["data"]["user"].update({c: stats[c] for c in pedidos})
        return self._json(dados)

    # ---- Display API (spec 016) ----

    def _tem_escopo(self, open_id: str, escopo: str) -> bool:
        u = self.por_open_id.get(open_id)
        return u is None or escopo in u.escopos.split(",")

    def _publicos_de(self, open_id: str) -> list[VideoFake]:
        handle = self._usuario_de(open_id).username or ""
        return sorted((v for v in self.videos.values() if v.handle == handle and v.publico),
                      key=lambda v: (v.criado_ms, int(v.id) if v.id.isdigit() else 0),
                      reverse=True)

    def _video_list(self, request, form, corpo) -> httpx.Response:
        open_id = self._token_de(request)
        if open_id is None:
            return self._erro("access_token_invalid")
        if not self._tem_escopo(open_id, "video.list"):
            return self._erro("scope_not_authorized")
        max_count = int(corpo.get("max_count") or MAX_VIDEOS)
        if not 0 < max_count <= MAX_VIDEOS:
            return self._erro("invalid_params")
        cursor = corpo.get("cursor")
        videos = [v for v in self._publicos_de(open_id)
                  if cursor is None or v.criado_ms < int(cursor)]
        pagina = videos[:max_count]
        campos = _campos(urlsplit(str(request.url)).query)
        dados = fixture("video_list.json")
        dados["data"] = {"videos": [v.json(campos) for v in pagina],
                         "cursor": pagina[-1].criado_ms if pagina else (cursor or 0),
                         "has_more": len(videos) > len(pagina)}
        return self._json(dados)

    def _video_query(self, request, form, corpo) -> httpx.Response:
        open_id = self._token_de(request)
        if open_id is None:
            return self._erro("access_token_invalid")
        if not self._tem_escopo(open_id, "video.list"):
            return self._erro("scope_not_authorized")
        ids = [str(i) for i in (corpo.get("filters") or {}).get("video_ids") or []]
        if not 0 < len(ids) <= MAX_VIDEOS:
            return self._erro("invalid_params")
        meus = {v.id: v for v in self._publicos_de(open_id)}  # só os da conta do token
        campos = _campos(urlsplit(str(request.url)).query)
        dados = fixture("video_query.json")
        dados["data"] = {"videos": [meus[i].json(campos) for i in ids if i in meus]}
        return self._json(dados)

    # ---- Content Posting ----

    def _creator_info(self, request, form, corpo) -> httpx.Response:
        open_id = self._token_de(request)
        if open_id is None:
            return self._erro("access_token_invalid")
        u = self._usuario_de(open_id)
        dados = fixture("creator_info.json")
        dados["data"] = copy.deepcopy(self.criador)
        dados["data"]["creator_username"] = u.username or ""
        dados["data"]["creator_nickname"] = u.display_name
        return self._json(dados)

    def _init(self, request, corpo, direto: bool) -> httpx.Response:
        open_id = self._token_de(request)
        if open_id is None:
            return self._erro("access_token_invalid")
        fonte = corpo.get("source_info") or {}
        size, chunk = int(fonte.get("video_size", 0)), int(fonte.get("chunk_size", 0))
        total = int(fonte.get("total_chunk_count", 0))
        if fonte.get("source") != "FILE_UPLOAD" or size <= 0 or chunk <= 0 or total <= 0 \
                or (not direto and "post_info" in corpo) \
                or not _regra_partes_ok(size, chunk, total):
            return self._erro("invalid_params")
        n = next(self._seq)
        publish_id = f"v_{'pub' if direto else 'inbox'}_file~v2.{n}"
        upload_token = f"upl-{n}-{secrets.token_hex(4)}"
        self.envios[publish_id] = Envio(publish_id, open_id, direto, size, chunk, total,
                                        upload_token, corpo.get("post_info"))
        self.upload_tokens[upload_token] = publish_id
        dados = fixture("init.json")
        dados["data"] = {"publish_id": publish_id, "upload_url":
                         f"https://{UPLOAD_HOST}/upload/?upload_id={n}&upload_token={upload_token}"}
        return self._json(dados)

    def _inbox_init(self, request, form, corpo) -> httpx.Response:
        return self._init(request, corpo, direto=False)

    def _video_init(self, request, form, corpo) -> httpx.Response:
        return self._init(request, corpo, direto=True)

    def _put(self, request: httpx.Request, url) -> httpx.Response:
        token = parse_qs(url.query).get("upload_token", [""])[0]
        faixa = request.headers.get("content-range", "")
        self.requests.append(("PUT", "put", {"content_range": faixa}))
        falha = self._falha("put", request)
        if falha == "5xx":
            return httpx.Response(503)
        if falha:
            return httpx.Response(400)
        envio = self.envios.get(self.upload_tokens.get(token, ""))
        if envio is None:
            return httpx.Response(404)
        try:
            unidade, resto = faixa.split(" ", 1)
            intervalo, total = resto.split("/")
            inicio, fim = (int(x) for x in intervalo.split("-"))
        except ValueError:
            return httpx.Response(400)
        corpo = request.content
        if unidade != "bytes" or int(total) != envio.video_size \
                or fim - inicio + 1 != len(corpo) or fim >= envio.video_size:
            return httpx.Response(416)
        if inicio == envio.recebidos:  # na ordem
            envio.recebidos = fim + 1
            envio.partes.append((inicio, fim))
        elif (inicio, fim) in envio.partes:  # a mesma parte de novo: repetível
            pass
        else:
            return httpx.Response(416)
        return httpx.Response(201 if envio.completo else 206)

    def _status(self, request, form, corpo) -> httpx.Response:
        if self._token_de(request) is None:
            return self._erro("access_token_invalid")
        publish_id = corpo.get("publish_id", "")
        dados = fixture("status.json")
        if publish_id in self.rascunhos:  # spec 016: o dono finalizou (ou não) no app
            post_id = self.rascunhos[publish_id]
            if post_id is None:
                dados["data"].update(status="SEND_TO_USER_INBOX")
            else:
                dados["data"].update(status="PUBLISH_COMPLETE", publicaly_available_post_id=[
                    int(post_id) if post_id.isdigit() else post_id])
            return self._json(dados)
        envio = self.envios.get(publish_id)
        if envio is None:
            return self._erro("invalid_params")
        envio.consultas += 1
        if self.fail_reason_proximo and envio.completo:
            envio.fail_reason, self.fail_reason_proximo = self.fail_reason_proximo, None
        if envio.fail_reason:
            dados["data"].update(status="FAILED", fail_reason=envio.fail_reason)
        elif not envio.completo or envio.consultas <= self.passos_status:
            dados["data"].update(status="PROCESSING_UPLOAD", uploaded_bytes=envio.recebidos)
        elif envio.direto:
            dados["data"].update(status="PUBLISH_COMPLETE", uploaded_bytes=envio.recebidos,
                                 publicaly_available_post_id=[7_000_000_000_000_000_000 + 1])
        else:
            dados["data"].update(status="SEND_TO_USER_INBOX", uploaded_bytes=envio.recebidos)
        return self._json(dados)


def _campos(query: str) -> list[str]:
    """O `fields` da query string (spec 016), na ordem pedida."""
    valor = parse_qs(query).get("fields", [""])[0]
    return [c for c in valor.split(",") if c]
