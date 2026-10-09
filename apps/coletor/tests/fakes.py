"""Fakes dos testes: SociMan falso (`httpx.MockTransport`), relógio simulado e navegador falso.

Nada aqui toca a rede real nem usa conta de ninguém. URLs e dados são sintéticos.
"""

from __future__ import annotations

import email
import email.policy
import gzip
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs

import httpx

from sociman_coletor.redes.base import Interceptada
from sociman_coletor.redes.tiktok_shop import AdaptadorTikTokShop

HOST_REDE = "https://rede.sintetica.test"
HOST_IMG = "https://img.sintetica.test"
INTERCEPTAR_TESTE = (re.compile(r"/api-sintetica/"),)
IMAGENS_HOSTS_TESTE = frozenset({"img.sintetica.test", "127.0.0.1", "localhost"})

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x03\x00\x08\xfc\x02\xfe\xa7"
    b"\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def rede_teste() -> AdaptadorTikTokShop:
    return AdaptadorTikTokShop(interceptar=INTERCEPTAR_TESTE, imagens_hosts=IMAGENS_HOSTS_TESTE)


def sha(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


class RelogioFalso:
    """`__call__` dá o agora; `dormir(s)` só avança o relógio (nenhuma espera real)."""

    def __init__(self, inicio: datetime | None = None):
        self.agora = inicio or datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
        self.dormidas: list[float] = []

    def __call__(self) -> datetime:
        return self.agora

    def dormir(self, segundos: float) -> None:
        self.dormidas.append(segundos)
        self.agora += timedelta(seconds=segundos)


# ---- dados sintéticos da rede (formato de referência do adaptador) ----


def json_produto(pid: str = "7291001", com_pessoal: bool = False) -> dict[str, Any]:
    prod = {
        "product_id": pid,
        "title": f"Shorts de linho {pid}",
        "description": "Tecido fresco.",
        "specifications": [{"attr_name": "Material", "attr_value": "Linho"}],
        "skus": [
            {
                "sku_id": "17001",
                "sku_name": "Bege / M",
                "price": {"sale_price": "49.90", "original_price": "79.90", "currency": "BRL"},
                "stock": 12,
                "image": {"url_list": [f"{HOST_IMG}/sku-{pid}.png?x=1"]},
            }
        ],
        "images": [
            {"url_list": [f"{HOST_IMG}/main-{pid}.png"]},
            {"url_list": [f"{HOST_IMG}/main2-{pid}.png"]},
        ],
        "sold_count": "1,2 mil",
        "price": {
            "min_price": "49.90",
            "max_price": "59.90",
            "original_price": "79.90",
            "currency": "BRL",
        },
        "rating": {"score": 4.8, "review_count": 311},
        "stock": 230,
        "available": True,
        "labels": ["Mais vendido", "Cupom R$ 5"],
        "selling_points": ["Frete grátis"],
        "coupons": ["R$ 5"],
        "free_shipping": True,
        "category": {
            "category_id": "cat789",
            "path": [
                {"category_id": "cat1", "category_name": "Moda"},
                {"category_id": "cat45", "category_name": "Feminino"},
                {"category_id": "cat789", "category_name": "Shorts"},
            ],
        },
        "shop": {
            "shop_id": "loja123",
            "shop_name": "Loja X",
            "official": True,
            "shop_url": f"{HOST_REDE}/shop/loja123?ref=1",
        },
        "launch_time": 1789862400,
    }
    if com_pessoal:
        prod["seller"] = {"nickname": "Fulana", "avatar": "x"}
    return {"data": {"product": prod}}


def json_affiliate(pid: str = "7291001") -> dict[str, Any]:
    return {
        "data": {
            "affiliate": {
                "product_id": pid,
                "commission_rate": "12%",
                "creator_count": 37,
                "sales_7d": 410,
                "sales_30d": 1620,
                "price": {"min_price": 49.9, "max_price": 59.9, "currency": "BRL"},
                "open_plan": True,
                "free_sample": True,
                "targeted_commission_rate": None,
            }
        }
    }


def json_ranking(n: int = 3) -> dict[str, Any]:
    return {
        "data": {
            "category": {
                "category_id": "cat45",
                "path": [
                    {"category_id": "cat1", "category_name": "Moda"},
                    {"category_id": "cat45", "category_name": "Feminino"},
                ],
            },
            "items": [
                {
                    "rank": i + 1,
                    "sold_count": "12,3 mil",
                    "commission_rate": 1200,
                    "creator_count": 10 + i,
                    "product": {
                        "product_id": f"72910{i:02d}",
                        "title": f"Produto {i}",
                        "product_url": f"{HOST_REDE}/product/72910{i:02d}?src=rank",
                        "price": {"min_price": "49.90"},
                        "image": {"url": f"{HOST_IMG}/rank-{i}.png"},
                        "shop": {"shop_id": "loja123", "shop_name": "Loja X", "official": False},
                    },
                }
                for i in range(n)
            ],
        }
    }


def json_categorias() -> dict[str, Any]:
    return {
        "data": {
            "categories": [
                {
                    "category_id": "cat1",
                    "category_name": "Moda",
                    "children": [
                        {
                            "category_id": "cat45",
                            "category_name": "Feminino",
                            "children": [{"category_id": "cat789", "category_name": "Shorts"}],
                        }
                    ],
                },
                {"category_id": "cat2", "category_name": "Casa"},
            ]
        }
    }


def json_vitrine() -> dict[str, Any]:
    return {
        "data": {
            "items": [
                {
                    "added_time": 1790726400,
                    "commission_rate": 0.12,
                    "product": {
                        "product_id": "7291001",
                        "title": "Shorts",
                        "product_url": f"{HOST_REDE}/product/7291001",
                        "image": {"url": f"{HOST_IMG}/v1.png"},
                    },
                }
            ]
        }
    }


def json_loja() -> dict[str, Any]:
    return {
        "data": {
            "shop": {
                "shop_id": "loja123",
                "shop_name": "Loja X",
                "official": True,
                "shop_url": f"{HOST_REDE}/shop/loja123",
                "rating": 4.7,
                "followers": 15800,
                "on_time_shipping_rate": 97.5,
                "response_rate": 92.0,
                "product_count": 84,
                "sold_total": "230 mil",
            },
            "items": [
                {
                    "product_id": "7300001",
                    "title": "Novo",
                    "product_url": f"{HOST_REDE}/product/7300001",
                    "price": {"min_price": "39.90"},
                    "sold_count": 120,
                    "is_new": True,
                    "image": {"url": f"{HOST_IMG}/l1.png"},
                }
            ],
        }
    }


def json_avaliacoes(pid: str = "7291001") -> dict[str, Any]:
    return {
        "data": {
            "page": 1,
            "total_pages": 14,
            "reviews": [
                {
                    "review_id": "av1",
                    "user": {"uid": "6812001", "nickname": "Fulana", "avatar": "x", "bio": "..."},
                    "text": "Tecido ótimo, veio no prazo.",
                    "rating": 5,
                    "create_time": 1790899200,
                    "sku_specification": "Bege / M",
                    "images": [{"url": f"{HOST_IMG}/av1.png"}],
                    "digg_count": 3,
                },
                {
                    "review_id": "av2",
                    "user": {"uid": "6812002", "nickname": "Beltrano"},
                    "text": "Veio menor.",
                    "rating": 3,
                    "create_time": 1790899200,
                },
            ],
        }
    }


def json_videos(pid: str = "7291001") -> dict[str, Any]:
    return {
        "data": {
            "product_id": pid,
            "videos": [
                {
                    "video_id": "7320001",
                    "author": {
                        "unique_id": "fulana.achados",
                        "nickname": "Fulana",
                        "avatar_thumb": "x",
                        "signature": "bio",
                    },
                    "statistics": {
                        "play_count": 1250000,
                        "digg_count": 84000,
                        "comment_count": 1200,
                        "share_count": 3100,
                    },
                    "desc": "Olha esse shorts",
                    "create_time": 1790622120,
                    "duration": 34,
                    "product_tagged": True,
                }
            ],
        }
    }


# ---- SociMan falso ----


@dataclass
class ColetaFalsa:
    id: str
    estado: str = "ativa"
    itens: list[dict[str, Any]] = field(default_factory=list)
    fim: dict[str, Any] | None = None


class SocimanFalso:
    """Responde as rotas C. Modos de erro e o roteiro de respostas são atributos públicos."""

    def __init__(self, relogio: RelogioFalso | None = None, fuso: str = "America/Sao_Paulo"):
        self.relogio = relogio or RelogioFalso()
        self.fuso = fuso
        self.tarefas: list[dict[str, Any]] = []
        self.habilitada = True
        self.motivo_vazia: str | None = None
        self.janela = {"inicio": 8, "fim": 23, "dentro": True}
        self.limites = {
            "paginasDia": 300,
            "imagensDia": 1500,
            "imagensPorProduto": 9,
            "itensPorColeta": 40,
            "pausaMinS": 5,
            "pausaMaxS": 40,
            "leaseMin": 30,
        }
        self.orcamento = {
            "paginasHoje": 0,
            "paginasRestantes": 300,
            "imagensHoje": 0,
            "imagensRestantes": 1500,
        }
        # modos
        self.modo_401 = False
        self.modo_426 = False
        self.n_429 = 0
        self.retry_after: str | None = "2"
        self.coleta_em_andamento_n = 0
        self.desligada = False
        self.parar_apos_lote = 0  # a partir do N-ésimo lote de itens responde parar=true
        self.batimento_parar: dict[str, Any] | None = None
        self.continuar_em: datetime | None = None
        self.continuar_apos_batimentos: int | None = None
        self.status_por_tarefa: dict[str, dict[str, Any]] = {}
        self.imagens_orcamento_esgotado = False
        self.brutos: dict[str, dict[str, Any]] = {}
        # registro
        self.coletas: dict[str, ColetaFalsa] = {}
        self.chamadas: list[tuple[str, str, dict[str, str]]] = []
        self.ordem: list[str] = []
        self.lotes: list[list[dict[str, Any]]] = []
        self.imagens: list[tuple[list[dict[str, Any]], list[bytes]]] = []
        self.batimentos: list[dict[str, Any]] = []
        self.eventos: list[dict[str, Any]] = []
        self.fins: list[dict[str, Any]] = []
        self.filas: list[dict[str, Any]] = []
        self.transport = httpx.MockTransport(self.handler)

    # ---- montagem ----

    def tarefa(
        self,
        tipo: str,
        url: str,
        chave: str | None = None,
        fonte: str = "pagina_publica",
        extra: dict[str, Any] | None = None,
        nivel: int = 1,
    ) -> dict[str, Any]:
        t = {
            "tarefaId": str(uuid.uuid4()),
            "tipo": tipo,
            "rede": "tiktok",
            "mercado": "BR",
            "fonte": fonte,
            "chave": chave or f"{tipo}:x",
            "url": url,
            "nivel": nivel,
            "prioridade": 0,
            "turno": None,
            "reservadaAte": None,
            "extra": extra or {},
        }
        self.tarefas.append(t)
        return t

    def _coleta_json(self, c: ColetaFalsa) -> dict[str, Any]:
        return {
            "id": c.id,
            "clienteId": str(uuid.uuid4()),
            "rede": "tiktok",
            "mercado": "BR",
            "estado": c.estado,
            "iniciadaEm": self.relogio().isoformat(),
            "batimentoEm": self.relogio().isoformat(),
            "terminadaEm": None,
            "tarefaAtualId": None,
            "paginas": len(c.itens),
            "imagens": 0,
            "itensOk": 0,
            "itensErro": 0,
            "itensRepetidos": 0,
            "versaoColetor": "0.1.0",
            "chromeVersao": None,
            "protocolo": 1,
            "resumo": {},
        }

    @staticmethod
    def _erro(
        status: int,
        code: str,
        message: str = "",
        headers: dict[str, str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> httpx.Response:
        corpo: dict[str, Any] = {"code": code, "message": message}
        if details:
            corpo["details"] = details
        return httpx.Response(status, json={"error": corpo}, headers=headers)

    # ---- handler ----

    def handler(self, pedido: httpx.Request) -> httpx.Response:
        caminho = pedido.url.path
        metodo = pedido.method
        self.chamadas.append((metodo, caminho, dict(pedido.headers)))
        if caminho == "/api/health":
            return httpx.Response(200, json={"status": "ok", "db": "ok", "redis": "ok"})
        if caminho.startswith("/api/midia/"):
            tid = caminho.rsplit("/", 1)[-1].removeprefix("tok-")
            bruto = self.brutos.get(tid, {})
            return httpx.Response(
                200,
                content=gzip.compress(json.dumps(bruto).encode()),
                headers={"content-type": "application/json", "content-encoding": "gzip"},
            )
        # portão
        auth = pedido.headers.get("authorization", "")
        if self.modo_401 or not auth.startswith("Bearer scol_"):
            return self._erro(401, "token_invalido", "token recusado")
        if pedido.headers.get("origin"):
            return self._erro(403, "escopo_coleta", "Este token só vale para o serviço do coletor")
        if self.modo_426 or pedido.headers.get("x-sociman-coleta-protocolo") != "1":
            return self._erro(
                426,
                "protocolo_coleta",
                "Atualize o sociman-coletor: o servidor fala o protocolo 2",
                details={"esperado": 2},
            )
        if self.n_429 > 0:
            self.n_429 -= 1
            h = {"Retry-After": self.retry_after} if self.retry_after else {}
            return self._erro(429, "mcp_limite", "limite", headers=h)
        if caminho == "/api/coleta/fila":
            return self._fila(pedido)
        if self.desligada:
            return self._erro(503, "coleta_desligada", "A coleta está desligada no servidor")
        if caminho == "/api/coleta/coletas" and metodo == "POST":
            return self._abrir(pedido)
        if caminho == "/api/coleta/coletas" and metodo == "GET":
            return httpx.Response(
                200,
                json={
                    "itens": [self._coleta_json(c) for c in self.coletas.values()],
                    "proximo": None,
                },
            )
        if caminho == "/api/coleta/eventos":
            corpo = json.loads(pedido.content)
            self.eventos.append(corpo)
            self.ordem.append(f"evento:{corpo['tipo']}")
            return httpx.Response(
                201,
                json={
                    "eventoId": len(self.eventos),
                    "coleta": None,
                    "pausadaAte": None,
                    "notificado": True,
                },
            )
        m = re.match(r"^/api/coleta/coletas/([^/]+)(?:/(.*))?$", caminho)
        if not m:
            return self._erro(404, "nao_encontrado")
        coleta = self.coletas.get(m.group(1))
        if coleta is None:
            return self._erro(404, "coleta_nao_encontrada")
        sub = m.group(2) or ""
        if sub == "" and metodo == "GET":
            j = self._coleta_json(coleta)
            j["itens"] = [
                {
                    "id": i + 1,
                    "tarefaId": it["tarefaId"],
                    "tipo": self._tipo(it),
                    "fonte": it.get("fonte"),
                    "status": "gravado",
                    "brutoPendente": False,
                }
                for i, it in enumerate(coleta.itens)
                if it["status"] == "ok"
            ]
            j["eventos"] = []
            return httpx.Response(200, json=j)
        if sub.startswith("bruto/"):
            tid = sub.split("/", 1)[1]
            if tid not in self.brutos:
                return self._erro(404, "bruto_nao_encontrado")
            return httpx.Response(
                200,
                json={
                    "link": {"url": f"/api/midia/tok-{tid}", "expiresAt": None},
                    "bytes": 100,
                    "esquemaVersao": "tiktok_shop/1",
                    "dataLocal": "2026-10-09",
                    "turno": "tarde",
                },
            )
        if coleta.estado not in ("ativa", "pausada_captcha", "pausada_login"):
            if sub == "fim":
                return self._erro(409, "coleta_fechada", "rodada já fechada")
            return self._erro(409, "coleta_fechada", "rodada já fechada")
        if sub == "itens":
            return self._itens(coleta, pedido)
        if sub == "imagens":
            return self._imagens(coleta, pedido)
        if sub == "batimento":
            return self._batimento(coleta, pedido)
        if sub == "fim":
            corpo = json.loads(pedido.content)
            coleta.fim = corpo
            coleta.estado = (
                "interrompida"
                if corpo["motivo"] in ("parar_local", "servico_parado")
                else "encerrada"
            )
            self.fins.append(corpo)
            self.ordem.append("fim")
            return httpx.Response(200, json=self._coleta_json(coleta))
        return self._erro(404, "nao_encontrado")

    def _tipo(self, item: dict[str, Any]) -> str:
        for t in self.tarefas:
            if t["tarefaId"] == item["tarefaId"]:
                return t["tipo"]
        return "produto"

    def _fila(self, pedido: httpx.Request) -> httpx.Response:
        q = parse_qs(pedido.url.query.decode())
        limite = int(q.get("limite", ["40"])[0])
        simular = q.get("simular", ["false"])[0] == "true"
        self.filas.append({"limite": limite, "simular": simular})
        agora = self.relogio()
        tarefas = [] if (not self.habilitada or self.motivo_vazia) else self.tarefas[:limite]
        return httpx.Response(
            200,
            json={
                "habilitada": self.habilitada,
                "desligadaNoServidor": False,
                "pausadaAte": None,
                "continuarEm": None,
                "agoraServidor": agora.isoformat(),
                "dataLocal": agora.date().isoformat(),
                "fuso": self.fuso,
                "janela": self.janela,
                "limites": self.limites,
                "orcamento": self.orcamento,
                "tarefas": tarefas,
                "motivoVazia": self.motivo_vazia if not tarefas else None,
            },
        )

    def _abrir(self, pedido: httpx.Request) -> httpx.Response:
        if self.coleta_em_andamento_n > 0:
            self.coleta_em_andamento_n -= 1
            return self._erro(
                409, "coleta_em_andamento", "já há rodada aberta", details={"coletaId": "x"}
            )
        corpo = json.loads(pedido.content)
        c = ColetaFalsa(id=str(uuid.uuid4()))
        c.abertura = corpo  # type: ignore[attr-defined]
        self.coletas[c.id] = c
        self.ordem.append("abrir")
        return httpx.Response(201, json=self._coleta_json(c))

    def _itens(self, coleta: ColetaFalsa, pedido: httpx.Request) -> httpx.Response:
        corpo = json.loads(pedido.content)
        lote = corpo["itens"]
        if not 1 <= len(lote) <= 50:
            return self._erro(400, "entrada_invalida", "lote", details={"field": "itens"})
        self.lotes.append(lote)
        self.ordem.append("itens")
        resultados = []
        for it in lote:
            coleta.itens.append(it)
            override = self.status_por_tarefa.get(it["tarefaId"])
            if override:
                resultados.append({"tarefaId": it["tarefaId"], **override})
            elif it["status"] == "ok":
                resultados.append(
                    {
                        "tarefaId": it["tarefaId"],
                        "status": "gravado",
                        "dataLocal": "2026-10-09",
                        "turno": "tarde",
                        "imagensPendentes": [],
                        "brutoPendente": False,
                        "fichaNova": True,
                    }
                )
            elif it["status"] == "captcha":
                resultados.append({"tarefaId": it["tarefaId"], "status": "captcha"})
            else:
                resultados.append(
                    {
                        "tarefaId": it["tarefaId"],
                        "status": "erro",
                        "erroCodigo": it.get("erroCodigo"),
                        "tentativas": 1,
                        "voltaParaFila": True,
                    }
                )
            if it["status"] == "ok":
                self.orcamento["paginasHoje"] += 1
                self.orcamento["paginasRestantes"] = max(0, self.orcamento["paginasRestantes"] - 1)
        parar = bool(self.parar_apos_lote and len(self.lotes) >= self.parar_apos_lote)
        return httpx.Response(
            200,
            json={
                "coletaId": coleta.id,
                "resultados": resultados,
                "orcamento": self.orcamento,
                "pausadaAte": None,
                "parar": parar,
            },
        )

    def _imagens(self, coleta: ColetaFalsa, pedido: httpx.Request) -> httpx.Response:
        ct = pedido.headers.get("content-type", "")
        msg = email.message_from_bytes(
            b"Content-Type: " + ct.encode() + b"\r\n\r\n" + pedido.content, policy=email.policy.HTTP
        )
        arquivos: list[bytes] = []
        manifesto: list[dict[str, Any]] = []
        for parte in msg.iter_parts():
            nome = parte.get_param("name", header="content-disposition")
            if nome == "arquivos":
                arquivos.append(parte.get_payload(decode=True))
            elif nome == "manifesto":
                manifesto = json.loads(parte.get_payload(decode=True))
        self.imagens.append((manifesto, arquivos))
        self.ordem.append("imagens")
        if len(arquivos) > 10:
            return self._erro(413, "lote_grande")
        aceitas, repetidas, recusadas = [], [], []
        shas_vistos = getattr(self, "_shas", set())
        self._shas = shas_vistos
        for conteudo, m in zip(arquivos, manifesto, strict=True):
            s = sha(conteudo)
            if s != m["sha256"]:
                recusadas.append({"sha256": m["sha256"], "motivo": "sha_divergente"})
            elif self.imagens_orcamento_esgotado:
                recusadas.append({"sha256": s, "motivo": "orcamento"})
            elif s in shas_vistos:
                repetidas.append(s)
            else:
                shas_vistos.add(s)
                aceitas.append(s)
                self.orcamento["imagensHoje"] += 1
                self.orcamento["imagensRestantes"] = max(0, self.orcamento["imagensRestantes"] - 1)
        return httpx.Response(
            200,
            json={
                "aceitas": aceitas,
                "repetidas": repetidas,
                "recusadas": recusadas,
                "orcamento": {
                    "imagensHoje": self.orcamento["imagensHoje"],
                    "imagensRestantes": self.orcamento["imagensRestantes"],
                },
            },
        )

    def _batimento(self, coleta: ColetaFalsa, pedido: httpx.Request) -> httpx.Response:
        corpo = json.loads(pedido.content)
        self.batimentos.append(corpo)
        self.ordem.append("batimento")
        resposta: dict[str, Any] = {
            "parar": False,
            "motivo": None,
            "pausadaAte": None,
            "continuarEm": None,
            "limites": self.limites,
            "orcamento": self.orcamento,
        }
        if self.batimento_parar:
            resposta.update(self.batimento_parar)
        if (
            self.continuar_apos_batimentos is not None
            and len(self.batimentos) >= self.continuar_apos_batimentos
        ):
            if self.continuar_em is None:
                self.continuar_em = self.relogio()
        if self.continuar_em is not None:
            resposta["continuarEm"] = self.continuar_em.isoformat()
        return httpx.Response(200, json=resposta)


# ---- navegador falso (sem Chrome) ----


@dataclass
class Cenario:
    """O que a página sintética faz quando aberta."""

    status: int = 200
    titulo: str = "Produto"
    iframes: list[str] = field(default_factory=list)
    redirecionar_para: str | None = None
    interceptadas: list[tuple[str, Any]] = field(default_factory=list)  # (url da api, json)
    imagens: dict[str, bytes] = field(default_factory=dict)  # url → bytes carregados pela página
    timeout: bool = False
    chrome_fechado: bool = False


class RespostaFalsa:
    def __init__(
        self, url: str, status: int = 200, corpo: bytes = b"", content_type: str = "image/png"
    ):
        self.url = url
        self.status = status
        self.ok = 200 <= status < 300
        self._corpo = corpo
        self.headers = {"content-type": content_type}

    def body(self) -> bytes:
        return self._corpo

    def json(self) -> Any:
        return json.loads(self._corpo)


class _Mouse:
    def __init__(self) -> None:
        self.movimentos = 0
        self.rolagens: list[int] = []

    def move(self, x: int, y: int, steps: int = 1) -> None:
        self.movimentos += 1

    def wheel(self, dx: int, dy: int) -> None:
        self.rolagens.append(dy)


class _Locator:
    def __init__(self, texto: str | None = None):
        self._texto = texto
        self.cliques = 0

    @property
    def first(self) -> _Locator:
        return self

    def nth(self, i: int) -> _Locator:
        return self

    def count(self) -> int:
        return 1 if self._texto is not None else 0

    def inner_text(self, timeout: int = 0) -> str:
        return self._texto or ""

    def get_attribute(self, nome: str, timeout: int = 0) -> str | None:
        return None

    def click(self, timeout: int = 0) -> None:
        self.cliques += 1


class _Request:
    def __init__(self, pagina: PaginaFalsa):
        self._pagina = pagina

    def get(self, url: str, timeout: int = 0) -> RespostaFalsa:
        self._pagina.downloads.append(url)
        corpo = self._pagina.navegador.imagens_carregadas.get(url)
        if corpo is None:
            return RespostaFalsa(url, 404, b"")
        return RespostaFalsa(url, 200, corpo)


class _Frame:
    def __init__(self, url: str):
        self.url = url


class PaginaFalsa:
    def __init__(self, navegador: NavegadorFalso):
        self.navegador = navegador
        self.url = "about:blank"
        self._titulo = ""
        self.frames: list[Any] = [self]
        self.mouse = _Mouse()
        self.request = _Request(self)
        self.esperas: list[int] = []
        self.downloads: list[str] = []
        self.locators: dict[str, _Locator] = {}
        self.voltas = 0

    def goto(self, url: str, wait_until: str = "", timeout: int = 0) -> RespostaFalsa | None:
        cen = self.navegador.cenario_de(url)
        if cen.chrome_fechado:
            raise RuntimeError("Target page, context or browser has been closed")
        if cen.timeout:
            raise TimeoutError("Timeout 45000ms exceeded.")
        self.url = cen.redirecionar_para or url
        self._titulo = cen.titulo
        self.frames = [self] + [_Frame(u) for u in cen.iframes]
        self.navegador.interceptadas = [Interceptada(u, 200, j) for u, j in cen.interceptadas]
        self.navegador.imagens_carregadas = dict(cen.imagens)
        for u in cen.imagens:
            self.navegador.baixador.registrar_resposta(RespostaFalsa(u, 200, b"", "image/png"))
        self.navegador.aberturas.append(url)
        return RespostaFalsa(self.url, cen.status, b"", "text/html")

    def title(self) -> str:
        return self._titulo

    def wait_for_timeout(self, ms: int) -> None:
        self.esperas.append(ms)

    def locator(self, seletor: str) -> _Locator:
        return self.locators.get(seletor, _Locator(None))

    def content(self) -> str:
        return ""

    def go_back(self, wait_until: str = "", timeout: int = 0) -> None:
        self.voltas += 1


class NavegadorFalso:
    """Substitui `navegador.Navegador` nos testes de protocolo: sem Chrome, mesmo contrato."""

    def __init__(self, baixador: Any, rede: Any, roteiro: dict[str, Cenario]):
        self.baixador = baixador
        self.rede = rede
        self.roteiro = roteiro
        self.pagina = PaginaFalsa(self)
        self.versao = "131.0.6778.85"
        self.interceptadas: list[Interceptada] = []
        self.imagens_carregadas: dict[str, bytes] = {}
        self.aberturas: list[str] = []
        self.fechado = 0
        self.aberto = 0

    def cenario_de(self, url: str) -> Cenario:
        chave = self.rede.url_canonica(url)
        return self.roteiro.get(chave, Cenario())

    def abrir(self) -> PaginaFalsa:
        self.aberto += 1
        self.baixador.ligar(self.pagina)
        return self.pagina

    def nova_pagina(self) -> None:
        self.interceptadas = []
        self.baixador.nova_pagina()

    def esperar_interceptadas(self, pagina: Any, minimo: int = 1, ms: int = 0) -> None:
        pass

    def fechar(self) -> None:
        self.fechado += 1

    def chrome_vivo(self) -> bool:
        return self.fechado == 0


def cenario_produto(
    pid: str = "7291001", com_affiliate: bool = True, com_pessoal: bool = False
) -> Cenario:
    imagens = {
        f"{HOST_IMG}/main-{pid}.png": PNG_1PX + pid.encode(),
        f"{HOST_IMG}/main2-{pid}.png": PNG_1PX + b"2" + pid.encode(),
        f"{HOST_IMG}/sku-{pid}.png?x=1": PNG_1PX + b"sku" + pid.encode(),
    }
    inter = [(f"{HOST_REDE}/api-sintetica/product/{pid}?a=1", json_produto(pid, com_pessoal))]
    if com_affiliate:
        inter.append((f"{HOST_REDE}/api-sintetica/affiliate/{pid}", json_affiliate(pid)))
    return Cenario(titulo=f"Shorts {pid}", interceptadas=inter, imagens=imagens)
