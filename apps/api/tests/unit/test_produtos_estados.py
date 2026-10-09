"""Regras puras do cadastro do produto (spec 012, T008; research R8, R9 e R11)."""

import uuid
from dataclasses import dataclass, field, replace

import pytest

from sociman_api.geracao.models import GeracaoStatus as G
from sociman_api.produtos import estados
from sociman_api.produtos.estados import FICHA, FLAT, RECORTE, Pendencia, Ultima
from sociman_api.produtos.models import ProdutoFichaPor
from sociman_api.produtos.models import ProdutoStatus as S


@dataclass(frozen=True)
class P:
    status: S = S.gerando
    ficha_por: ProdutoFichaPor | None = None
    nome_comercial: str | None = "Short canelado"
    categoria: str | None = "roupa > shorts"
    material_en: str | None = "ribbed knit"
    material_pt: str | None = "malha canelada"
    formato_corte: str | None = "biker shorts"
    tamanho_relativo: str | None = "identical"
    descricao_prompt: str | None = "Ribbed knit biker shorts."
    descricao_venda: str | None = "Confortável."
    detalhes_visiveis: list[str] = field(default_factory=lambda: ["LS logo"])
    cuidados: list[str] = field(default_factory=lambda: ["não é jeans"])
    precisa_flat: bool | None = True


@dataclass(frozen=True)
class V:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    cor_en: str | None = "black"
    cor_pt: str | None = "preto"
    recorte_image_id: uuid.UUID | None = None
    flat_image_id: uuid.UUID | None = None


IMG = uuid.uuid4()
COM_FICHA = P(ficha_por=ProdutoFichaPor.ia)


def _proximo(produto, variantes, ultimas=(), evento="gancho"):
    return estados.proximo(produto, variantes, list(ultimas), evento)


# ---- a tabela de transições do data-model ----

def test_sem_variante_e_rascunho():
    d = _proximo(P(status=S.revisao, ficha_por=ProdutoFichaPor.ia), [])
    assert d.status == S.rascunho and d.pedidos == ()


def test_fotos_enviadas_pedem_a_ficha_uma_vez():
    v = V()
    d = _proximo(P(status=S.rascunho, precisa_flat=None), [v])
    assert d.status == S.gerando and d.pedidos == ((FICHA, None),)
    aberta = Ultima(FICHA, None, G.rodando)
    assert _proximo(P(precisa_flat=None), [v], [aberta]).pedidos == ()


def test_ficha_aplicada_pede_os_recortes_que_faltam():
    a, b = V(), V()
    abertas = [Ultima(RECORTE, a.id, G.na_fila)]
    d = _proximo(COM_FICHA, [a, b], abertas)
    assert d.status == S.gerando and d.pedidos == ((RECORTE, b.id),)


def test_flat_so_depois_do_recorte():
    sem_recorte, com_recorte = V(), V(recorte_image_id=IMG)
    d = _proximo(COM_FICHA, [sem_recorte, com_recorte])
    assert d.pedidos == ((RECORTE, sem_recorte.id), (FLAT, com_recorte.id))


def test_flat_espera_a_cor_e_a_ficha_completa():
    v = V(recorte_image_id=IMG, cor_en=None)
    assert _proximo(COM_FICHA, [v]).pedidos == ()
    incompleta = replace(COM_FICHA, formato_corte=None)
    assert _proximo(incompleta, [V(recorte_image_id=IMG)]).pedidos == ()


def test_geracao_falha_nao_e_repedida():
    v = V()
    for status in (G.falhou, G.cancelada):
        d = _proximo(COM_FICHA, [v], [Ultima(RECORTE, v.id, status)])
        assert d.status == S.gerando and d.pedidos == ()
    assert _proximo(P(), [v], [Ultima(FICHA, None, G.falhou)]).pedidos == ()


def test_tudo_pronto_vai_a_revisao():
    v = V(recorte_image_id=IMG, flat_image_id=IMG)
    assert _proximo(COM_FICHA, [v]).status == S.revisao
    sem_flat = replace(COM_FICHA, precisa_flat=False)
    d = _proximo(sem_flat, [V(recorte_image_id=IMG)])
    assert d.status == S.revisao and d.pedidos == ()


def test_aprovado_so_sai_com_edicao():
    v = V(recorte_image_id=IMG, flat_image_id=IMG)
    aprovado = replace(COM_FICHA, status=S.aprovado)
    assert _proximo(aprovado, [v], evento="gancho").status == S.aprovado
    assert _proximo(aprovado, [v], evento="edicao").status == S.revisao
    # Edição que cria passo (variante nova sem recorte) → gerando.
    assert _proximo(aprovado, [v, V()], evento="edicao").status == S.gerando


# ---- pendências (FR-018) ----

def test_pendencias_exatas():
    sem_cor = V(cor_en=None, recorte_image_id=IMG, flat_image_id=IMG)
    sem_recorte = V()
    abertas = [Ultima(FLAT, sem_cor.id, G.revisao), Ultima(FLAT, sem_cor.id, G.na_fila)]
    out = estados.pendencias(P(), [sem_cor, sem_recorte], abertas)
    assert out == [
        Pendencia("ficha_incompleta"),
        Pendencia("sem_cor", sem_cor.id),
        Pendencia("sem_recorte", sem_recorte.id),
        Pendencia("sem_flat", sem_recorte.id),
        Pendencia("geracao_em_andamento", sem_cor.id),
    ]


def test_pendencias_vazias_quando_tudo_pronto():
    v = V(recorte_image_id=IMG, flat_image_id=IMG)
    terminada = [Ultima(FLAT, v.id, G.falhou)]
    assert estados.pendencias(COM_FICHA, [v], terminada) == []
    assert estados.pendencias(COM_FICHA, [], []) == [Pendencia("sem_variante")]


@pytest.mark.parametrize("campo", ["nome_comercial", "material_en", "descricao_venda"])
def test_ficha_completa_exige_cada_texto(campo):
    v = V()
    assert estados.ficha_completa(COM_FICHA, [v])
    assert not estados.ficha_completa(replace(COM_FICHA, **{campo: "  "}), [v])
    assert not estados.ficha_completa(replace(COM_FICHA, cuidados=[]), [v])
    assert not estados.ficha_completa(replace(COM_FICHA, precisa_flat=None), [v])
    assert not estados.ficha_completa(COM_FICHA, [V(cor_pt=None)])
