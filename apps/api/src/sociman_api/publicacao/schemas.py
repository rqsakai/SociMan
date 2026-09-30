"""Modelos Pydantic da publicação (contracts/http-api.md da 015). JSON em camelCase.

Nenhum schema aqui tem campo de token, código, verifier ou `upload_url` (princípio V): os
segredos só existem decifrados em variáveis locais de `publicacao/`.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from sociman_api.auth.schemas import CamelModel
from sociman_api.conteudos.models import Modo
from sociman_api.perfis.models import Platform
from sociman_api.perfis.schemas import UserRef, VersionNumber

ConexaoEstadoOut = Literal["nao_conectada", "conectada", "precisa_reconectar"]
Privacidade = Literal["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR",
                      "SELF_ONLY"]
SituacaoApp = Literal["sandbox", "auditado"]
TentativaFaseOut = Literal["iniciando", "enviando_partes", "processando", "entregue",
                           "publicada", "recusada", "incerta", "sem_vaga"]
Comercial = Literal["nenhum", "sua_marca", "parceria_paga"]

# Os valores vêm da URL de retorno da TikTok; os limites só barram lixo.
_Param = Annotated[str, StringConstraints(min_length=1, max_length=2000)]


# ---- conexão ----

class ModoInfo(CamelModel):
    """Um modo de agendamento da conta (014) + `aviso` (015, R12). `postagem.schemas` reexporta
    este schema (um só no OpenAPI; e `publicacao` não importa `postagem`, sem ciclo)."""

    modo: Modo
    disponivel: bool
    motivo: str | None  # pt-BR; null quando disponível
    aviso: str | None = None  # alerta que não bloqueia (ex.: publicar no sandbox)


class Conexao(CamelModel):
    conta_id: UUID
    rede: Platform
    estado: ConexaoEstadoOut
    username: str | None
    display_name: str | None
    avatar_url: str | None  # via /img (imgproxy); nunca a CDN da TikTok
    escopos: list[str]
    conectado_por: UserRef | None
    conectado_em: datetime | None
    motivo: str | None
    refresh_expira_em: datetime | None
    modos: list[ModoInfo]  # os mesmos de GET /contas/{id}/modos
    version: int | None  # da conexão viva (para desconectar); null sem conexão


class ConexaoOut(CamelModel):
    conexao: Conexao


class DesconectarOut(CamelModel):
    conexao: Conexao
    agendamentos_em_atencao: int  # destinos automáticos agendados que ficaram em atenção


class IniciarOut(CamelModel):
    autorizar_url: str
    expira_em: datetime


class RetornoIn(CamelModel):
    state: _Param
    code: _Param | None = None
    error: _Param | None = None
    error_description: _Param | None = None


class RetornoOut(CamelModel):
    conexao: Conexao
    conta_id: UUID
    perfil_id: UUID


# ---- Publicar (US3): tela obrigatória da TikTok ----

class Criador(CamelModel):
    username: str
    display_name: str
    avatar_url: str | None
    pode_postar: bool
    privacy_level_options: list[Privacidade]
    comentario_desligado: bool
    dueto_desligado: bool
    costura_desligada: bool
    duracao_maxima_s: int
    situacao_app: SituacaoApp


class CriadorOut(CamelModel):
    criador: Criador


class Consentimento(CamelModel):
    texto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                            max_length=1000)]
    aceito_em: datetime


class OpcoesTikTok(CamelModel):
    """O que o dono escolheu na tela obrigatória (research R13). Sem valores padrão onde a
    TikTok exige escolha: privacidade e os três toggles."""

    privacidade: Privacidade
    permitir_comentario: bool
    permitir_dueto: bool
    permitir_costura: bool
    comercial: Comercial = "nenhum"
    conteudo_ia: bool = False
    consentimento: Consentimento


# ---- interruptor ----

class EnderecosLogin(CamelModel):
    web: str | None
    desktop: str | None


class PublicacaoConfig(CamelModel):
    servidor_habilitado: bool  # PUBLICACAO_HABILITADA (só leitura)
    envios_habilitados: bool  # o botão "Envios automáticos"
    tokens_configurados: bool
    app_configurado: bool
    situacao_app: SituacaoApp
    enderecos_login: EnderecosLogin
    vencidos: int
    em_andamento: int
    version: int


class PublicacaoConfigOut(CamelModel):
    config: PublicacaoConfig


class PublicacaoConfigIn(CamelModel):
    version: VersionNumber
    envios_habilitados: bool


# ---- tentativas ----

class VideoEnviado(CamelModel):
    ref: str
    bytes: int
    sha256: str | None


class Tentativa(CamelModel):
    id: UUID
    numero: int
    modo: Modo
    fase: TentativaFaseOut
    disparo: str  # agendador | tentar_de_novo | confirmado
    disparado_por: UserRef | None
    iniciada_em: datetime
    concluida_em: datetime | None
    publish_id: str | None
    status_rede: str | None
    codigo_rede: str | None
    motivo: str | None
    acao: str | None
    rede_post_id: str | None
    partes_enviadas: int
    total_partes: int
    video: VideoEnviado


class TentativasList(CamelModel):
    items: list[Tentativa]  # mais nova primeiro


class TentarDeNovoIn(CamelModel):
    version: VersionNumber
    confirmo_que_nao_chegou: bool = Field(False, description=(
        "Obrigatório quando a última falha foi incerta: o dono conferiu no app e o rascunho "
        "não chegou (Clarifications Q4)"))
