"""T068 (SC-006): o bruto gravado no HD e as linhas normalizadas não trazem dado pessoal de
terceiros: nem chave pessoal, nem o `autorRef` cru das avaliações (vira hash com pepper), nem
cookie/Authorization. O coletor já é testado em `apps/coletor/tests/test_log.py`; aqui é o lado do
servidor, sobre o que a ingestão guardou."""

import gzip
import json
import re

from fakes.coletor_fake import SP, png
from sqlalchemy import select, text

from integration.coleta_helpers import coletor, dono, ligado  # noqa: F401
from sociman_api import storage
from sociman_api.coleta.privacidade import CHAVES_PESSOAIS
from sociman_api.mercado.models import Avaliacao, ColetaItem

PADROES = re.compile(r"cookie|authorization|autor-|user_name|nickname|avatar", re.IGNORECASE)


def test_bruto_e_linhas_sem_dado_pessoal(client, db, ligado, coletor):  # noqa: F811
    from datetime import UTC, datetime

    hoje = datetime.now(UTC).astimezone(SP).date()
    coletor.semear(db, produtos=1, dias=1, ranking=False)
    pid = coletor.produto_id(0)
    coletor.abrir()
    t_av = coletor.tarefa(db, "avaliacoes", f"avaliacoes:{pid}:1", coletor.url_produto(0), hoje,
                          nivel=8, fonte="pagina_publica", reservar=True)
    t_vid = coletor.tarefa(db, "produto_videos", f"produto_videos:{pid}", coletor.url_produto(0),
                           hoje, nivel=7, fonte="affiliate", reservar=True)
    foto = png(7)
    coletor.imagens([foto], t_av, origem="avaliacao")
    av = coletor.campos_avaliacoes(0, 3, imagens=[foto])
    vid = coletor.campos_videos(0, 2)
    # O coletor já podou: o bruto chega com as chaves pessoais marcadas, nunca com o valor.
    bruto_av = {"campos": av, "reviews": [{"user_name": "[podado]", "avatar": "[podado]",
                                           "texto": "ok"}]}
    bruto_vid = {"campos": vid, "creators": [{"nickname": "[podado]", "handle": "criadora.0"}]}
    r = coletor.itens([
        coletor.item(t_av, av, hoje, hora=20, imagens=[foto], bruto_extra={"reviews": bruto_av["reviews"]}),
        coletor.item(t_vid, vid, hoje, hora=20, bruto_extra={"creators": bruto_vid["creators"]}),
    ])
    assert all(x["status"] == "gravado" for x in r["resultados"]), r
    coletor.fechar()
    db.expire_all()
    # 1. As linhas: nenhuma avaliação guarda o autorRef; só o hash (64 hex) com o pepper.
    avs = db.scalars(select(Avaliacao)).all()
    assert len(avs) == 3
    for a in avs:
        assert re.fullmatch(r"[0-9a-f]{64}", a.autor_hash)
        assert "autor-" not in json.dumps(a.campos)
    # 2. O bruto gravado no HD: sem chave pessoal com valor e sem os padrões proibidos.
    itens = db.scalars(select(ColetaItem).where(ColetaItem.bruto_ref.is_not(None))).all()
    assert len(itens) >= 2
    for it in itens:
        dados = json.loads(gzip.decompress(storage.get(it.bruto_ref, bucket="mercado")))
        texto = json.dumps(dados, ensure_ascii=False)
        for m in PADROES.finditer(texto):
            # as chaves podadas podem aparecer, mas só com "[podado]" como valor
            trecho = texto[m.start():m.start() + 60]
            assert "[podado]" in trecho or m.group(0).lower() in ("avatar",) and "[podado]" in trecho, trecho
        for chave in _chaves(dados):
            if chave in CHAVES_PESSOAIS:
                assert _valor_podado(dados, chave), chave
    # 3. O registro da coleta (itens) não guarda nenhum trecho do bruto nem do autor.
    linhas = db.execute(text("SELECT erro_codigo, erro_campo FROM mercado_coleta_itens")).all()
    assert not any("autor-" in str(l_) for l_ in linhas)


def _chaves(obj) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            out |= _chaves(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _chaves(v)
    return out


def _valor_podado(obj, chave: str) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == chave and v != "[podado]":
                return False
            if not _valor_podado(v, chave):
                return False
    elif isinstance(obj, list):
        return all(_valor_podado(v, chave) for v in obj)
    return True
