"""Spec 011 (T043, R13): no conteúdo `gerado_ia`, o `conteudoIa` ausente nas opções do destino
vem `true`; o humano ainda manda `false`; fora disso, o padrão da 015 (`false`)."""

from datetime import UTC, datetime
from types import SimpleNamespace

from sociman_api.conteudos.models import Modo
from sociman_api.perfis.models import Platform
from sociman_api.postagem.service import resolver_opcoes
from sociman_api.publicacao.schemas import OpcoesTikTok
from sociman_api.publicacao.tiktok.opcoes import CONSENTIMENTO

CONTA = SimpleNamespace(platform=Platform.tiktok)


def _opcoes(**kw) -> OpcoesTikTok:
    return OpcoesTikTok.model_validate({
        "privacidade": "SELF_ONLY", "permitirComentario": True,
        "permitirDueto": False, "permitirCostura": False,
        "consentimento": {"texto": CONSENTIMENTO, "aceitoEm": datetime.now(UTC).isoformat()},
        **kw})


def test_gerado_ia_liga_o_padrao():
    assert resolver_opcoes(CONTA, Modo.publicar, _opcoes(), None, gerado_ia=True).conteudo_ia
    assert not resolver_opcoes(CONTA, Modo.publicar, _opcoes(conteudoIa=False), None,
                               gerado_ia=True).conteudo_ia
    assert not resolver_opcoes(CONTA, Modo.publicar, _opcoes(), None).conteudo_ia
