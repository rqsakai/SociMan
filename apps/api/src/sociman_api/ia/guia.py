"""Domínio do guia de comunicação (spec 017; data-model "Estruturas de domínio", research R2,
R4 a R7). Puro: sem HTTP e sem sessão, salvo `em_vigor`, que lê os dois guias em vigor.

- `GuiaCampos`: os campos de um guia (perfil ou conta), já limpos;
- `GuiaBloco`: um guia que vai ao prompt (campos, versão, nível e se é rascunho do "testar");
- `GuiaEfetivo`: o que as garantias de código usam (proibidas unidas, fixas na ordem, máximo
  da conta, emojis herdados);
- `Conflito`: aviso perfil × conta (não bloqueia).

A validação do save (limites, hashtags, proibidas) também é pura e fica aqui
(`validar_limites`, `proibidas_nos_campos`); a validação cruzada, que lê o banco, fica em
`service_guia.validar_campos`. Nenhum texto do guia vai para log.
"""

import re
import unicodedata
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.ia.models import IaGuia
from sociman_api.postagem import textos

# ---- limites (R2) ----

TOM_MAX = 500
REGRAS_ITENS = 10  # faça e não faça, cada
REGRA_MAX = 200
VOCABULARIO_ITENS = 30
PROIBIDAS_ITENS = 30
TERMO_MAX = 60  # vocabulário e proibidas
EMOJIS_ITENS = 10
EMOJI_MAX = 16
EXEMPLOS = 5
EXEMPLO_MAX = 500
TOTAL_MAX = 4000
FIXAS_PERFIL_MAX = 5  # o perfil vale para toda conta, inclusive as de máximo padrão
FIXAS_PADRAO = 5  # máximo da conta quando `max_hashtags_fixas` é NULL (Q3)
FIXAS_TETO = textos.HASHTAGS_MAX  # 8: fixas próprias da conta e teto do máximo

Nivel = Literal["perfil", "conta"]
Emojis = Literal["nao", "moderado", "livre"]
TIPOS_EXEMPLO = ("titulo", "legenda", "bordao")

EMOJIS_ROTULO = {"nao": "não usar", "moderado": "com moderação", "livre": "livre"}
EXEMPLO_ROTULO = {"titulo": "título", "legenda": "legenda", "bordao": "bordão"}


@dataclass(frozen=True)
class GuiaCampos:
    """Os campos do guia em snake_case. `exemplos` = `[{"tipo", "texto"}]`."""

    tom: str = ""
    faca: tuple[str, ...] = ()
    nao_faca: tuple[str, ...] = ()
    vocabulario: tuple[str, ...] = ()
    proibidas: tuple[str, ...] = ()
    emojis: Emojis | None = None
    emojis_preferidos: tuple[str, ...] = ()
    hashtags_fixas: tuple[str, ...] = ()
    max_hashtags_fixas: int | None = None  # só na conta
    exemplos: tuple[dict[str, str], ...] = ()

    @property
    def vazio(self) -> bool:
        """Sem nada (inclusive sem máximo de fixas): conta como "sem guia"."""
        return self == GuiaCampos()

    @classmethod
    def de_linha(cls, row: IaGuia) -> "GuiaCampos":
        return cls(
            tom=row.tom, faca=tuple(row.faca), nao_faca=tuple(row.nao_faca),
            vocabulario=tuple(row.vocabulario), proibidas=tuple(row.proibidas),
            emojis=row.emojis.value if row.emojis is not None else None,  # type: ignore[arg-type]
            emojis_preferidos=tuple(row.emojis_preferidos),
            hashtags_fixas=tuple(row.hashtags_fixas),
            max_hashtags_fixas=row.max_hashtags_fixas,
            exemplos=tuple({"tipo": e["tipo"], "texto": e["texto"]} for e in row.exemplos),
        )

    @classmethod
    def de_snapshot(cls, state: dict[str, Any]) -> "GuiaCampos":
        """Do snapshot `after` de uma versão (`entity_versions`), para reverter."""
        return cls(
            tom=state.get("tom") or "", faca=tuple(state.get("faca") or ()),
            nao_faca=tuple(state.get("nao_faca") or ()),
            vocabulario=tuple(state.get("vocabulario") or ()),
            proibidas=tuple(state.get("proibidas") or ()), emojis=state.get("emojis"),
            emojis_preferidos=tuple(state.get("emojis_preferidos") or ()),
            hashtags_fixas=tuple(state.get("hashtags_fixas") or ()),
            max_hashtags_fixas=state.get("max_hashtags_fixas"),
            exemplos=tuple(dict(e) for e in state.get("exemplos") or ()),
        )

    def textos(self) -> list[tuple[str, str]]:
        """(campo, texto) de tudo o que a validação de proibidas confere, com o caminho do erro
        na forma do contrato (`faca.3`, `exemplos.2.texto`). As proibidas ficam de fora."""
        saida: list[tuple[str, str]] = []
        if self.tom:
            saida.append(("tom", self.tom))
        for nome, itens in (("faca", self.faca), ("naoFaca", self.nao_faca),
                            ("vocabulario", self.vocabulario),
                            ("hashtagsFixas", self.hashtags_fixas)):
            saida.extend((f"{nome}.{i}", item) for i, item in enumerate(itens))
        saida.extend((f"exemplos.{i}.texto", e["texto"]) for i, e in enumerate(self.exemplos))
        return saida


