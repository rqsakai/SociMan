"""Códigos da TikTok → motivo em pt-BR e ação possível (research R19 da spec 015, SC-006).

Vale para o `error.code` do `init` e para o `fail_reason` do `status/fetch`. O código cru fica
em `publicacao_tentativas.codigo_rede`; a tela mostra o `motivo` e oferece a `acao` (código
curto, com rótulo no SPA). Código desconhecido cai no fallback "A TikTok recusou o envio
(código X)" com **Tentar de novo**. As situações do próprio SociMan (sem resposta, link
expirado, vídeo mudou) ficam em `publicacao/executor.py`, que a trilha pode importar.
"""

from sociman_api.publicacao.executor import Acao, Motivo

_FORA_DAS_REGRAS = "O vídeo está fora das regras da TikTok"
_AUTORIZACAO = Motivo("A autorização da conta não vale mais; reconecte a conta",
                      Acao.reconectar)

MOTIVOS: dict[str, Motivo] = {
    # limites
    "spam_risk_too_many_pending_share": Motivo(
        "Já há 5 rascunhos esperando na TikTok nas últimas 24 h", Acao.esperar),
    "rate_limit_exceeded": Motivo("A TikTok pediu para esperar um pouco antes de enviar de novo",
                                  Acao.esperar),
    "spam_risk_too_many_posts": Motivo("A conta atingiu o limite de posts do dia",
                                       Acao.reagendar),
    "reached_active_user_cap": Motivo(
        "O app atingiu o limite diário de contas que podem postar pela API", Acao.reagendar),
    # conta e autorização
    "unaudited_client_can_only_post_to_private_accounts": Motivo(
        "Sem auditoria, a conta precisa estar privada para publicar", Acao.deixar_privada),
    "privacy_level_option_mismatch": Motivo(
        "A privacidade escolhida não está mais disponível para a conta", Acao.reagendar),
    "access_token_invalid": _AUTORIZACAO,
    "scope_not_authorized": _AUTORIZACAO,
    "scope_permission_missed": _AUTORIZACAO,
    "auth_removed": _AUTORIZACAO,
    "spam_risk_user_banned_from_posting": Motivo(
        "A TikTok bloqueou postagens desta conta", Acao.verificar_app),
    "spam_risk": Motivo("A TikTok considerou o envio arriscado e o bloqueou", Acao.verificar_app),
    "spam_risk_text": Motivo("A TikTok recusou o texto do post", Acao.reagendar),
    # vídeo
    "file_format_check_failed": Motivo(f"{_FORA_DAS_REGRAS} (formato)", Acao.trocar_video),
    "duration_check_failed": Motivo(f"{_FORA_DAS_REGRAS} (duração)", Acao.trocar_video),
    "frame_rate_check_failed": Motivo(f"{_FORA_DAS_REGRAS} (quadros por segundo)",
                                      Acao.trocar_video),
    "picture_size_check_failed": Motivo(f"{_FORA_DAS_REGRAS} (tamanho da imagem)",
                                        Acao.trocar_video),
    "video_pull_failed": Motivo("A TikTok não conseguiu ler o vídeo enviado", Acao.tentar_de_novo),
    "invalid_file_upload": Motivo("A TikTok recusou o arquivo enviado", Acao.trocar_video),
    # pedido e processamento
    "invalid_params": Motivo("A TikTok recusou os dados do envio", Acao.tentar_de_novo),
    "invalid_param": Motivo("A TikTok recusou os dados do envio", Acao.tentar_de_novo),
    "internal": Motivo("A TikTok teve um erro interno ao processar o vídeo",
                       Acao.tentar_de_novo),
    "internal_error": Motivo("A TikTok teve um erro interno", Acao.tentar_de_novo),
    "publish_cancelled": Motivo("O envio foi cancelado na TikTok", Acao.tentar_de_novo),
}


def traduzir(codigo: str | None) -> Motivo:
    """Motivo e ação de um código da TikTok (fallback com o código cru)."""
    if codigo and codigo in MOTIVOS:
        return MOTIVOS[codigo]
    return Motivo(f"A TikTok recusou o envio (código {codigo or 'desconhecido'})",
                  Acao.tentar_de_novo)
