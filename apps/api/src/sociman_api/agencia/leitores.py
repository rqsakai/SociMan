"""Leitores dos arquivos da agência (research R3): texto → estruturas, sem banco e sem rede.

Cada leitor procura as seções do molde (`_modelo/`) pelo número ou pelo título normalizado e os
rótulos pelo começo do nome. Faltou seção ou coluna obrigatória: `NaoReconhecido` com a lista do
que faltou, e o arquivo inteiro fica "não reconhecido" (nunca lido pela metade em silêncio).
"""

import re
from dataclasses import dataclass, field
from datetime import date

from sociman_api.agencia import markdown as md
from sociman_api.agencia.itens import impressao

STATUS_PERFIL = {"ativo": "ativo", "pausado": "pausado", "onboarding": "em_preparacao",
                 "pesquisa": "em_preparacao", "aguardando-aprovacao": "em_preparacao",
                 "aguardando aprovacao": "em_preparacao"}
STATUS_FONTE = ("autorizado", "programa-de-cortes", "pendente", "negado", "desconhecido")
SECOES_PERFIL = {1: "identidade", 2: "nicho", 3: "publico", 4: "posicionamento e tom",
                 5: "estilo visual", 6: "monetizacao", 7: "metas", 8: "decisoes e historico"}
SECOES_ANOTACAO = (3, 6, 7)  # público, monetização, metas: uma anotação por seção
NICHO_MAX = 200
TOM_MAX = 500
TERMO_MAX = 60
VOCABULARIO_MAX = 30
REGRA_MAX = 200
REGRAS_MAX = 10
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HANDLE = re.compile(r"@([A-Za-z0-9._-]{1,60})")
_PROPRIA = ("canal proprio", "conteudo proprio", "proprio do dono")
_CITADA = re.compile(r"(?:shared/)?((?:perfis/[^\s`'\"()]+/)?assets/[^\s`'\"()]+\.(?:png|jpe?g|webp))",
                     re.IGNORECASE)


class NaoReconhecido(Exception):
    def __init__(self, faltou: list[str]):
        super().__init__(", ".join(faltou))
        self.faltou = faltou


def data_valida(texto: str) -> str | None:
    """`AAAA-MM-DD` (gravada como está, America/Sao_Paulo); None se inválida."""
    t = md.limpar(texto)[:10]
    if not _DATA.match(t):
        return None
    try:
        date.fromisoformat(t)
    except ValueError:
        return None
    return t


def _secao(secoes: list[md.Secao], n: int, nome: str) -> md.Secao | None:
    for s in secoes:
        if s.nivel == 2 and (re.match(rf"^{n}\s*[.)-]?\s", s.titulo) or s.titulo == nome
                             or s.titulo.startswith(nome)):
            return s
    return None


def _campo(campos: dict[str, str], *prefixos: str) -> str | None:
    for chave, valor in campos.items():
        if any(chave.startswith(p) for p in prefixos):
            return valor
    return None


def _valor(campos: dict[str, str], *prefixos: str) -> str:
    v = _campo(campos, *prefixos)
    return "" if v is None or md.vazio(v) else md.limpar(v)


def _corpo_util(corpo: str) -> str:
    """O corpo sem os campos de valor vazio, sem tabelas vazias e sem linhas em branco extras."""
    saida = []
    linhas = corpo.splitlines()
    for i, ln in enumerate(linhas):
        s = ln.strip()
        if not s:
            if saida and saida[-1]:
                saida.append("")
            continue
        m = re.match(r"^[-*]\s+(.*)$", s)
        par = md.rotulo_valor(m.group(1)) if m else None
        if par is not None and md.vazio(par[1]):
            continue
        if s.startswith("|"):
            prox = linhas[i + 1].strip() if i + 1 < len(linhas) else ""
            ant = linhas[i - 1].strip() if i else ""
            separador = bool(md.SEPARADOR.match(s))
            cabecalho_sem_linhas = (md.SEPARADOR.match(prox) is not None
                                    and not (i + 2 < len(linhas)
                                             and linhas[i + 2].strip().startswith("|")))
            if cabecalho_sem_linhas or (separador and not prox.startswith("|")
                                        and ant.startswith("|")):
                continue
        saida.append(ln.rstrip())
    return "\n".join(saida).strip()