@dataclass(frozen=True)
class GuiaBloco:
    campos: GuiaCampos
    version: int  # no rascunho do "testar", a versão base (0 se não havia guia salvo)
    nivel: Nivel
    rascunho: bool = False


@dataclass(frozen=True)
class GuiasEmVigor:
    perfil: GuiaBloco | None = None
    conta: GuiaBloco | None = None


@dataclass(frozen=True)
class GuiaEfetivo:
    """O que as garantias de código usam (R5, R6)."""

    proibidas: tuple[str, ...] = ()  # na forma do guia (perfil, depois conta, sem repetir)
    hashtags_fixas: tuple[str, ...] = ()  # perfil, depois conta; cortadas em `max` (inválido)
    max_hashtags_fixas: int = FIXAS_PADRAO
    emojis: Emojis | None = None
    emojis_preferidos: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()  # estado inválido herdado das fixas
    hashtags_evitar: tuple[str, ...] = ()  # spec 023: as "evitar" aceitas (`#…`), tiradas da saída

    @property
    def proibidas_normalizadas(self) -> tuple[str, ...]:
        return tuple(normalizar(p) for p in self.proibidas)


@dataclass(frozen=True)
class Conflito:
    campo: Literal["emojis", "faca", "naoFaca", "hashtagsFixas"]
    perfil: str
    conta: str
    mensagem: str


# ---- normalização e proibidas (R7) ----

_ESPACOS = re.compile(r"\s+")
_PALAVRA = re.compile(r"\w+")
_HASHTAG = re.compile(r"#(\w+)")


def normalizar(texto: str) -> str:
    """NFKD, sem marcas combinantes (acentos, cedilha), `casefold`, espaços colapsados."""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_marcas = "".join(c for c in decomposto if not unicodedata.combining(c))
    return _ESPACOS.sub(" ", sem_marcas.casefold()).strip()


def _padrao(termo: str) -> tuple[re.Pattern[str], str] | None:
    """Palavra inteira (`(?<!\\w)tok1\\W+tok2(?!\\w)`) e a forma sem espaços (para hashtags)."""
    tokens = _PALAVRA.findall(normalizar(termo))
    if not tokens:
        return None
    corpo = r"\W+".join(re.escape(t) for t in tokens)
    return re.compile(rf"(?<!\w){corpo}(?!\w)"), "".join(tokens)


def achar_proibidas(textos_: Iterable[str], termos: Iterable[str]) -> list[str]:
    """As proibidas (na forma dada) que aparecem em algum dos textos, na ordem de `termos`.

    Casa por palavra inteira sobre o texto normalizado ("pix" não casa "pixel"; termos de mais
    de uma palavra aceitam pontuação entre elas) e pela hashtag inteira igual ao termo sem
    espaços (`#compreja` × "compre já")."""
    normalizados = [normalizar(t) for t in textos_ if t]
    hashtags = {h for t in normalizados for h in _HASHTAG.findall(t)}
    achadas: list[str] = []
    vistos: set[str] = set()
    for termo in termos:
        chave = normalizar(termo)
        if chave in vistos:
            continue
        vistos.add(chave)
        padrao = _padrao(termo)
        if padrao is None:
            continue
        regex, junto = padrao
        if junto in hashtags or any(regex.search(t) for t in normalizados):
            achadas.append(termo)
    return achadas


