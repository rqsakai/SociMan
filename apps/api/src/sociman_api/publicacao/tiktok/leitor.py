"""Leitor da TikTok (spec 016, research R2): o `LeitorRede` da rede `tiktok`. **Só lê.**

Quatro pedidos, todos pelo cliente com a lista fechada (`cliente.ALLOWED`):
- `stats_conta`: `GET /v2/user/info/` com os campos de stats;
- `listar`: `POST /v2/video/list/` (cursor em ms, até 20 por página);
- `consultar`: `POST /v2/video/query/` com até 20 ids;
- `post_publicado`: `POST /v2/post/publish/status/fetch/` (o `publicaly_available_post_id`).

Não pede `cover_image_url` (expira em 6 h) nem `embed_html`. O id do vídeo é sempre texto.
`scope_not_authorized` (e `access_token_invalid` na lista e na consulta) vira
`SemPermissaoLeitura`, sem mexer na conexão (R1). Nada aqui registra legenda, link nem token (o
cliente registra só método, caminho e status).
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sociman_api.perfis.models import Platform
from sociman_api.publicacao.executor import (
    Contexto,
    Falhou,
    Pendente,
    PostId,
    RecusaRede,
    SemPermissaoLeitura,
    StatsConta,
    VideoLido,
)

USER_INFO = "/v2/user/info/"
VIDEO_LIST = "/v2/video/list/"
VIDEO_QUERY = "/v2/video/query/"
STATUS = "/v2/post/publish/status/fetch/"
CAMPOS_CONTA = "open_id,follower_count,following_count,likes_count,video_count"
CAMPOS_VIDEO = ("id,create_time,share_url,video_description,title,duration,width,height,"
                "view_count,like_count,comment_count,share_count")
MAX_IDS = 20
SEM_ESCOPO = "scope_not_authorized"
TOKEN_INVALIDO = "access_token_invalid"
PUBLICADO = "PUBLISH_COMPLETE"
FALHOU = "FAILED"


def _int(valor: Any) -> int | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _texto(valor: Any) -> str | None:
    return str(valor) if valor not in (None, "") else None


def video_lido(v: Mapping[str, Any]) -> VideoLido:
    criado = _int(v.get("create_time")) or 0
    return VideoLido(
        id=str(v["id"]),
        criado_em=datetime.fromtimestamp(criado, UTC),
        url=_texto(v.get("share_url")),
        legenda=_texto(v.get("video_description")),
        titulo=_texto(v.get("title")),
        duracao_s=_int(v.get("duration")) or 0,
        largura=_int(v.get("width")),
        altura=_int(v.get("height")),
        views=_int(v.get("view_count")),
        likes=_int(v.get("like_count")),
        comments=_int(v.get("comment_count")),
        shares=_int(v.get("share_count")),
    )


class LeitorTikTok:
    rede = Platform.tiktok

    def _ler(self, ctx: Contexto, metodo: str, caminho: str, *, token_e_escopo: bool,
             **kw: Any) -> dict[str, Any]:
        try:
            return ctx.client.api(metodo, caminho, token=ctx.token(), **kw)
        except RecusaRede as e:
            if e.codigo == SEM_ESCOPO or (token_e_escopo and e.codigo == TOKEN_INVALIDO):
                raise SemPermissaoLeitura(e.codigo, "", e.status, e.log_id) from None
            raise

    def stats_conta(self, ctx: Contexto) -> StatsConta:
        dados = self._ler(ctx, "GET", USER_INFO, token_e_escopo=False,
                          params={"fields": CAMPOS_CONTA})
        u = (dados.get("data") or {}).get("user") or {}
        return StatsConta(seguidores=_int(u.get("follower_count")),
                          seguindo=_int(u.get("following_count")),
                          curtidas=_int(u.get("likes_count")),
                          videos=_int(u.get("video_count")))

    def listar(self, ctx: Contexto, cursor: int | None = None, max_count: int = MAX_IDS
               ) -> tuple[list[VideoLido], int | None, bool]:
        corpo: dict[str, Any] = {"max_count": min(max_count, MAX_IDS)}
        if cursor is not None:
            corpo["cursor"] = cursor
        dados = self._ler(ctx, "POST", VIDEO_LIST, token_e_escopo=True,
                          params={"fields": CAMPOS_VIDEO}, json=corpo)
        data = dados.get("data") or {}
        videos = [video_lido(v) for v in data.get("videos") or [] if v.get("id") is not None]
        return videos, _int(data.get("cursor")), bool(data.get("has_more"))

    def consultar(self, ctx: Contexto, ids: Sequence[str]) -> list[VideoLido]:
        ids = [str(i) for i in ids]
        if not ids:
            return []
        if len(ids) > MAX_IDS:
            raise ValueError(f"video/query aceita até {MAX_IDS} ids")
        dados = self._ler(ctx, "POST", VIDEO_QUERY, token_e_escopo=True,
                          params={"fields": CAMPOS_VIDEO},
                          json={"filters": {"video_ids": ids}})
        data = dados.get("data") or {}
        return [video_lido(v) for v in data.get("videos") or [] if v.get("id") is not None]

    def post_publicado(self, ctx: Contexto, publish_id: str) -> PostId | Pendente | Falhou:
        dados = self._ler(ctx, "POST", STATUS, token_e_escopo=False,
                          json={"publish_id": publish_id})
        data = dados.get("data") or {}
        status = str(data.get("status") or "")
        if status == FALHOU:
            return Falhou(str(data.get("fail_reason") or "falhou_sem_motivo"))
        ids = data.get("publicaly_available_post_id") or []  # grafia da API
        if status == PUBLICADO and isinstance(ids, list) and ids:
            return PostId(str(ids[0]))
        return Pendente(status)