# ---- INDEX.md ----

@dataclass(frozen=True)
class IndexLinha:
    linha: int
    slug: str
    nome: str
    status: str


def ler_index(texto: str) -> list[IndexLinha]:
    for t in md.tabelas(texto):
        i_slug, i_nome = md.coluna(t.cabecalho, "slug"), md.coluna(t.cabecalho, "nome")
        i_status = md.coluna(t.cabecalho, "status")
        if i_slug is None:
            continue
        return [IndexLinha(n, md.limpar(c[i_slug]),
                           md.limpar(c[i_nome]) if i_nome is not None else "",
                           md.normalizar(c[i_status]) if i_status is not None else "")
                for n, c in t.linhas if md.limpar(c[i_slug])]
    raise NaoReconhecido(["tabela com a coluna slug"])


# ---- perfil.md ----

@dataclass(frozen=True)
class ContaLida:
    plataforma: str  # youtube | tiktok
    bruto: str
    handle: str | None
    url: str | None
    linha: int


@dataclass(frozen=True)
class TrechoLido:
    trecho: str  # legível: "§3. Público", "§8 · 2026-09-25"
    chave: str  # parte estável da chave: "3", "8:<data>:<sha8>", "nicho"
    texto: str
    linha: int


@dataclass
class PerfilLido:
    slug_pasta: str
    nome: str
    idioma: str
    status_md: str
    status: str | None  # mapeado; None = desconhecido
    nicho: str  # completo (o corte em 200 fica na conciliação)
    linha_identidade: int
    linha_nicho: int
    linha_guia: int
    contas: list[ContaLida] = field(default_factory=list)
    tom: str = ""
    vocabulario: list[str] = field(default_factory=list)
    nao_faca: list[str] = field(default_factory=list)
    anotacoes: list[TrechoLido] = field(default_factory=list)
    citadas: list[str] = field(default_factory=list)  # caminhos relativos a `shared/`


def separar_expressoes(valor: str) -> list[str]:
    """"A" · "B" / C → [A, B, C]: aspas primeiro; senão `·`, ` / `, `;` ou `,`. Sem as notas
    entre parênteses; cada termo até 60 caracteres; até 30 termos."""
    sem_notas = re.sub(r"\([^)]*\)", " ", valor)
    _, traco, depois = sem_notas.partition(" — ")
    if traco and re.search(r"[\"“”]", depois):  # "Família de frases… — "A" / "B"": só a lista
        sem_notas = depois
    aspas = re.findall(r"[\"“”]([^\"“”]+)[\"“”]", sem_notas)
    partes = aspas or re.split(r"\s*(?:·|•|\s/\s|;|,)\s*", sem_notas)
    out: list[str] = []
    for p in partes:
        t = md.limpar(p).strip(" .\"'“”")
        if t and not md.vazio(t) and t.lower() not in (x.lower() for x in out):
            out.append(t[:TERMO_MAX].rstrip())
    return out[:VOCABULARIO_MAX]


def separar_regras(valor: str) -> list[str]:
    """Proibido → "não faça": um item por vírgula ou `;` fora de parênteses; até 10 × 200."""
    partes, atual, nivel = [], [], 0
    for c in valor:
        if c == "(":
            nivel += 1
        elif c == ")":
            nivel = max(0, nivel - 1)
        if c in ",;" and nivel == 0:
            partes.append("".join(atual))
            atual = []
        else:
            atual.append(c)
    partes.append("".join(atual))
    out = [md.limpar(p).strip(" .")[:REGRA_MAX] for p in partes]
    return [p for p in out if p and not md.vazio(p)][:REGRAS_MAX]


def _conta(plataforma: str, bruto: str, linha: int) -> ContaLida | None:
    if md.vazio(bruto) or md.normalizar(bruto).startswith(("nenhum", "nao tem", "sem ")):
        return None
    host = "youtube.com" if plataforma == "youtube" else "tiktok.com"
    url = next((u for u in md.links(bruto) if host in u.lower()), None)
    if url is not None and not url.lower().startswith("http"):
        url = f"https://{url}"
    m = _HANDLE.search(bruto.split("http")[0]) or _HANDLE.search(bruto)
    handle = m.group(1).rstrip(".").lower() if m else None
    return ContaLida(plataforma, md.limpar(bruto), handle, url, linha)


