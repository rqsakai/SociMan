"""Motivos em pt-BR (spec 015, T019, R19, SC-006): todo código conhecido tem motivo e ação."""

from fakes.tiktok_fake import HTTP_DOS_CODIGOS

from sociman_api.publicacao.executor import Acao
from sociman_api.publicacao.tiktok import erros

# Os do R19 e os `fail_reason` documentados do status/fetch.
CODIGOS_R19 = {
    "spam_risk_too_many_pending_share", "spam_risk_too_many_posts",
    "unaudited_client_can_only_post_to_private_accounts", "privacy_level_option_mismatch",
    "access_token_invalid", "scope_not_authorized", "file_format_check_failed",
    "duration_check_failed", "frame_rate_check_failed", "picture_size_check_failed",
    "spam_risk_user_banned_from_posting", "rate_limit_exceeded", "internal", "auth_removed",
    "publish_cancelled", "video_pull_failed",
}


def test_todo_codigo_conhecido_tem_motivo_e_acao():
    assert CODIGOS_R19 <= set(erros.MOTIVOS)
    assert set(HTTP_DOS_CODIGOS) <= set(erros.MOTIVOS)
    for codigo, m in erros.MOTIVOS.items():
        assert m.motivo and m.motivo[0].isupper(), codigo
        assert isinstance(m.acao, Acao), codigo
        assert codigo not in m.motivo  # o código cru fica na tentativa, não no texto


def test_acoes_do_r19():
    assert erros.traduzir("spam_risk_too_many_pending_share").acao == Acao.esperar
    assert erros.traduzir("spam_risk_too_many_posts").acao == Acao.reagendar
    assert erros.traduzir("access_token_invalid").acao == Acao.reconectar
    assert erros.traduzir("duration_check_failed").acao == Acao.trocar_video
    assert erros.traduzir("unaudited_client_can_only_post_to_private_accounts").acao \
        == Acao.deixar_privada


def test_fallback_com_o_codigo():
    m = erros.traduzir("codigo_novo_da_tiktok")
    assert m.motivo == "A TikTok recusou o envio (código codigo_novo_da_tiktok)"
    assert m.acao == Acao.tentar_de_novo
    assert "desconhecido" in erros.traduzir(None).motivo
