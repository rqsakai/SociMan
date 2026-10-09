"""Claude falso para os textos de postagem (T061): `httpx2.MockTransport` passado ao SDK por
`http_client` (o SDK 1.x usa o `httpx2`). Nenhuma chamada real e nenhuma chave de verdade.

Uso:
    from fakes.anthropic_fake import anthropic_fake  # noqa: F401  (fixture)

    anthropic_fake.responder("fora_dos_limites", "valida")  # uma resposta por chamada
    client = anthropic_fake.client()                       # IaClient com o fake
    anthropic_fake.bodies                                   # corpos JSON enviados

Cada item de `responder` é o nome de um arquivo de `tests/fixtures/anthropic/` (200), um dict
(200), `"timeout"` (o transporte levanta `ReadTimeout`) ou `(status, fixture_ou_dict)`. Sem
resposta enfileirada, devolve uma resposta válida **para o schema pedido** (spec 008: `proposta`,
`itens` ou os textos da postagem; `valida` na 006).

Spec 008: `anthropic_fake.ia_client()` devolve o `IaClient` com o fake; `mensagem(dados,
usage=..., model=...)` monta respostas com cache e `iterations` de fallback.

Spec 023 (R15): a resposta padrão cobre `taxonomia` (os nomes mais frequentes dos posts),
`classificacao` (o 1º tema da `<taxonomia>` cujo nome aparece no post) e `analise` (2 hipóteses
com os 2 primeiros posts enviados). "id inválido" na `<instrucao>` devolve um id fora do conjunto;
`anthropic_fake.imagens` conta os blocos `image` de cada chamada.

Spec 012 (T012): a resposta padrão cobre a ficha do produto (`ficha(...)`, o `shorts_canelado`
determinístico, uma cor por foto enviada). Na `<instrucao>`: "sem flat" devolve
`precisa_flat = false`; "recusa" devolve `stop_reason = refusal`; "ficha inválida" devolve um
`material_en` de 6 palavras (fora do limite, nas duas tentativas). `anthropic_fake.fichas` conta
as chamadas de ficha (SC-002).

Spec 025 (T010): a resposta padrão cobre a checagem de identidade do avatar (`identidade(...)`):
as notas vêm de `anthropic_fake.notas_identidade` (padrão 8 em cada slot) e a descrição de
`anthropic_fake.descricao_identidade` (padrão: 50 palavras em inglês).

Spec 017: a resposta padrão cobre os formatos `guia` (`guia(...)`) e `variacoes`
(`variacoes(...)`, 3 textos de postagem **sem** hashtags fixas: quem inclui é o servidor);
`anthropic_fake.systems` devolve o `system` enviado em cada chamada (texto dos blocos) e
`anthropic_fake.system_blocos` os blocos crus (para conferir a ordem e o `cache_control`).
"""

import json
import re
from collections import Counter, deque
from pathlib import Path
from typing import Any

import httpx2
import pytest

from sociman_api.ia.cliente import IaClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "anthropic"
CHAVE_TESTE = "chave-de-teste-do-claude"  # não casa com o padrão `sk-ant-…` do check:secrets