def ler_perfil(texto: str, slug_pasta: str) -> PerfilLido:
    front, resto, desloc = md.frontmatter(texto)
    secoes = md.secoes(resto, desloc)
    achadas = {n: _secao(secoes, n, nome) for n, nome in SECOES_PERFIL.items()}
    faltou = [f"seção {n}. {nome}" for n, nome in SECOES_PERFIL.items() if achadas[n] is None]
    if faltou:
        raise NaoReconhecido(faltou)
    ident = md.campos(achadas[1].corpo)  # type: ignore[union-attr]
    nicho = md.campos(achadas[2].corpo)  # type: ignore[union-attr]
    tom = md.campos(achadas[4].corpo)  # type: ignore[union-attr]
    nome = _valor(ident, "nome do perfil")
    if not nome:
        raise NaoReconhecido(["campo \"Nome do perfil\" (§1)"])
    status_md = md.normalizar(front.get("status", ""))
    perfil = PerfilLido(
        slug_pasta=slug_pasta, nome=nome, idioma=_valor(ident, "idioma") or "pt-BR",
        status_md=status_md, status=STATUS_PERFIL.get(status_md),
        nicho=_valor(nicho, "nicho principal"),
        linha_identidade=achadas[1].linha, linha_nicho=achadas[2].linha,  # type: ignore[union-attr]
        linha_guia=achadas[4].linha,  # type: ignore[union-attr]
    )
    for plataforma, rotulo_ in (("youtube", "@ no youtube"), ("tiktok", "@ no tiktok")):
        bruto = _campo(ident, rotulo_)
        if bruto is not None:
            conta = _conta(plataforma, bruto, achadas[1].linha)  # type: ignore[union-attr]
            if conta is not None:
                perfil.contas.append(conta)
    perfil.tom = _valor(tom, "tom")[:TOM_MAX]
    perfil.vocabulario = separar_expressoes(_valor(tom, "expressoes da casa"))
    perfil.nao_faca = separar_regras(_valor(tom, "proibido"))

    for n in SECOES_ANOTACAO:
        s = achadas[n]
        corpo = _corpo_util(s.corpo)  # type: ignore[union-attr]
        if corpo:
            perfil.anotacoes.append(TrechoLido(f"§{s.titulo_original}", str(n),  # type: ignore[union-attr]
                                               f"perfil.md §{s.titulo_original}\n\n{corpo}",  # type: ignore[union-attr]
                                               s.linha))  # type: ignore[union-attr]
    dec = achadas[8]
    for t in md.tabelas(dec.corpo, dec.linha):  # type: ignore[union-attr]
        i_data, i_dec = md.coluna(t.cabecalho, "data"), md.coluna(t.cabecalho, "decisao")
        i_pq = md.coluna(t.cabecalho, "por que", "porque")
        if i_data is None or i_dec is None:
            continue
        for n, c in t.linhas:
            decisao = md.limpar(c[i_dec])
            if not decisao or md.vazio(decisao):
                continue
            quando = md.limpar(c[i_data])
            porque = md.limpar(c[i_pq]) if i_pq is not None else ""
            linha_txt = " | ".join(c)
            sha8 = impressao(linha_txt)[:8]
            corpo = f"Decisão: {decisao}" + (f"\nPor quê: {porque}" if porque else "")
            perfil.anotacoes.append(TrechoLido(
                f"§8 · {quando}", f"8:{quando}:{sha8}",
                f"perfil.md §{dec.titulo_original} · {quando}\n\n{corpo}", n))  # type: ignore[union-attr]
        break
    perfil.citadas = sorted({_rel_citada(m.group(1), slug_pasta) for m in _CITADA.finditer(resto)})
    return perfil


def _rel_citada(caminho: str, slug: str) -> str:
    return caminho if caminho.startswith("perfis/") else f"perfis/{slug}/{caminho}"