def tamanho(campos: GuiaCampos) -> int:
    """A soma simples dos caracteres de todos os textos do guia (R2; o SPA mostra a mesma)."""
    listas = (campos.faca, campos.nao_faca, campos.vocabulario, campos.proibidas,
              campos.emojis_preferidos, campos.hashtags_fixas)
    return (len(campos.tom) + sum(len(i) for lista in listas for i in lista)
            + sum(len(e["texto"]) for e in campos.exemplos))


# ---- validação pura do save (data-model, passos 1 a 3) ----

def _lista(nome: str, itens: Sequence[str], max_itens: int, max_chars: int,
           erros: dict[str, str], chave: Callable[[str], str] = normalizar
           ) -> tuple[str, ...]:
    """Apara, descarta vazios, recusa longos e repetidos (normalizados). O índice do erro é o
    da lista enviada."""
    limpos: list[str] = []
    vistos: dict[str, int] = {}
    for i, bruto in enumerate(itens):
        item = bruto.strip()
        if not item:
            continue
        if len(item) > max_chars:
            erros[f"{nome}.{i}"] = f"no máximo {max_chars} caracteres"
            continue
        k = chave(item)
        if k in vistos:
            erros[f"{nome}.{i}"] = "item repetido"
            continue
        vistos[k] = i
        limpos.append(item)
    if len(limpos) > max_itens:
        erros.setdefault(nome, f"no máximo {max_itens} itens")
    return tuple(limpos)


def validar_limites(campos: GuiaCampos, nivel: Nivel) -> tuple[GuiaCampos, dict[str, str]]:
    """Passos 1, 2 e 4 do data-model (sem banco): limites, hashtags fixas normalizadas pela
    regra da 006 e o máximo de fixas. Devolve os campos limpos e os erros por campo."""
    erros: dict[str, str] = {}
    tom = campos.tom.strip()
    if len(tom) > TOM_MAX:
        erros["tom"] = f"no máximo {TOM_MAX} caracteres"
    faca = _lista("faca", campos.faca, REGRAS_ITENS, REGRA_MAX, erros)
    nao_faca = _lista("naoFaca", campos.nao_faca, REGRAS_ITENS, REGRA_MAX, erros)
    vocabulario = _lista("vocabulario", campos.vocabulario, VOCABULARIO_ITENS, TERMO_MAX, erros)
    proibidas = _lista("proibidas", campos.proibidas, PROIBIDAS_ITENS, TERMO_MAX, erros)
    for i, termo in enumerate(campos.proibidas):
        if termo.strip() and not _PALAVRA.search(normalizar(termo)):
            erros.setdefault(f"proibidas.{i}", "precisa ter ao menos uma letra ou número")
    preferidos = _lista("emojisPreferidos", campos.emojis_preferidos, EMOJIS_ITENS, EMOJI_MAX,
                        erros, chave=str)

    fixas: list[str] = []
    for i, bruto in enumerate(campos.hashtags_fixas):
        if not bruto.strip():
            continue
        tag = textos.normalizar_hashtag(bruto)
        if tag is None:
            erros[f"hashtagsFixas.{i}"] = "hashtag inválida"
        elif tag in fixas:
            erros[f"hashtagsFixas.{i}"] = "hashtag repetida"
        else:
            fixas.append(tag)
    teto = FIXAS_PERFIL_MAX if nivel == "perfil" else FIXAS_TETO
    if len(fixas) > teto:
        erros.setdefault("hashtagsFixas", f"no máximo {teto} hashtags fixas")

    maximo = campos.max_hashtags_fixas
    if nivel == "perfil" and maximo is not None:
        erros["maxHashtagsFixas"] = "o máximo de hashtags fixas é definido em cada conta"
    elif maximo is not None and not 0 <= maximo <= FIXAS_TETO:
        erros["maxHashtagsFixas"] = f"de 0 a {FIXAS_TETO}"

    exemplos: list[dict[str, str]] = []
    for i, e in enumerate(campos.exemplos):
        texto = (e.get("texto") or "").strip()
        if not texto:
            continue
        if e.get("tipo") not in TIPOS_EXEMPLO:
            erros[f"exemplos.{i}.tipo"] = "tipo inválido"
        elif len(texto) > EXEMPLO_MAX:
            erros[f"exemplos.{i}.texto"] = f"no máximo {EXEMPLO_MAX} caracteres"
        else:
            exemplos.append({"tipo": e["tipo"], "texto": texto})
    if len(exemplos) > EXEMPLOS:
        erros.setdefault("exemplos", f"no máximo {EXEMPLOS} exemplos")

    limpos = GuiaCampos(tom=tom, faca=faca, nao_faca=nao_faca, vocabulario=vocabulario,
                        proibidas=proibidas, emojis=campos.emojis, emojis_preferidos=preferidos,
                        hashtags_fixas=tuple(fixas), max_hashtags_fixas=maximo,
                        exemplos=tuple(exemplos))
    total = tamanho(limpos)
    if total > TOTAL_MAX:
        erros.setdefault("total", f"o guia tem {total} caracteres; o máximo é {TOTAL_MAX}")
    return limpos, erros


