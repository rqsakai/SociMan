"""Executor da TikTok (research R20 da spec 015): o `ExecutorRede` da rede `tiktok`.

- rascunho: `inbox/video/init` com `FILE_UPLOAD` e **sem `post_info`** (a API do inbox não
  recebe textos, R13); `spam_risk_too_many_pending_share` → `SemVaga` (espera de 1 h, R10);
- publicar: `video/init` com o `post_info` montado **só do snapshot** que o dono confirmou;
- partes: `PUT upload_url` com `Content-Range` e `Content-Type: video/mp4`, até 3 tentativas por
  parte (recuo 1, 4, 16 s); a trilha lê do MinIO e grava cada parte enviada;
- status: `SEND_TO_USER_INBOX` → `Entregue`, `PUBLISH_COMPLETE` → `Publicado`, `FAILED` →
  `Recusado` (com o `fail_reason` traduzido), o resto → `EmAndamento`.

A taxa por token (R10) e a máquina de estados ficam na trilha. O OAuth fica em
`publicacao/tiktok/oauth.py` e é exposto por `oauth` (a parte genérica nunca importa este pacote;
chega aqui por `publicacao/registro.py`). Nada aqui registra token nem `upload_url`.
"""

import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import TYPE_CHECKING, Any

import httpx

from sociman_api.conteudos.models import Modo
from sociman_api.perfis.models import Platform
from sociman_api.publicacao.executor import (
    Contexto,
    EmAndamento,
    Entregue,
    Iniciado,
    Motivo,
    Publicado,
    Recusado,
    SemVaga,
)
from sociman_api.publicacao.tiktok import cliente, erros

if TYPE_CHECKING:
    from sociman_api.publicacao.models import Tentativa

INIT_INBOX = "/v2/post/publish/inbox/video/init/"
INIT_DIRETO = "/v2/post/publish/video/init/"
STATUS = "/v2/post/publish/status/fetch/"
RECUOS_PARTE = (1.0, 4.0, 16.0)
SEM_VAGA = "spam_risk_too_many_pending_share"
TAXA = "rate_limit_exceeded"
ADIAR_S = 60
ESPERA_SEM_VAGA = timedelta(hours=1)
NA_CAIXA = "SEND_TO_USER_INBOX"
PUBLICADO = "PUBLISH_COMPLETE"
FALHOU = "FAILED"


def _recusado(codigo: str, adiar_s: int | None = None) -> Recusado:
    m = erros.traduzir(codigo)
    return Recusado(codigo, m.motivo, m.acao.value, adiar_s)


def source_info(video_bytes: int, chunk_size: int, total_partes: int) -> dict[str, Any]:
    return {"source": "FILE_UPLOAD", "video_size": video_bytes, "chunk_size": chunk_size,
            "total_chunk_count": total_partes}


