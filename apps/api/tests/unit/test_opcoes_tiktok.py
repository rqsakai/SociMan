"""Regras da tela obrigatória do Publicar (spec 015, T078, research R13)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sociman_api.publicacao.schemas import OpcoesTikTok
from sociman_api.publicacao.tiktok import opcoes as regras
from sociman_api.publicacao.tiktok.opcoes import Criador

TODAS = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"]


def _opcoes(**over) -> OpcoesTikTok:
    comercial = over.get("comercial", "nenhum")
    base = {"privacidade": "SELF_ONLY", "permitirComentario": False, "permitirDueto": False,
            "permitirCostura": False, "comercial": comercial, "conteudoIa": False,
            "consentimento": {"texto": regras.texto_consentimento(comercial),
                              "aceitoEm": datetime.now(UTC).isoformat()}}
    return OpcoesTikTok.model_validate({**base, **over})


def _criador(**over) -> Criador:
    base = {"username": "conta", "display_name": "Conta", "pode_postar": True,
            "privacidades": tuple(TODAS), "comentario_desligado": False,
            "dueto_desligado": False, "costura_desligada": False, "duracao_maxima_s": 600}
    return Criador(**{**base, **over})


def _campos(problemas) -> list[str]:
    return [p.campo for p in problemas]


@pytest.mark.parametrize("faltando", ["privacidade", "permitirComentario", "permitirDueto",
                                      "permitirCostura", "consentimento"])
def test_campos_obrigatorios_sem_padrao(faltando):
    dados = _opcoes().model_dump(by_alias=True)
    dados.pop(faltando)
    with pytest.raises(ValidationError):
        OpcoesTikTok.model_validate(dados)


def test_privacidade_desconhecida_recusada():
    with pytest.raises(ValidationError):
        _opcoes(privacidade="PUBLICO")


def test_valido_sem_problemas():
    assert regras.validar(_opcoes(), _criador(), "auditado") == []
    assert regras.validar(_opcoes(), None, "sandbox") == []


def test_sandbox_so_self_only():
    op = _opcoes(privacidade="PUBLIC_TO_EVERYONE")
    assert _campos(regras.validar(op, _criador(), "sandbox")) == ["privacidade"]
    assert regras.validar(op, _criador(), "auditado") == []


def test_privacidade_fora_das_opcoes_da_conta():
    op = _opcoes(privacidade="PUBLIC_TO_EVERYONE")
    criador = _criador(privacidades=("SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS"))
    assert _campos(regras.validar(op, criador, "auditado")) == ["privacidade"]


@pytest.mark.parametrize(("campo", "desligado"), [
    ("permitirComentario", "comentario_desligado"),
    ("permitirDueto", "dueto_desligado"),
    ("permitirCostura", "costura_desligada"),
])
def test_toggle_ligado_que_a_conta_desligou(campo, desligado):
    op = _opcoes(**{campo: True})
    assert regras.validar(op, _criador(), "auditado") == []
    assert _campos(regras.validar(op, _criador(**{desligado: True}), "auditado")) == [campo]
    # false com a conta desligada é o esperado
    assert regras.validar(_opcoes(), _criador(**{desligado: True}), "auditado") == []


def test_parceria_paga_e_so_voce_recusado():
    op = _opcoes(comercial="parceria_paga", privacidade="SELF_ONLY")
    assert "comercial" in _campos(regras.validar(op, _criador(), "auditado"))
    ok = _opcoes(comercial="parceria_paga", privacidade="PUBLIC_TO_EVERYONE")
    assert regras.validar(ok, _criador(), "auditado") == []


def test_consentimento_musica_e_marca():
    sem_musica = _opcoes(consentimento={"texto": "ok", "aceitoEm": datetime.now(UTC).isoformat()})
    assert _campos(regras.validar(sem_musica, None, "auditado")) == ["consentimento"]
    # parceria paga com o texto só de música: falta a política de marca
    op = _opcoes(comercial="parceria_paga", privacidade="PUBLIC_TO_EVERYONE",
                 consentimento={"texto": regras.CONSENTIMENTO,
                                "aceitoEm": datetime.now(UTC).isoformat()})
    assert _campos(regras.validar(op, None, "auditado")) == ["consentimento"]
    assert regras.TEXTO_MARCA in regras.texto_consentimento("parceria_paga")
    assert regras.TEXTO_MARCA not in regras.texto_consentimento("sua_marca")


def test_nao_pode_postar_e_duracao():
    assert "conta" in _campos(regras.validar(_opcoes(), _criador(pode_postar=False), "auditado"))
    probs = regras.validar(_opcoes(), _criador(duracao_maxima_s=60), "auditado", duracao_s=61)
    assert _campos(probs) == ["video"]
    assert regras.validar(_opcoes(), _criador(duracao_maxima_s=60), "auditado", duracao_s=60) == []