def fixture(nome: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{nome}.json").read_text())


def mensagem(dados: dict[str, Any], stop_reason: str = "end_turn",
             usage: dict[str, Any] | None = None, model: str | None = None) -> dict[str, Any]:
    """Resposta 200 com `dados` como o JSON da saída estruturada."""
    base = fixture("valida")
    base["content"] = [{"type": "text", "text": json.dumps(dados, ensure_ascii=False)}]
    base["stop_reason"] = stop_reason
    if usage is not None:
        base["usage"] = usage
    if model is not None:
        base["model"] = model
    return base


def texto(proposta: str, explicacao: str = "Deixei mais direto.",
          avisos: list[str] | None = None, **kw: Any) -> dict[str, Any]:
    return mensagem({"proposta": proposta, "explicacao": explicacao, "avisos": avisos or []},
                    **kw)


def itens(*valores: str, explicacao: str = "Sugestões novas.",
          avisos: list[str] | None = None, **kw: Any) -> dict[str, Any]:
    return mensagem({"itens": list(valores), "explicacao": explicacao, "avisos": avisos or []},
                    **kw)


def guia(explicacao: str = "Montei o guia a partir da descrição.",
         avisos: list[str] | None = None, **campos: Any) -> dict[str, Any]:
    dados = {"tom": "Descontraído e direto, como quem conversa com um amigo.",
             "faca": ["Fale com o público de você"], "nao_faca": ["Não use gírias ofensivas"],
             "vocabulario": ["achadinho"], "proibidas": ["clickbait"], "emojis": "moderado",
             "emojis_preferidos": ["✨"]} | campos
    return mensagem(dados | {"explicacao": explicacao, "avisos": avisos or []})


def variacoes(*titulos: str, hashtags: list[str] | None = None,
              explicacao: str = "Três versões com o guia.",
              avisos: list[str] | None = None, **kw: Any) -> dict[str, Any]:
    titulos = titulos or ("Primeira versão do título", "Segunda versão do título",
                          "Terceira versão do título")
    tags = hashtags or ["#tecnologia", "#dicas", "#produtividade"]
    return mensagem({"variacoes": [{"titulo": t, "descricao": f"Descrição de {t.lower()}.",
                                    "hashtags": list(tags)} for t in titulos],
                     "explicacao": explicacao, "avisos": avisos or []}, **kw)


def campos_cena(explicacao: str = "Ajustei a cena.", avisos: list[str] | None = None,
                **campos: str) -> dict[str, Any]:
    """Spec 010 (`cena.ajustar`): os 4 campos da cena."""
    dados = {"acao": "lifts the lid slowly and smiles at the product",
             "camera": "eye level, shallow depth of field", "estilo": "warm soft light",
             "audio": "gentle kitchen ambience"} | campos
    return mensagem(dados | {"explicacao": explicacao, "avisos": avisos or []})


CORES_FICHA = (("black", "preto"), ("heather grey", "cinza mescla"), ("navy blue", "azul-marinho"),
               ("off-white", "off-white"), ("olive green", "verde-oliva"), ("wine red", "vinho"))


def ficha(n_fotos: int = 1, precisa_flat: bool = True, material_en: str = "ribbed knit",
          **campos: Any) -> dict[str, Any]:
    """Spec 012: a ficha do `shorts_canelado` (como no teste do pipeline)."""
    dados = {
        "nome_comercial": "Short canelado cintura alta",
        "categoria": "roupa > shorts",
        "material_en": material_en,
        "material_pt": "malha canelada",
        "cores": [{"foto": i, "en": CORES_FICHA[(i - 1) % 6][0],
                   "pt": CORES_FICHA[(i - 1) % 6][1]} for i in range(1, n_fotos + 1)],
        "formato_corte": "high-waisted biker-style shorts, mid-thigh length",
        "detalhes_visiveis": ["small white 'LS' logo on the left leg hem",
                              "wide elastic waistband"],
        "tamanho_relativo": "all variants are identical in size and cut",
        "descricao_prompt": "High-waisted ribbed knit biker shorts with a small 'LS' logo on "
                            "the left leg.",
        "cuidados": ["O tecido é malha canelada, não jeans",
                     "O logo LS fica na perna esquerda"],
        "descricao_venda": "Short canelado de cintura alta, confortável para o dia a dia. "
                           "Tem logo LS discreto na perna.",
        "precisa_flat": precisa_flat,
        "explicacao": "Ficha a partir das fotos.", "avisos": [],
    } | campos
    return mensagem(dados)


def _ficha(body: dict[str, Any]) -> dict[str, Any]:
    texto = _texto_user(body)
    pedido = texto.split("<instrucao>")[-1].split("</instrucao>")[0].lower()
    n = sum(b.get("type") == "image" for b in body["messages"][0]["content"]
            if isinstance(b, dict))
    if "recusa" in pedido:
        return fixture("recusa")
    if "ficha inválida" in pedido:
        return ficha(n or 1, material_en="soft stretchy ribbed cotton knit fabric")
    return ficha(n or 1, precisa_flat="sem flat" not in pedido)


SLOTS_NOTA = ("rosto_frontal", "rosto_34_esq", "rosto_34_dir", "corpo_base")
DESCRICAO_IDENTIDADE = (
    "Adult woman in her early thirties with warm medium-brown skin, an oval face, almond-shaped "
    "dark brown eyes under softly arched eyebrows, a straight medium nose, full lips, shoulder-"
    "length dark curly hair with defined ringlets parted slightly to the left, an average build "
    "with rounded shoulders, and a small beauty mark above the right corner of the upper lip.")


def identidade(notas: dict[str, int] | None = None, descricao: str = DESCRICAO_IDENTIDADE,
               **kw: Any) -> dict[str, Any]:
    """Spec 025: as notas por slot e a descrição fixa para prompts."""
    notas = {s: 8 for s in SLOTS_NOTA} | (notas or {})
    return mensagem({"notas": [{"slot": s, "nota": n, "observacao": "Mesmo rosto, mesma pele."}
                               for s, n in notas.items()],
                     "descricao_prompt": descricao, "explicacao": "Conferi as 5 imagens.",
                     "avisos": []}, **kw)


def _texto_user(body: dict[str, Any]) -> str:
    conteudo = body["messages"][0]["content"]
    if isinstance(conteudo, str):
        return conteudo
    return "\n".join(b.get("text", "") for b in conteudo if b.get("type") == "text")


ID_INVALIDO = "00000000-0000-4000-8000-000000000000"
_TAXONOMIA = re.compile(r"- id: ([0-9a-f-]{36}) \| ([^|\n]+)")
_POST = re.compile(r'<post id="([0-9a-f-]{36})"[^>]*>\n(.*?)\n</post>', re.DOTALL)


def taxonomia(*nomes: str, **kw: Any) -> dict[str, Any]:
    nomes = nomes or ("Marvel", "Games", "Tecnologia")
    return mensagem({"temas": [{"nome": n, "descricao": f"Posts sobre {n.lower()}.",
                                "palavras_chave": [n.lower()]} for n in nomes],
                     "explicacao": "Temas a partir dos posts.", "avisos": []}, **kw)


def classificacao(tema_id: str | None, estilo: str | None = "pergunta",
                  secundarios: list[str] | None = None, sugestao: str | None = None,
                  **kw: Any) -> dict[str, Any]:
    return mensagem({"tema_id": tema_id, "secundarios": secundarios or [],
                     "estilo_gancho": estilo, "justificativa": "O post fala do tema.",
                     "sugestao_tema": sugestao, "explicacao": "Classifiquei.", "avisos": []},
                    **kw)


def analise(*hipoteses: tuple[str, list[str]], **kw: Any) -> dict[str, Any]:
    return mensagem({"hipoteses": [{"texto": t, "posts_ids": ids, "contraste": "Os outros não.",
                                    "n": len(ids)} for t, ids in hipoteses],
                     "explicacao": "Comparei os grupos.", "avisos": []}, **kw)


def _aprendizado(props: dict[str, Any], body: dict[str, Any]) -> dict[str, Any] | None:
    texto = _texto_user(body)
    invalido = "id inválido" in texto.split("<instrucao>")[-1]
    if "temas" in props:
        palavras = re.findall(r"#(\w+)", texto) or ["geral", "dicas", "novidades"]
        nomes = [w.capitalize() for w, _ in Counter(palavras).most_common(5)]
        while len(nomes) < 3:
            nomes.append(f"Tema {len(nomes) + 1}")
        return taxonomia(*nomes)
    if "tema_id" in props:
        if invalido:
            return classificacao(ID_INVALIDO, sugestao="Tema inventado")
        temas = _TAXONOMIA.findall(texto)
        post = (_POST.findall(texto) or [("", texto)])[0][1].lower()
        post += " " + texto.split("</post>")[-1].lower()
        escolhido = next((tid for tid, nome in temas if nome.strip().lower() in post), None)
        return classificacao(escolhido)
    if "hipoteses" in props:
        ids = [i for i, _ in _POST.findall(texto)]
        if invalido:
            return analise(("Hipótese com post de fora", [ID_INVALIDO]),
                           ("Gancho com pergunta prende mais", ids[:1]))
        return analise(("Gancho com pergunta prende mais", ids[:2]),
                       ("Cortes curtos rendem melhor", ids[:1]))
    return None


def _padrao(body: dict[str, Any]) -> dict[str, Any]:
    """Uma resposta válida para o schema pedido (sem fila)."""
    props = (body.get("output_config", {}).get("format", {}).get("schema", {})
             .get("properties", {}))
    if (resposta := _aprendizado(props, body)) is not None:  # spec 023
        return resposta
    if "material_en" in props:  # spec 012
        return _ficha(body)
    if "descricao_prompt" in props and "notas" in props:  # spec 025
        return identidade(_NOTAS.get("atual"), _NOTAS.get("descricao", DESCRICAO_IDENTIDADE))
    if "proposta" in props:
        return texto("Texto proposto pela IA.")
    if "variacoes" in props:
        return variacoes()
    if "tom" in props:
        return guia()
    if "acao" in props:  # spec 010
        return campos_cena()
    if "itens" in props:
        return itens("#dica", "#casa", "#achadinhos")
    base = fixture("valida")
    if "explicacao" in props:
        dados = json.loads(base["content"][0]["text"])
        return mensagem(dados | {"explicacao": "Textos para o clipe.", "avisos": []})
    return base


_NOTAS: dict[str, Any] = {}


class AnthropicFake:
    @property
    def notas_identidade(self) -> dict[str, int] | None:
        return _NOTAS.get("atual")

    @notas_identidade.setter
    def notas_identidade(self, valor: dict[str, int] | None) -> None:
        _NOTAS["atual"] = valor

    @property
    def descricao_identidade(self) -> str:
        return _NOTAS.get("descricao", DESCRICAO_IDENTIDADE)

    @descricao_identidade.setter
    def descricao_identidade(self, valor: str) -> None:
        _NOTAS["descricao"] = valor

    def __init__(self) -> None:
        _NOTAS.clear()
        self.fila: deque[Any] = deque()
        self.requests: list[httpx2.Request] = []
        self.transport = httpx2.MockTransport(self._handle)

    def responder(self, *itens: Any) -> None:
        self.fila.extend(itens)

    def client(self, **kwargs: Any) -> IaClient:
        """Desde a spec 008 o cliente do Claude é um só (o `TextosClient` da 006 virou este)."""
        return self.ia_client(**kwargs)

    def ia_client(self, **kwargs: Any) -> IaClient:
        kwargs.setdefault("max_retries", 0)
        return IaClient(api_key=CHAVE_TESTE, transport=self.transport, **kwargs)

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]

    @property
    def imagens(self) -> list[int]:
        """Spec 023: quantos blocos `image` cada chamada levou."""
        out = []
        for b in self.bodies:
            conteudo = b["messages"][0]["content"]
            out.append(0 if isinstance(conteudo, str)
                       else sum(x.get("type") == "image" for x in conteudo))
        return out

    @property
    def fichas(self) -> int:
        """Spec 012 (SC-002): quantas chamadas pediram a ficha do produto."""
        return sum("material_en" in (b.get("output_config", {}).get("format", {})
                                     .get("schema", {}).get("properties", {}))
                   for b in self.bodies)

    @property
    def system_blocos(self) -> list[list[dict[str, Any]]]:
        return [b.get("system") or [] for b in self.bodies]

    @property
    def systems(self) -> list[str]:
        """O `system` de cada chamada, com os blocos juntos por linha em branco."""
        return ["\n\n".join(bl.get("text", "") for bl in blocos)
                for blocos in self.system_blocos]

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        item = self.fila.popleft() if self.fila else _padrao(json.loads(request.content))
        if item == "timeout":
            raise httpx2.ReadTimeout("timeout do fake", request=request)
        status = 200
        if isinstance(item, tuple):
            status, item = item
        body = fixture(item) if isinstance(item, str) else item
        return httpx2.Response(status, json=body, headers={"request-id": "req_fake"})


@pytest.fixture
def anthropic_fake() -> AnthropicFake:
    return AnthropicFake()
