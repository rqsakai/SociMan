"""Regras da tela obrigatória do Direct Post da TikTok (research R13, FR-008).

Usadas em dois momentos, com as mesmas regras:
- ao **agendar** em `publicar` (400 `opcoes_invalidas` com `details.problemas`);
- no **horário**, contra o `creator_info` consultado de novo: um problema vira tentativa
  `recusada` com o motivo, sem trocar a escolha do humano.

Nada aqui escolhe valor por conta própria: privacidade e toggles vêm do dono.
"""

from dataclasses import dataclass, field

from sociman_api.publicacao.executor import Problema
from sociman_api.publicacao.schemas import OpcoesTikTok

TEXTO_MUSICA = "Confirmação de Uso de Música"
TEXTO_MARCA = "Política de Conteúdo de Marca"
CONSENTIMENTO = f"Ao postar, você concorda com a {TEXTO_MUSICA} da TikTok."
CONSENTIMENTO_PARCERIA = (f"Ao postar, você concorda com a {TEXTO_MARCA} e com a "
                          f"{TEXTO_MUSICA} da TikTok.")
SO_VOCE = "SELF_ONLY"


@dataclass(frozen=True)
class Criador:
    """`creator_info` na hora (R13): o que a tela obrigatória do Publicar mostra."""

    username: str
    display_name: str
    privacidades: tuple[str, ...]
    comentario_desligado: bool
    dueto_desligado: bool
    costura_desligada: bool
    duracao_maxima_s: int
    pode_postar: bool = True
    avatar_url: str | None = field(default=None, repr=False)  # link da CDN (expira)


def texto_consentimento(comercial: str) -> str:
    """A frase que a tela mostra (e que o dono aceita) para a divulgação escolhida."""
    return CONSENTIMENTO_PARCERIA if comercial == "parceria_paga" else CONSENTIMENTO


def validar(opcoes: OpcoesTikTok, criador: Criador | None, situacao_app: str,
            duracao_s: float | None = None) -> list[Problema]:
    """Problemas da escolha do dono; lista vazia = pode seguir.

    Sem `criador` (não consultado), valem só as regras que não dependem da conta.
    """
    problemas: list[Problema] = []

    if situacao_app == "sandbox" and opcoes.privacidade != SO_VOCE:
        problemas.append(Problema(
            "privacidade", "Sem auditoria da TikTok, só dá para publicar como \"só você\""))
    if opcoes.comercial == "parceria_paga" and opcoes.privacidade == SO_VOCE:
        problemas.append(Problema(
            "comercial", "Parceria paga não pode ser publicada como \"só você\""))

    texto = opcoes.consentimento.texto
    if TEXTO_MUSICA not in texto:
        problemas.append(Problema(
            "consentimento", "Aceite a Confirmação de Uso de Música da TikTok"))
    if opcoes.comercial == "parceria_paga" and TEXTO_MARCA not in texto:
        problemas.append(Problema(
            "consentimento", "Com parceria paga, aceite também a Política de Conteúdo de Marca"))

    if criador is None:
        return problemas

    if not criador.pode_postar:
        problemas.append(Problema(
            "conta", "A TikTok não deixa esta conta postar agora; tente mais tarde"))
    if opcoes.privacidade not in criador.privacidades:
        problemas.append(Problema(
            "privacidade", "A privacidade escolhida não está disponível para esta conta"))
    for campo, ligado, desligado, nome in (
        ("permitirComentario", opcoes.permitir_comentario, criador.comentario_desligado,
         "comentários"),
        ("permitirDueto", opcoes.permitir_dueto, criador.dueto_desligado, "duetos"),
        ("permitirCostura", opcoes.permitir_costura, criador.costura_desligada, "costuras"),
    ):
        if ligado and desligado:
            problemas.append(Problema(campo, f"A conta desligou {nome} no app da TikTok"))
    if duracao_s is not None and criador.duracao_maxima_s and \
            duracao_s > criador.duracao_maxima_s:
        problemas.append(Problema(
            "video", f"O vídeo passa do máximo da conta ({criador.duracao_maxima_s} s)"))
    return problemas