def post_info(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """O `post_info` do Direct Post, só com o que o dono confirmou (R13): nunca os textos vivos
    do destino nem um valor escolhido aqui."""
    opcoes = snapshot["opcoes"]
    comercial = opcoes.get("comercial", "nenhum")
    return {
        "title": snapshot.get("legenda", ""),
        "privacy_level": opcoes["privacidade"],
        "disable_comment": not opcoes["permitirComentario"],
        "disable_duet": not opcoes["permitirDueto"],
        "disable_stitch": not opcoes["permitirCostura"],
        "brand_organic_toggle": comercial == "sua_marca",
        "brand_content_toggle": comercial == "parceria_paga",
        "is_aigc": bool(opcoes.get("conteudoIa", False)),
    }


class TikTokExecutor:
    rede = Platform.tiktok
    modos = frozenset({Modo.criar_rascunho, Modo.publicar})
    escopos_por_modo: Mapping[Modo, str] = {
        Modo.criar_rascunho: "video.upload",
        Modo.publicar: "video.publish",
    }

    @property
    def oauth(self) -> ModuleType:
        from sociman_api.publicacao.tiktok import oauth

        return oauth

    def novo_cliente(self, transport: httpx.BaseTransport | None = None
                     ) -> cliente.TikTokCliente:
        return cliente.get_tiktok_client(transport)

    # Recuo entre as tentativas de uma parte (s); os testes trocam por zeros.
    recuos_parte: tuple[float, ...] = RECUOS_PARTE

    def iniciar(self, ctx: Contexto, tentativa: "Tentativa",
                snapshot: Mapping[str, Any] | None) -> Iniciado | SemVaga | Recusado:
        """O `init`, o único passo que cria algo na TikTok. `SemResposta` sobe para a trilha
        (fase `incerta`); `ConexaoIndisponivel` também (nada foi criado)."""
        corpo: dict[str, Any] = {"source_info": source_info(
            tentativa.video_bytes, tentativa.chunk_size, tentativa.total_partes)}
        if tentativa.modo == Modo.criar_rascunho:
            caminho = INIT_INBOX  # nunca com `post_info`
        elif tentativa.modo == Modo.publicar:
            if not snapshot or not snapshot.get("opcoes"):
                return _recusado("sem_snapshot")
            caminho = INIT_DIRETO
            corpo["post_info"] = post_info(snapshot)
        else:
            raise ValueError(f"modo sem execução na TikTok: {tentativa.modo}")
        try:
            dados = ctx.client.api("POST", caminho, token=ctx.token(), json=corpo)
        except cliente.RecusaRede as e:
            if e.codigo == SEM_VAGA:
                return SemVaga(e.codigo, erros.traduzir(e.codigo).motivo,
                               datetime.now(UTC) + ESPERA_SEM_VAGA)
            return _recusado(e.codigo, ADIAR_S if e.codigo == TAXA else None)
        data = dados.get("data") or {}
        publish_id, upload_url = data.get("publish_id"), data.get("upload_url")
        if not publish_id or not upload_url:
            # Resposta sem o id: não dá para saber se a TikTok criou algo.
            raise cliente.SemResposta("init sem publish_id ou upload_url")
        return Iniciado(publish_id=str(publish_id), upload_url=str(upload_url))

    def enviar_parte(self, ctx: Contexto, tentativa: "Tentativa", upload_url: str,
                     indice: int, inicio: int, dados: bytes) -> Recusado | None:
        """PUT da parte `indice` (0-based) a partir do byte `inicio`. Repete até 3 vezes em
        falha de rede ou 5xx (a última falha sobe: a trilha reenvia na próxima volta); uma
        recusa (4xx) volta como `Recusado`."""
        for n, recuo in enumerate((0.0, *self.recuos_parte)):
            if recuo:
                time.sleep(recuo)
            try:
                ctx.client.put_parte(upload_url, dados, inicio, tentativa.video_bytes)
                return None
            except cliente.RecusaRede as e:
                return _recusado(e.codigo)
            except (cliente.ConexaoIndisponivel, cliente.SemResposta):
                if n == len(self.recuos_parte):
                    raise
        return None  # pragma: no cover

    def consultar(self, ctx: Contexto, tentativa: "Tentativa"
                  ) -> EmAndamento | Entregue | Publicado | Recusado:
        # Uma recusa do próprio pedido de status (token, taxa) sobe: o vídeo já foi entregue,
        # e a trilha consulta de novo até o prazo (depois, `incerta`).
        dados = ctx.client.api("POST", STATUS, token=ctx.token(),
                                json={"publish_id": tentativa.publish_id})
        data = dados.get("data") or {}
        status = str(data.get("status") or "")
        if status == FALHOU:
            codigo = str(data.get("fail_reason") or "falhou_sem_motivo")
            return _recusado(codigo)
        if tentativa.modo == Modo.criar_rascunho and status in (NA_CAIXA, PUBLICADO):
            return Entregue(status)
        if tentativa.modo == Modo.publicar and status == PUBLICADO:
            ids = data.get("publicaly_available_post_id") or []  # grafia da API
            return Publicado(status, str(ids[0]) if isinstance(ids, list) and ids else None)
        return EmAndamento(status, {"uploadedBytes": data.get("uploaded_bytes")})

    def validar_opcoes(self, opcoes: Any, criador: Any, duracao_s: float | None = None
                       ) -> Sequence[Any]:
        """Regras da tela obrigatória (R13, `opcoes.py`): `opcoes` é o `OpcoesTikTok` ou o
        dict do snapshot; `criador`, o `consultar_criador` (ou None, sem consulta)."""
        from sociman_api.config import get_settings
        from sociman_api.publicacao.schemas import OpcoesTikTok
        from sociman_api.publicacao.tiktok import opcoes as regras

        if not isinstance(opcoes, OpcoesTikTok):
            opcoes = OpcoesTikTok.model_validate(opcoes)
        return regras.validar(opcoes, criador, get_settings().tiktok_app_situacao, duracao_s)

    def consultar_criador(self, ctx: Contexto) -> Any:
        """`creator_info` na hora (R13) → `opcoes.Criador`. Uma recusa de "não pode postar
        agora" (spam_risk_*, limite de usuários) vira `pode_postar = False`."""
        from sociman_api.publicacao.executor import RecusaRede
        from sociman_api.publicacao.tiktok import oauth
        from sociman_api.publicacao.tiktok.opcoes import Criador

        try:
            d = oauth.consultar_criador(ctx.client, ctx.token())
        except RecusaRede as e:
            if not (e.codigo.startswith("spam_risk") or e.codigo == "reached_active_user_cap"):
                raise
            return Criador(username="", display_name="", privacidades=(),
                           comentario_desligado=True, dueto_desligado=True,
                           costura_desligada=True, duracao_maxima_s=0, pode_postar=False)
        return Criador(
            username=str(d.get("creator_username") or "").lstrip("@"),
            display_name=str(d.get("creator_nickname") or ""),
            privacidades=tuple(d.get("privacy_level_options") or ()),
            comentario_desligado=bool(d.get("comment_disabled")),
            dueto_desligado=bool(d.get("duet_disabled")),
            costura_desligada=bool(d.get("stitch_disabled")),
            duracao_maxima_s=int(d.get("max_video_post_duration_sec") or 0),
            avatar_url=d.get("creator_avatar_url") or None)

    def traduzir(self, codigo: str | None) -> Motivo:
        return erros.traduzir(codigo)
