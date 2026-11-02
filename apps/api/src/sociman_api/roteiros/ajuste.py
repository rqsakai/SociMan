"""O "Não aprovo" do wizard virando ajuste pela IA (spec 031, research R6; FR-016, FR-034, FR-037).

- **pedido:** `guiado.recusar` grava o `pedido_troca` no chat (autor = o humano) e pede o passo
  `roteiro.ajuste` (Claude, resultado único, sem escolha). Um pedido é uma cadeia: a resposta a
  um esclarecimento (um novo "Não aprovo" no mesmo alvo, logo depois dele) continua o mesmo
  pedido (`conteudo.pedido` = o `seq` do primeiro);
- **esclarecimento:** a IA não entendeu e devolve uma pergunta com opções; ela vai para o chat e
  nada é gerado. No máximo `MAX_ESCLARECIMENTOS` por pedido: no último, a mensagem pede a
  mudança, e uma pergunta a mais vira só um aviso;
- **mudança:** o aplicador confere que só os campos do alvo mudam (`CAMPOS_DO_ALVO`) e aplica pelo
  save normal (`service.editar` na narração e no final; `cenas/quadros.arquivar_desde` nos
  quadros; o save da cena e o arquivamento da tomada no trecho), com o autor = o humano que
  recusou (o `created_by` do pedido) e `details.ia` com o `chamadaId`. A máquina refaz só o que
  mudou, e o resultado volta para a aprovação humana no mesmo portão (princípio VII).

O alvo `posicao` (o modal de cenas, US4; FR-021) devolve a cena daquela posição (ação, motor e
uma instrução por quadro) com os mesmos `trechos`: a soma da grade não muda. Com `extras.nova`
(o "criar nova" do `guiado.definir_cena`), ela vira uma cena nova da biblioteca; sem ele (o "Não
aprovo" da posição), muda a cena da posição. Uma cena reaproveitada (reuso total, `usada` ou de
outro vídeo) nunca é alterada: o ajuste de posição, de quadros ou de trecho **deriva** antes
(`plano_guiado.separar`, FR-022).
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.cenas import quadros as cenas_quadros
from sociman_api.cenas import schemas as cenas_schemas
from sociman_api.cenas import service as cenas_service
from sociman_api.cenas import tomadas as cenas_tomadas
from sociman_api.cenas.models import Cena, CenaMotor, CenaTomada
from sociman_api.errors import ApiError
from sociman_api.geracao.erros import MotorErro
from sociman_api.geracao.models import Geracao, GeracaoAlvo, GeracaoCandidato
from sociman_api.roteiros import (
    conversa,
    estado,
    grade,
    maquina,
    pedidos,
    plano_guiado,
    schemas,
)
from sociman_api.roteiros.models import (
    ConversaTipo,
    PosicaoReuso,
    Roteiro,
    RoteiroConversa,
)

MAX_ESCLARECIMENTOS = 3
# Os campos da `mudanca` que cada alvo pode mudar (o resto tem de vir vazio).
CAMPOS_DO_ALVO: dict[str, frozenset[str]] = {
    "narracao": frozenset({"velocidade", "frases"}),
    "final": frozenset({"velocidade", "frases"}),
    "quadros": frozenset({"quadros"}),
    "trecho": frozenset({"acao", "motor"}),
    "posicao": frozenset({"trechos", "acao", "motor", "quadros"}),
}
_CAMPOS = ("quadros", "acao", "motor", "velocidade", "frases", "trechos")


# ---- o pedido ----

def _cadeia(linhas: list[RoteiroConversa], alvo: dict[str, Any]) -> int | None:
    """O pedido que esta recusa continua: o da última mensagem de troca, se ela é um
    esclarecimento do mesmo alvo (a resposta a ele)."""
    trocas = [m for m in linhas if m.tipo in (ConversaTipo.pedido_troca,
                                               ConversaTipo.esclarecimento)]
    if trocas and trocas[-1].tipo == ConversaTipo.esclarecimento and trocas[-1].alvo == alvo:
        return trocas[-1].conteudo.get("pedido")
    return None


def esclarecimentos(linhas: list[RoteiroConversa], pedido: int | None) -> list[RoteiroConversa]:
    return [m for m in linhas if m.tipo == ConversaTipo.esclarecimento
            and m.conteudo.get("pedido") == pedido]


def registrar_pedido(db: Session, actor: Actor, r: Roteiro, alvo: dict[str, Any],
                     opcoes: list[str], texto: str) -> RoteiroConversa:
    """O `pedido_troca` no chat (o texto como o humano escreveu; a IA recebe sem as proibidas,
    com o aviso no chat). As opções de um esclarecimento viram os rótulos dele."""
    linhas = conversa.mensagens(db, r.id)
    pedido = _cadeia(linhas, alvo)
    if pedido is not None:
        ultimo = esclarecimentos(linhas, pedido)[-1]
        rotulos = {o["id"]: o["rotulo"] for o in ultimo.conteudo.get("opcoes") or []}
        opcoes = [rotulos.get(o, o) for o in opcoes]
    conteudo: dict[str, Any] = {"alvo": alvo, "opcoes": opcoes}
    if texto:
        conteudo["texto"] = texto
    # O 1º da cadeia: o pedido é ele (o `seq` que vai ganhar; a tabela é só de inserção, e o
    # roteiro está travado por quem chama).
    conteudo["pedido"] = pedido if pedido is not None else \
        max((m.seq for m in linhas), default=0) + 1
    linha = conversa.adicionar(db, r, ConversaTipo.pedido_troca, conteudo, autor=actor,
                               alvo=alvo)
    _, efetivo, _ = conversa.guia_do(db, r.perfil_id)
    _, achadas = conversa.sem_proibidas(texto, efetivo.proibidas) if texto else ("", [])
    if achadas:
        conversa.adicionar(db, r, ConversaTipo.aviso, {
            "code": "palavra_proibida", "palavras": achadas, "pedido": linha.conteudo["pedido"],
            "texto": f"{', '.join(achadas)}: proibida(s) pelo guia do perfil; não entra(m) no "
                     "pedido à IA."}, alvo=alvo)
    return linha


def pedir(db: Session, actor: Actor, r: Roteiro, alvo: dict[str, Any],
          linha: RoteiroConversa, *, nova: bool = False) -> Geracao:
    """A mensagem é montada na hora da chamada (`mensagem`), a partir do `seq` do pedido. `nova`:
    a posição ganha uma cena nova (o "criar nova" do modal)."""
    extras: dict[str, Any] = {"alvo": alvo, "seq": linha.seq,
                              "pedido": linha.conteudo["pedido"]}
    if nova:
        extras["nova"] = True
    return pedidos._criar(db, actor, r, "roteiro.ajuste", GeracaoAlvo.roteiro, r.id,
                          r.perfil_id, {"instrucao": _texto_pedido(db, r, linha),
                                        "extras": extras})


def _texto_pedido(db: Session, r: Roteiro, linha: RoteiroConversa) -> str:
    _, efetivo, _ = conversa.guia_do(db, r.perfil_id)
    partes = list(linha.conteudo.get("opcoes") or [])
    texto, _ = conversa.sem_proibidas(linha.conteudo.get("texto") or "", efetivo.proibidas)
    if texto:
        partes.append(texto)
    return "; ".join(partes)[:600]


# ---- a mensagem ----

def _alvo_tag(alvo: dict[str, Any]) -> str:
    attrs = "".join(f' {k}="{alvo[k]}"' for k in ("ordem", "quadro", "trecho")
                    if alvo.get(k) is not None)
    return f'<alvo tipo="{alvo["tipo"]}"{attrs}/>'


def _atual(db: Session, r: Roteiro, alvo: dict[str, Any]) -> list[str]:
    limpo = conversa._limpo
    out = ["<atual>"]
    pos = estado.posicoes(r)
    if alvo["tipo"] in ("narracao", "final"):
        out.append(f"<velocidade>{r.velocidade}</velocidade>")
        for p in pos:
            out.append(f'<posicao ordem="{p.ordem}" orcamento="{p.orcamento_chars or 0}">')
            for i in p.frases:
                if 0 <= i < len(r.frases):
                    out.append(f'<frase indice="{i}">{limpo(r.frases[i])}</frase>')
            out.append("</posicao>")
    else:
        p = next(p for p in pos if p.ordem == alvo["ordem"])
        cena = db.get(Cena, p.cena_id)
        out.append(f'<cena trechos="{p.trechos}" motor="{cena.motor.value}">'
                   f"{limpo(cena.acao)}</cena>")
        if cena.camera:
            out.append(f"<camera>{limpo(cena.camera)}</camera>")
        for q in cenas_quadros.ativos(db, cena.id):
            out.append(f'<quadro ordem="{q.ordem}" papel="{q.papel.value}">'
                       f"{limpo(q.instrucao)}</quadro>")
    out.append("</atual>")
    return out


def mensagem(db: Session, geracao: Geracao) -> str:
    r = db.get(Roteiro, geracao.alvo_id)
    ex = estado.extras(geracao)
    alvo = ex["alvo"]
    linhas = conversa.mensagens(db, r.id)
    linha = next((m for m in linhas if m.seq == ex.get("seq")), None)
    pedido = conversa._limpo(_texto_pedido(db, r, linha) if linha is not None else "")
    out = ["<instrucao>Transforme o <pedido> do operador numa mudança só do <alvo>.</instrucao>",
           _alvo_tag(alvo), f"<pedido>{pedido}</pedido>", *_atual(db, r, alvo)]
    if alvo["tipo"] == "posicao":
        p = next(p for p in estado.posicoes(r) if p.ordem == alvo["ordem"])
        tipo = "uma cena NOVA (outra ação) para esta posição" if ex.get("nova") \
            else "a cena desta posição com o que foi pedido"
        out.append(f"<cena_da_posicao trechos=\"{p.trechos}\">Devolva {tipo}: a ação, o motor e "
                   f"exatamente {(p.trechos or 1) + 1} quadros (o estado final de cada um, em "
                   "inglês). Os trechos não mudam: a soma da grade é fixa.</cena_da_posicao>")
    feitas = esclarecimentos(linhas, ex.get("pedido"))
    if feitas:
        out.append("<esclarecimentos>")
        for e in feitas:
            resposta = next((m for m in linhas if m.seq > e.seq
                             and m.tipo == ConversaTipo.pedido_troca), None)
            texto = _texto_pedido(db, r, resposta) if resposta is not None else ""
            out.append(f"<pergunta>{conversa._limpo(e.conteudo.get('texto'))}</pergunta>"
                       f"<resposta>{conversa._limpo(texto)}</resposta>")
        out.append("</esclarecimentos>")
    if len(feitas) >= MAX_ESCLARECIMENTOS:
        out.append("<sem_mais_perguntas>Não pergunte de novo: devolva a mudança.</sem_mais_perguntas>")
    guia, _, _ = conversa.guia_do(db, r.perfil_id)
    if guia:
        out.append(f"<guia_perfil>{conversa._limpo(guia)}</guia_perfil>")
    return "\n".join(out)


# ---- aplicar ----

def _aviso(db: Session, r: Roteiro, alvo: dict[str, Any], code: str, texto: str,
           pedido: Any, chamada_id: uuid.UUID | None) -> None:
    conversa.adicionar(db, r, ConversaTipo.aviso, {"code": code, "texto": texto,
                                                   "pedido": pedido},
                       alvo=alvo, ia_chamada_id=chamada_id)


def _mudou(mudanca: dict[str, Any]) -> set[str]:
    return {c for c in _CAMPOS if mudanca.get(c) not in (None, [], "")}


def conferir(alvo: dict[str, Any], mudanca: dict[str, Any]) -> None:
    """Só os campos do alvo mudam, e a mudança é do alvo pedido (FR-016)."""
    veio = mudanca.get("alvo") or {}
    if veio.get("tipo") != alvo["tipo"] or (alvo.get("ordem") is not None
                                            and veio.get("ordem") != alvo["ordem"]):
        raise MotorErro("entrada_invalida", "A IA propôs mudar outro item do vídeo",
                        detalhe=f"alvo {veio}")
    fora = _mudou(mudanca) - CAMPOS_DO_ALVO[alvo["tipo"]]
    if fora:
        raise MotorErro("entrada_invalida", "A IA propôs mudar fora do item recusado",
                        detalhe=f"campos {sorted(fora)}")
    if alvo["tipo"] == "quadros":
        desde = alvo.get("quadro") or 0
        if any(int(q["ordem"]) < desde for q in mudanca.get("quadros") or []):
            raise MotorErro("entrada_invalida", "A IA propôs mudar um quadro mantido")


def aplicar(db: Session, actor: Actor, geracao: Geracao, candidato: GeracaoCandidato) -> None:
    """O aplicador do `roteiro.ajuste` (o `actor` é o humano que recusou)."""
    r = db.get(Roteiro, geracao.alvo_id, with_for_update=True)
    if r is None or r.archived or not r.guiado:
        return
    m = candidato.metricas or {}
    dados = m.get("ajuste") or {}
    chamada_id = conversa_uuid(m.get("chamada_id"))
    ex = estado.extras(geracao)
    alvo, pedido = ex["alvo"], ex.get("pedido")
    if dados.get("tipo") == "pergunta":
        _esclarecer(db, r, alvo, pedido, dados, chamada_id)
        return
    if m.get("proibidas"):  # a 2ª tentativa ainda trouxe palavra proibida (017): nada muda
        _aviso(db, r, alvo, "palavra_proibida", "A IA usou uma palavra proibida pelo guia do "
               "perfil; nada foi trocado. Peça de outro jeito.", pedido, chamada_id)
        return
    mudanca = dados.get("mudanca") or {}
    conferir(alvo, mudanca)
    if alvo["tipo"] == "posicao" and ex.get("nova"):  # o modal, ou o avançado depois do texto
        if estado.nivel(r.status) < estado.nivel(_status_do_alvo("posicao")[0]):
            raise MotorErro("entrada_invalida", "O plano do vídeo mudou depois do pedido")
    elif r.status not in _status_do_alvo(alvo["tipo"]):
        raise MotorErro("entrada_invalida", "O vídeo mudou de etapa depois do pedido; peça de "
                        "novo")
    ia = {"chamadaId": str(chamada_id) if chamada_id else None, "passo": "roteiro.ajuste",
          "geracaoId": str(geracao.id), "pedido": pedido}
    if ex.get("nova"):
        ia["nova"] = True
    aplicar_alvo = _APLICAR[alvo["tipo"]]
    try:
        aplicar_alvo(db, actor, r, alvo, mudanca, ia)
    except ApiError as exc:  # a cena usada (duplique), o texto inválido…
        raise MotorErro("entrada_invalida", exc.message, detalhe=exc.code) from exc
    _aviso(db, r, alvo, "ajuste_aplicado", dados.get("resumo") or "Ajustei o que foi pedido.",
           pedido, chamada_id)


def conversa_uuid(valor: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(valor)) if valor else None
    except ValueError:
        return None


def _status_do_alvo(tipo: str):
    from sociman_api.roteiros import guiado

    return guiado.STATUS_DO_ALVO[tipo]


def _esclarecer(db: Session, r: Roteiro, alvo: dict[str, Any], pedido: Any,
                dados: dict[str, Any], chamada_id: uuid.UUID | None) -> None:
    feitos = esclarecimentos(conversa.mensagens(db, r.id), pedido)
    if len(feitos) >= MAX_ESCLARECIMENTOS:
        _aviso(db, r, alvo, "ajuste_sem_entender", "A IA não entendeu o pedido. Descreva de outro "
               "jeito o que trocar.", pedido, chamada_id)
        return
    p = dados.get("pergunta") or {}
    conversa.adicionar(db, r, ConversaTipo.esclarecimento,
                       {**p, "pedido": pedido, "resumo": dados.get("resumo") or ""},
                       pergunta_id=p.get("id"), alvo=alvo, ia_chamada_id=chamada_id)


def _narracao(db: Session, actor: Actor, r: Roteiro, alvo: dict[str, Any],
              mudanca: dict[str, Any], ia: dict[str, Any]) -> None:
    """Velocidade e/ou frases, pelo `service.editar` (a narração fica desatualizada e é refeita;
    os quadros não mudam)."""
    from sociman_api.roteiros import service

    campos: dict[str, Any] = {}
    if mudanca.get("velocidade") is not None:
        campos["velocidade"] = Decimal(str(mudanca["velocidade"])).quantize(Decimal("0.01"))
    if mudanca.get("frases"):
        frases = list(r.frases)
        for f in mudanca["frases"]:
            i = int(f["indice"])
            if not 0 <= i < len(frases):
                raise MotorErro("entrada_invalida", "A IA mudou uma frase que não existe")
            frases[i] = " ".join(str(f["texto"]).split())
        for p in estado.posicoes(r):  # o orçamento de fala de cada posição (R4)
            chars = sum(len(frases[i]) for i in p.frases if 0 <= i < len(frases))
            limite = p.orcamento_chars or grade.orcamento_chars(float(p.duracao_s or 0))
            if limite and chars > limite:
                raise MotorErro("entrada_invalida", f"A fala nova não cabe na cena {p.ordem + 1}")
        campos["frases"] = frases
    if not campos:
        raise MotorErro("entrada_invalida", "A IA não propôs nenhuma mudança na narração")
    service.editar(db, actor, r.id, schemas.RoteiroPatch(version=r.version, **campos),
                   ia={**ia, "alvo": alvo})


def _quadros(db: Session, actor: Actor, r: Roteiro, alvo: dict[str, Any],
             mudanca: dict[str, Any], ia: dict[str, Any]) -> None:
    """Refaz o quadro recusado e os seguintes (FR-026/028), com as instruções novas; os de antes
    e as outras posições ficam. As aprovações da cena caem (`cenas/quadros.py`)."""
    from sociman_api.roteiros import service

    p = service._posicao(r, alvo["ordem"])
    desde = alvo.get("quadro") or 0
    instrucoes = {int(q["ordem"]): str(q["instrucao"]) for q in mudanca.get("quadros") or []}
    before = history.snapshot(r)
    cena = plano_guiado.separar(db, actor, r, p, manter=desde,
                                details={"ordem": p.ordem, "ia": ia})
    refeitas = cenas_quadros.arquivar_desde(db, actor, cena, desde, instrucoes=instrucoes,
                                            details={"ia": ia, "roteiroId": str(r.id)})
    service._comandar(r, actor)
    service._record(db, actor, r, "updated", before,
                    {"acao": "ajuste", "alvo": alvo, "ia": ia, "refeitos": refeitas})
    maquina.keyframe_mudou(db, cena.id)


def _trecho(db: Session, actor: Actor, r: Roteiro, alvo: dict[str, Any],
            mudanca: dict[str, Any], ia: dict[str, Any]) -> None:
    """A ação e/ou o motor da cena pelo save da cena, e a tomada do trecho recusado arquivada:
    só ele é refeito (os outros trechos continuam servindo, R8)."""
    from sociman_api.roteiros import service

    p = service._posicao(r, alvo["ordem"])
    before = history.snapshot(r)
    x = p.trecho(alvo["trecho"])
    tomada = db.get(CenaTomada, x.tomada_id) if x is not None and x.tomada_id else None
    origem = db.get(Cena, p.cena_id)
    campos = _campos_da_cena(origem, mudanca)
    if campos and not plano_guiado.propria(db, r, p):
        # A cena reaproveitada não muda (FR-022): a derivada já nasce com a mudança e com os
        # quadros da origem; os trechos são refeitos nela (as tomadas são da cena).
        plano_guiado.separar(db, actor, r, p, manter=grade.MAX_TRECHOS + 1, mudancas=campos,
                             details={"ordem": p.ordem, "ia": ia})
        tomada = None
    elif campos:
        cena = cenas_service.get_cena_or_404(db, p.cena_id, lock=True)
        cenas_service.editar(db, actor, cena.id,
                             cenas_schemas.CenaPatch(version=cena.version, **campos))
    if tomada is not None and not tomada.archived:
        cenas_tomadas.arquivar(db, actor, tomada.id, tomada.version)
    p.aprovado_clipe_em = p.aprovado_clipe_por = None
    service._comandar(r, actor)
    service._record(db, actor, r, "updated", before,
                    {"acao": "ajuste", "alvo": alvo, "ia": ia,
                     "cena": sorted(campos), "tomadaArquivada": str(tomada.id) if tomada
                     else None})
    maquina.avancar(db, r, actor)


def _campos_da_cena(cena: Cena, mudanca: dict[str, Any]) -> dict[str, Any]:
    campos: dict[str, Any] = {}
    if mudanca.get("acao") and mudanca["acao"] != cena.acao:
        campos["acao"] = str(mudanca["acao"])[:1000]
    if mudanca.get("motor") and mudanca["motor"] != cena.motor.value:
        campos["motor"] = CenaMotor(mudanca["motor"])
    return campos


def _instrucoes(mudanca: dict[str, Any], trechos: int, acao: str,
                atuais: list[str] | None = None) -> list[str]:
    """Uma instrução por quadro: a da IA, senão a atual, senão a genérica a partir da ação."""
    da_ia = {int(q["ordem"]): str(q["instrucao"]) for q in mudanca.get("quadros") or []}
    if any(not 0 <= o <= trechos for o in da_ia):
        raise MotorErro("entrada_invalida", "A IA propôs um quadro que a cena não tem")
    genericas = plano_guiado.genericas(acao, trechos)
    return [da_ia.get(i) or (atuais[i] if atuais and i < len(atuais) else genericas[i])
            for i in range(trechos + 1)]


def _posicao(db: Session, actor: Actor, r: Roteiro, alvo: dict[str, Any],
             mudanca: dict[str, Any], ia: dict[str, Any]) -> None:
    """A cena de uma posição (o modal de cenas): com `ia.nova`, uma cena nova da biblioteca
    (FR-023); sem, a cena da posição muda (a própria) ou é derivada (a reaproveitada, FR-022).
    Os trechos não mudam: a soma da grade é fixa."""
    from sociman_api.roteiros import service

    p = service._posicao(r, alvo["ordem"])
    trechos = int(p.trechos or 1)
    if mudanca.get("trechos") not in (None, trechos):
        raise MotorErro("entrada_invalida", f"A IA mudou a cena {p.ordem + 1} para "
                        f"{mudanca['trechos']} trecho(s); a soma da grade não fecharia")
    atual = db.get(Cena, p.cena_id)
    before = history.snapshot(r)
    campos = _campos_da_cena(atual, mudanca)
    acao = campos.get("acao") or atual.acao
    details: dict[str, Any] = {"acao": "ajuste", "alvo": alvo, "ia": ia}
    if ia.get("nova"):
        nova = {"nome": f"{r.nome[:100]} – cena {p.ordem + 1}", "acao": acao,
                "plano": atual.plano.value if atual.plano else None,
                "movimento": atual.movimento, "camera": None,
                "motor": (campos.get("motor") or atual.motor).value,
                "quadros": _instrucoes(mudanca, trechos, acao)}
        cena = plano_guiado.cena_nova(db, actor, r, nova, trechos, ia)
        plano_guiado.trocar_cena(p, cena, PosicaoReuso.nova, "Cena nova pedida pelo operador.")
        details |= {"cenaId": str(cena.id), "cenaAnteriorId": str(atual.id)}
    else:
        atuais = [q.instrucao for q in cenas_quadros.ativos(db, atual.id)]
        instrucoes = _instrucoes(mudanca, trechos, acao, atuais)
        if not campos and instrucoes == atuais:
            raise MotorErro("entrada_invalida", "A IA não propôs nenhuma mudança na cena")
        if plano_guiado.propria(db, r, p):
            if campos:
                cenas_service.editar(db, actor, atual.id,
                                     cenas_schemas.CenaPatch(version=atual.version, **campos))
            mudaram = {i: t for i, t in enumerate(instrucoes)
                       if i >= len(atuais) or t != atuais[i]}
            if mudaram:
                cenas_quadros.arquivar_desde(db, actor, atual, min(mudaram),
                                             instrucoes=mudaram,
                                             details={"ia": ia, "roteiroId": str(r.id)})
        else:
            cena = plano_guiado.derivar(db, actor, r, atual, trechos, ia, instrucoes=instrucoes,
                                        mudancas=campos, details={"ordem": p.ordem})
            plano_guiado.trocar_cena(p, cena, PosicaoReuso.plano, p.motivo)
            details |= {"cenaId": str(cena.id), "cenaAnteriorId": str(atual.id)}
    service._comandar(r, actor)
    service._record(db, actor, r, "updated", before, details)
    maquina.avancar(db, r, actor)


_APLICAR = {"narracao": _narracao, "final": _narracao, "quadros": _quadros, "trecho": _trecho,
            "posicao": _posicao}