# ---- fontes.md ----

@dataclass(frozen=True)
class FonteLida:
    linha: int
    criador: str
    canal: str  # a célula original
    status_md: str  # normalizado (`programa-de-cortes`…)
    evidencia: str
    regras: str
    confirmado_por: str
    data: str
    propria: bool


def ler_fontes(texto: str) -> list[FonteLida]:
    for t in md.tabelas(texto):
        i_criador, i_canal = md.coluna(t.cabecalho, "criador"), md.coluna(t.cabecalho, "canal")
        i_status = md.coluna(t.cabecalho, "status")
        if i_criador is None or i_canal is None or i_status is None:
            continue
        i_ev = md.coluna(t.cabecalho, "evidencia")
        i_regras = md.coluna(t.cabecalho, "regras")
        i_conf = md.coluna(t.cabecalho, "confirmado")
        i_data = md.coluna(t.cabecalho, "data")

        def cel(c: list[str], i: int | None) -> str:
            return "" if i is None or md.vazio(c[i]) else md.limpar(c[i])

        out = []
        for n, c in t.linhas:
            if md.vazio(c[i_criador]) and md.vazio(c[i_canal]):
                continue
            linha_norm = md.normalizar(" ".join(c))
            out.append(FonteLida(
                linha=n, criador=cel(c, i_criador), canal=cel(c, i_canal),
                status_md=md.normalizar(c[i_status]).strip(" ."), evidencia=cel(c, i_ev),
                regras=cel(c, i_regras), confirmado_por=cel(c, i_conf), data=cel(c, i_data),
                propria=any(p in linha_norm for p in _PROPRIA)))
        return out
    raise NaoReconhecido(["tabela com as colunas criador, canal e status"])


# ---- pesquisa.md e ideias-gravacao.md ----

def ler_pesquisa(texto: str) -> list[TrechoLido]:
    """Uma anotação por seção `##` (com as subseções), sem as vazias do molde."""
    _, resto, desloc = md.frontmatter(texto)
    out = []
    for s in md.secoes(resto, desloc):
        if s.nivel != 2:
            continue
        corpo = _corpo_util(s.corpo)
        if corpo:
            out.append(TrechoLido(f"§{s.titulo_original}", s.titulo,
                                  f"pesquisa.md §{s.titulo_original}\n\n{corpo}", s.linha))
    return out


_PAUTA = re.compile(r"^(\d+)[.)]\s+(.*)$")


def ler_ideias(texto: str) -> list[TrechoLido]:
    """Uma anotação por pauta numerada dentro de cada seção `##`."""
    _, resto, desloc = md.frontmatter(texto)
    out = []
    for s in md.secoes(resto, desloc):
        if s.nivel != 2:
            continue
        pautas: list[tuple[str, int, list[str]]] = []  # (número, linha, linhas do texto)
        aberta = False
        for i, ln in enumerate(s.corpo.splitlines()):
            m = _PAUTA.match(ln.strip()) if not ln.startswith(("  ", "\t")) else None
            if m:
                pautas.append((m.group(1), s.linha + 1 + i, [m.group(2).strip()]))
                aberta = True
            elif aberta and ln.strip() and ln.startswith(("  ", "\t")):
                pautas[-1][2].append(ln.strip())
            elif ln.strip():
                aberta = False
        for num, linha, partes in pautas:
            corpo = "\n".join(partes).strip()
            out.append(TrechoLido(f"§{s.titulo_original} · {num}", f"{s.titulo}:{num}",
                                  f"ideias-gravacao.md §{s.titulo_original} · pauta {num}"
                                  f"\n\n{corpo}", linha))
    return out


# ---- registro-clipes.md ----

@dataclass(frozen=True)
class RegistroLinha:
    linha: int
    id: str
    data: str | None  # None = inválida
    fonte: str
    titulo: str
    produto: str
    obs: str