def proibidas_nos_campos(campos: GuiaCampos, termos: Sequence[str]) -> dict[str, str]:
    """Passo 3: nenhuma proibida (deste guia ∪ o outro nível) no tom, faça, não faça,
    vocabulário, exemplos nem nas hashtags fixas deste guia. `{"faca.1": "usa a palavra
    proibida 'x'"}`."""
    erros: dict[str, str] = {}
    if not termos:
        return erros
    for campo, texto in campos.textos():
        achadas = achar_proibidas([texto], termos)
        if achadas:
            erros[campo] = f"usa a palavra proibida '{achadas[0]}'"
    return erros


# ---- fusão e conflitos (R5, R6) ----

def _unir(*listas: Iterable[str], chave: Callable[[str], str] = str) -> tuple[str, ...]:
    vistos: dict[str, str] = {}
    for lista in listas:
        for item in lista:
            vistos.setdefault(chave(item), item)
    return tuple(vistos.values())


def maximo_fixas(conta: GuiaCampos | None) -> int:
    """`M(conta) = conta.max_hashtags_fixas ?? 5`."""
    if conta is None or conta.max_hashtags_fixas is None:
        return FIXAS_PADRAO
    return conta.max_hashtags_fixas


def fixas_somadas(perfil: GuiaCampos | None, conta: GuiaCampos | None) -> tuple[str, ...]:
    """`F(conta)`: as fixas do perfil, na ordem, depois as da conta, sem repetir."""
    return _unir(perfil.hashtags_fixas if perfil else (), conta.hashtags_fixas if conta else ())


def aviso_fixas(maximo: int) -> str:
    return (f"O guia tem mais hashtags fixas que o máximo desta conta ({maximo}); ficaram as "
            f"{maximo} primeiras. Revise o guia.")


def _campos(b: GuiaBloco | GuiaCampos | None) -> GuiaCampos | None:
    return b.campos if isinstance(b, GuiaBloco) else b


def fundir(perfil: GuiaBloco | GuiaCampos | None,
           conta: GuiaBloco | GuiaCampos | None) -> GuiaEfetivo:
    """Proibidas = união (a conta não libera o que o perfil proíbe); fixas = `F` cortada em `M`
    só no estado inválido herdado (com aviso); emojis e preferidos da conta, senão do perfil."""
    p, c = _campos(perfil), _campos(conta)
    maximo = maximo_fixas(c)
    fixas = fixas_somadas(p, c)
    avisos: tuple[str, ...] = ()
    if len(fixas) > maximo:
        fixas, avisos = fixas[:maximo], (aviso_fixas(maximo),)
    emojis = (c.emojis if c is not None and c.emojis is not None
              else p.emojis if p is not None else None)
    preferidos = (c.emojis_preferidos if c is not None and c.emojis_preferidos
                  else p.emojis_preferidos if p is not None else ())
    return GuiaEfetivo(
        proibidas=_unir(p.proibidas if p else (), c.proibidas if c else (), chave=normalizar),
        hashtags_fixas=fixas, max_hashtags_fixas=maximo, emojis=emojis,
        emojis_preferidos=preferidos, avisos=avisos)


