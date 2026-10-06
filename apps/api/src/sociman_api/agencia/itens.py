"""Itens da pré-visualização (research R4): tipo, origem, chave de conciliação e situação.

Um item é um pedaço de arquivo (seção, linha de tabela, imagem, vídeo) ligado a uma entidade de
destino. A `chave` é estável por tipo (idempotência sem tabela de "de-para"); a `impressao` é o
SHA-256 do conteúdo normalizado do item (detecta trecho alterado). `dados` é o valor proposto
no formato do aplicador; `atual` e `proposto` são só o que a tela compara.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

TIPOS = ("perfil", "conta", "guia", "anotacao", "canal", "vinculo_canal", "imagem_logo", "asset",
         "arquivo_asset", "clipe", "sugestao_bordao")
SITUACOES = ("novo", "igual", "diverge", "fora", "aguardando_cota", "sugestao")
RESULTADOS = ("criado", "atualizado", "mantido", "igual", "fora", "nao_gravado", "sugestao")

# Motivos (código → texto da tela). Os de "fora" do mapeamento estão em `mapa.MOTIVOS`.
MOTIVOS: dict[str, str] = {
    # diverge
    "valor": "o valor no SociMan é diferente do markdown",
    "direito": "o status de direito no SociMan é diferente do mapeado do markdown",
    "editado": "já foi editado no SociMan",
    "arquivado": "está arquivado no SociMan (a importação não restaura)",
    # fora
    "sem_perfil_md": "sem perfil.md",
    "slug_em_uso": "o identificador (slug) já é de outro perfil",
    "status_desconhecido": "status do perfil desconhecido",
    "idioma_invalido": "idioma fora do padrão (ex.: pt-BR)",
    "handle_invalido": "@ inválido",
    "conta_de_outro_perfil": "o @ já é de outro perfil",
    "conta_arquivada": "a conta está arquivada no SociMan",
    "perfil_fora": "o perfil deste item não entra nesta importação",
    "sem_canal_youtube": "sem canal do YouTube identificável",
    "conteudo_proprio": "material original próprio: use o envio avulso (não é canal-fonte)",
    "canal_nao_encontrado": "o YouTube não achou este canal",
    "youtube_indisponivel": "não foi possível consultar o YouTube",
    "imagem_invalida": "imagem inválida",
    "arquivo_grande": "arquivo acima do limite",
    "arquivo_citado_nao_encontrado": "arquivo citado não encontrado",
    "linha_sem_video": "linha do registro sem o vídeo",
    "video_sem_linha": "vídeo sem linha no registro",
    "video_invalido": "vídeo inválido",
    "caminho_de_clipe": "caminho fora do formato <perfil>/<AAAA-MM-DD>/<id>.mp4",
    "sem_perfil_persona": "escolha o perfil da persona",
    "data_invalida": "data inválida",
    "nao_reconhecido": "arquivo não reconhecido",
    # aguardando cota
    "cota": "cota do YouTube esgotada: leia de novo depois que ela renovar",
    # resultados
    "mudou_desde_a_leitura": "o arquivo mudou desde a leitura; leia de novo",
    "editado_desde_a_leitura": "mudou no SociMan desde a leitura; leia de novo",
    "perfil_nao_importado": "o perfil deste item não foi importado",
    "dono_inativo": "o dono que confirmou não está mais ativo",
    "interrompida": "a importação foi interrompida (a API reiniciou no meio)",
    "em_uso": "já usado (não desfeito)",
    "editado_depois": "alterado depois da importação (não desfeito)",
}

TEXTO_MAX = 4000  # anotação (009)
TRECHO_MAX = 300  # texto longo na resposta da prévia


def impressao(valor: Any) -> str:
    """SHA-256 do JSON canônico do conteúdo do item."""
    bruto = json.dumps(valor, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(bruto.encode()).hexdigest()


def motivo_texto(codigo: str | None) -> str | None:
    if codigo is None:
        return None
    from sociman_api.agencia.mapa import MOTIVOS as MOTIVOS_MAPA

    return MOTIVOS.get(codigo) or MOTIVOS_MAPA.get(codigo) or codigo


def cortar(texto: str, limite: int = TRECHO_MAX) -> tuple[str, bool]:
    return (texto, False) if len(texto) <= limite else (texto[: limite - 1] + "…", True)


@dataclass
class Item:
    tipo: str
    perfil_slug: str | None
    arquivo: str  # `shared:…` ou `clipes:…`
    trecho: str
    chave: str
    situacao: str
    linha: int | None = None
    impressao: str = ""
    motivo: str | None = None
    dados: dict[str, Any] = field(default_factory=dict)  # valor proposto (aplicador)
    atual: dict[str, Any] | None = None  # o que a tela compara
    proposto: dict[str, Any] | None = None
    bytes: int | None = None
    base: dict[str, int] = field(default_factory=dict)  # "<entity_type>:<id>" → version lida
    origens: list[dict[str, Any]] = field(default_factory=list)  # outras linhas (canal)
    direitos_aceitos: list[str] | None = None
    direito_proposto: str | None = None
    exige_perfil: bool = False  # persona sem perfil padrão
    n: int = 0

    def json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_json(cls, d: dict[str, Any]) -> "Item":
        return cls(**d)

    @property
    def escolhivel(self) -> bool:
        return self.situacao == "novo" or (self.situacao == "diverge"
                                           and self.motivo != "arquivado")