def ler_registro(texto: str) -> dict[str, RegistroLinha]:
    for t in md.tabelas(texto):
        i_id, i_data = md.coluna(t.cabecalho, "id"), md.coluna(t.cabecalho, "data")
        i_titulo = md.coluna(t.cabecalho, "titulo")
        if i_id is None or i_data is None or i_titulo is None:
            continue
        i_fonte, i_prod = md.coluna(t.cabecalho, "fonte"), md.coluna(t.cabecalho, "produto")
        i_obs = md.coluna(t.cabecalho, "obs")

        def cel(c: list[str], i: int | None) -> str:
            return "" if i is None or md.vazio(c[i]) else md.limpar(c[i])

        out = {}
        for n, c in t.linhas:
            ident = cel(c, i_id)
            if ident and ident not in out:
                out[ident] = RegistroLinha(n, ident, data_valida(c[i_data]), cel(c, i_fonte),
                                           cel(c, i_titulo), cel(c, i_prod), cel(c, i_obs))
        return out
    raise NaoReconhecido(["tabela com as colunas ID, Data e Título"])


# ---- shop/persona.md ----

@dataclass(frozen=True)
class ImagemPersona:
    arquivo: str  # nome do arquivo em `shop/persona/`
    look: str
    uso: str
    linha: int


@dataclass
class PersonaLida:
    nome: str
    prompt: str
    voz: str
    regras: str
    linha: int
    imagens: list[ImagemPersona] = field(default_factory=list)
    cenarios: list[tuple[str, str, int]] = field(default_factory=list)  # (nome, prompt, linha)


def _texto_secao(corpo: str) -> str:
    linhas = [md.limpar(re.sub(r"^\s*(?:[-*>]\s*)", "", ln)) for ln in corpo.splitlines()]
    return "\n".join(ln for ln in linhas if ln).strip()


def ler_persona(texto: str) -> PersonaLida:
    _, resto, desloc = md.frontmatter(texto)
    secoes = md.secoes(resto, desloc)
    titulo = next((s for s in secoes if s.nivel == 1), None)
    desc = next((s for s in secoes if s.titulo.startswith("descricao para prompt")), None)
    faltou = (["título \"# Persona: <nome>\""] if titulo is None else []) \
        + (["seção \"Descrição para prompts\""] if desc is None else [])
    if faltou:
        raise NaoReconhecido(faltou)
    nome = md.limpar(titulo.titulo_original.split(":", 1)[-1])  # type: ignore[union-attr]
    citacao = [ln.strip()[1:].strip() for ln in desc.corpo.splitlines()  # type: ignore[union-attr]
               if ln.strip().startswith(">")]
    prompt = " ".join(citacao) if citacao else _texto_secao(desc.corpo)  # type: ignore[union-attr]
    voz = next((s for s in secoes if s.titulo.startswith("voz")), None)
    regras = next((s for s in secoes if s.titulo.startswith("regras de imagem")), None)
    p = PersonaLida(nome=nome, prompt=prompt.strip(), linha=titulo.linha,  # type: ignore[union-attr]
                    voz=_texto_secao(voz.corpo) if voz else "",
                    regras=_texto_secao(regras.corpo) if regras else "")
    cen = next((s for s in secoes if s.titulo.startswith("cenario")), None)
    if cen is not None:
        for i, ln in enumerate(cen.corpo.splitlines()):
            m = re.match(r"^\s*[-*]\s+(.*)$", ln)
            par = md.rotulo_valor(m.group(1)) if m else None
            if par is not None and not md.vazio(par[1]):
                p.cenarios.append((md.limpar(par[0]), md.limpar(par[1]), cen.linha + 1 + i))
    img = next((s for s in secoes if s.titulo.startswith("imagens de referencia")), None)
    if img is not None:
        for t in md.tabelas(img.corpo, img.linha):
            i_look, i_arq = md.coluna(t.cabecalho, "look"), md.coluna(t.cabecalho, "arquivo")
            i_uso = md.coluna(t.cabecalho, "uso")
            if i_arq is None:
                continue
            for n, c in t.linhas:
                m = re.search(r"([\w.-]+\.(?:png|jpe?g|webp))", c[i_arq], re.IGNORECASE)
                if m:
                    p.imagens.append(ImagemPersona(
                        m.group(1), md.limpar(c[i_look]) if i_look is not None else "",
                        md.limpar(c[i_uso]) if i_uso is not None else "", n))
            break
    return p