def conflitos(perfil: GuiaBloco | GuiaCampos | None,
              conta: GuiaBloco | GuiaCampos | None) -> list[Conflito]:
    """Avisos do GET do guia da conta: emojis diferentes, o mesmo item em "faça" de um e "não
    faça" do outro, e as fixas acima do máximo (estado inválido herdado)."""
    p, c = _campos(perfil), _campos(conta)
    saida: list[Conflito] = []
    if p is not None and c is not None:
        if p.emojis is not None and c.emojis is not None and p.emojis != c.emojis:
            saida.append(Conflito(
                "emojis", EMOJIS_ROTULO[p.emojis], EMOJIS_ROTULO[c.emojis],
                f"O perfil diz emojis \"{EMOJIS_ROTULO[p.emojis]}\"; a conta diz "
                f"\"{EMOJIS_ROTULO[c.emojis]}\": vale a conta."))
        for itens_p, itens_c, campo, rotulo_p, rotulo_c in (
                (p.faca, c.nao_faca, "naoFaca", "faça", "não faça"),
                (p.nao_faca, c.faca, "faca", "não faça", "faça")):
            da_conta = {normalizar(i): i for i in itens_c}
            for item in itens_p:
                if normalizar(item) in da_conta:
                    saida.append(Conflito(
                        campo, item, da_conta[normalizar(item)],
                        f"\"{item}\" está em \"{rotulo_p}\" do perfil e em \"{rotulo_c}\" da "
                        "conta: vale a conta."))
    fixas = fixas_somadas(p, c)
    maximo = maximo_fixas(c)
    if len(fixas) > maximo:
        saida.append(Conflito(
            "hashtagsFixas", " ".join(p.hashtags_fixas if p else ()),
            " ".join(c.hashtags_fixas if c else ()),
            f"Perfil e conta somam {len(fixas)} hashtags fixas; o máximo desta conta é "
            f"{maximo}. Na geração ficam as {maximo} primeiras."))
    return saida


# ---- render (R4) ----

def render(bloco: GuiaBloco | GuiaCampos, so_proibidas: bool = False) -> str:
    """O conteúdo do bloco `<guia_*>` em rótulos fixos; seções vazias omitidas. Com
    `so_proibidas`, só a linha "Palavras proibidas:" (tipos `so_proibidas`, Q1). Pode voltar
    vazio (ex.: guia da conta só com o máximo de fixas)."""
    c = _campos(bloco)
    assert c is not None
    linhas: list[str] = []
    proibidas = f"Palavras proibidas: {', '.join(c.proibidas)}" if c.proibidas else ""
    if so_proibidas:
        return proibidas
    if c.tom:
        linhas.append(f"Tom de voz: {c.tom}")
    for rotulo, itens in (("Faça:", c.faca), ("Não faça:", c.nao_faca)):
        if itens:
            linhas.append(rotulo + "".join(f"\n- {i}" for i in itens))
    if c.vocabulario:
        linhas.append(f"Vocabulário da casa: {', '.join(c.vocabulario)}")
    if proibidas:
        linhas.append(proibidas)
    if c.emojis is not None or c.emojis_preferidos:
        emojis = EMOJIS_ROTULO[c.emojis] if c.emojis is not None else "não definido"
        if c.emojis_preferidos:
            emojis += f" (preferidos: {' '.join(c.emojis_preferidos)})"
        linhas.append(f"Emojis: {emojis}")
    if c.hashtags_fixas:
        linhas.append(f"Hashtags fixas: {' '.join(c.hashtags_fixas)}")
    if c.exemplos:
        linhas.append("Exemplos aprovados (imite o estilo, não copie):" + "".join(
            f"\n- [{EXEMPLO_ROTULO.get(e['tipo'], e['tipo'])}] {e['texto']}"
            for e in c.exemplos))
    return "\n".join(linhas)


# ---- leitura (a única função com sessão) ----

def linha(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None,
          lock: bool = False) -> IaGuia | None:
    """A linha do guia do perfil (`conta_id=None`) ou da conta, pela chave única."""
    stmt = select(IaGuia)
    if conta_id is None:
        stmt = stmt.where(IaGuia.perfil_id == perfil_id, IaGuia.conta_id.is_(None))
    else:
        stmt = stmt.where(IaGuia.conta_id == conta_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def bloco(row: IaGuia | None, nivel: Nivel) -> GuiaBloco | None:
    if row is None:
        return None
    campos = GuiaCampos.de_linha(row)
    return None if campos.vazio else GuiaBloco(campos=campos, version=row.version, nivel=nivel)


def em_vigor(db: Session, perfil_id: uuid.UUID, conta_id: uuid.UUID | None) -> GuiasEmVigor:
    """Os guias salvos do perfil e (se houver) da conta; um guia vazio conta como ausente."""
    perfil = bloco(linha(db, perfil_id, None), "perfil")
    conta = bloco(linha(db, perfil_id, conta_id), "conta") if conta_id is not None else None
    return GuiasEmVigor(perfil=perfil, conta=conta)


def como_rascunho(campos: GuiaCampos, nivel: Nivel, version_base: int) -> GuiaBloco:
    """O guia do formulário no "testar guia" (R10): vai como `<guia_em_teste>`."""
    return GuiaBloco(campos=campos, version=version_base, nivel=nivel, rascunho=True)

