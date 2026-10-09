"""Coletor falso (spec 026, T019): gera rodadas sintéticas e as posta pela **API de ingestão**,
com um token real criado no teste. Nenhum teste chama a rede: o fake é o único "coletor" dos
testes da API (SC-001, SC-004, US1, US4, US5).

Uso:

    cliente, token = criar_cliente_coleta(client, h_dono)        # dono humano cria o cliente
    ligar_coleta(client, h_dono, coleta_habilitada)              # aceite + botão + .env
    fake = ColetorFake(client, token)
    fake.semear(db, produtos=3, dias=10)                        # tarefas + rodadas + itens

`semear` cria as tarefas direto no banco (a trilha `mercado` só nasce na US4) e posta os itens
pela API, dia a dia, com `coletadoEm` no fuso do mercado. Os números são determinísticos: o
produto 0 sobe (+20/dia), o 1 é estável (+5/dia), o 2 não tem foto do Affiliate Center.
"""

import base64
import gzip
import hashlib
import io
import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from PIL import Image
from sqlalchemy import text

from sociman_api.coleta.credenciais import Segredo

SP = ZoneInfo("America/Sao_Paulo")
PROTOCOLO = {"X-Sociman-Coleta-Protocolo": "1", "X-Sociman-Coletor-Versao": "0.1.0-fake"}
ESQUEMA = "tiktok_shop/1"
URL_BASE = "https://exemplo.test/shop"


class Cabecalhos(dict):
    def __repr__(self) -> str:
        return "{'Authorization': 'Bearer scol_***'}"


def bearer(token: str) -> dict[str, str]:
    return Cabecalhos(Authorization=f"Bearer {token}", **PROTOCOLO)


def criar_cliente_coleta(client, h, nome: str = "desktop do dono", **extra) -> tuple[dict, str]:
    r = client.post("/api/coleta/clientes", headers=h, json={"nome": nome, "mercado": "BR", **extra})
    assert r.status_code == 201, r.text
    return r.json()["cliente"], Segredo(r.json()["token"])


def ligar_coleta(client, h, coleta_habilitada) -> dict:
    """Os dois níveis do interruptor (o `.env` por override, a tela pela API) com o aceite."""
    coleta_habilitada(True)
    cfg = client.get("/api/coleta/config", headers=h).json()
    if not cfg["riscoAceito"]:
        r = client.post("/api/coleta/config/aceitar-risco", headers=h,
                        json={"version": cfg["version"], "textoVersao": "2026-10-08",
                              "confirmo": True})
        assert r.status_code == 200, r.text
        cfg = r.json()
    if not cfg["habilitada"] or (cfg["janelaInicio"], cfg["janelaFim"]) != (0, 23):
        # Janela o dia inteiro: o teste não pode depender da hora da parede.
        r = client.put("/api/coleta/config", headers=h,
                       json={**{k: cfg[k] for k in ("paginasDia", "imagensDia",
                                                    "imagensPorProduto", "itensPorColeta",
                                                    "pausaMinS", "pausaMaxS")},
                             "janelaInicio": 0, "janelaFim": 23,
                             "habilitada": True, "version": cfg["version"]})
        assert r.status_code == 200, r.text
        cfg = r.json()
    return cfg


def png(semente: int, tamanho: int = 96) -> bytes:
    """Um PNG sintético, diferente por semente (a cor), gerado pelo Pillow."""
    im = Image.new("RGB", (tamanho, tamanho), ((semente * 37) % 256, (semente * 91) % 256, 120))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def bruto(obj: dict) -> str:
    return base64.b64encode(gzip.compress(json.dumps(obj).encode())).decode()


def coletado_em(dia: date, hora: int = 10) -> str:
    return datetime.combine(dia, time(hora, 0), SP).isoformat()


class ColetorFake:
    def __init__(self, client, token: str, mercado: str = "BR"):
        self.client = client
        self.h = bearer(token)
        self.mercado = mercado
        self.coleta: dict | None = None

    # ---- protocolo ----

    def fila(self, limite: int = 40) -> dict:
        r = self.client.get(f"/api/coleta/fila?limite={limite}", headers=self.h)
        assert r.status_code == 200, r.text
        return r.json()

    def abrir(self) -> dict:
        r = self.client.post("/api/coleta/coletas", headers=self.h,
                             json={"versaoColetor": "0.1.0-fake", "protocolo": 1})
        assert r.status_code == 201, r.text
        self.coleta = r.json()
        return self.coleta

    def itens(self, itens: list[dict]) -> dict:
        assert self.coleta is not None
        r = self.client.post(f"/api/coleta/coletas/{self.coleta['id']}/itens", headers=self.h,
                             json={"itens": itens})
        assert r.status_code == 200, r.text
        return r.json()

    def imagens(self, arquivos: list[bytes], tarefa_id: str | None = None,
                origem: str = "produto") -> dict:
        assert self.coleta is not None
        manifesto = [{"sha256": sha(a), "tarefaId": tarefa_id, "origem": origem} for a in arquivos]
        files = [("arquivos", (f"{sha(a)[:8]}.png", a, "image/png")) for a in arquivos]
        r = self.client.post(f"/api/coleta/coletas/{self.coleta['id']}/imagens", headers=self.h,
                             files=files, data={"manifesto": json.dumps(manifesto)})
        assert r.status_code == 200, r.text
        return r.json()

    def batimento(self, **extra) -> dict:
        assert self.coleta is not None
        r = self.client.post(f"/api/coleta/coletas/{self.coleta['id']}/batimento",
                             headers=self.h, json={"estado": "ativa", **extra})
        assert r.status_code == 200, r.text
        return r.json()

    def fechar(self, motivo: str = "fila_vazia") -> dict:
        assert self.coleta is not None
        r = self.client.post(f"/api/coleta/coletas/{self.coleta['id']}/fim", headers=self.h,
                             json={"motivo": motivo})
        assert r.status_code == 200, r.text
        out = r.json()
        self.coleta = None
        return out

    def evento(self, tipo: str, **extra) -> dict:
        corpo = {"tipo": tipo, "coletaId": self.coleta["id"] if self.coleta else None, **extra}
        r = self.client.post("/api/coleta/eventos", headers=self.h, json=corpo)
        assert r.status_code == 201, r.text
        return r.json()

    # ---- tarefas direto no banco (a trilha chega na US4) ----

    @property
    def token_id(self) -> str:
        return self.h["Authorization"].split(" ", 1)[1].split("_", 2)[1]

    def tarefa(self, db, tipo: str, chave: str, url: str, dia: date, nivel: int = 1,
               fonte: str = "ambas", turno: str | None = None, extra: dict | None = None,
               reservar: bool = False) -> str:
        """Uma tarefa `pendente` do dia (a `fila()` a reserva); com `reservar=True` já nasce
        `reservada` por este cliente (para semear dias passados, que a fila de hoje não entrega)."""
        tid = uuid.uuid4()
        db.execute(text(
            "INSERT INTO mercado_fila (id, tipo, rede, mercado, fonte, chave, url, nivel, "
            "prioridade, data_local, turno, estado, extra, cliente_id, reservada_ate) VALUES "
            "(:id, :tipo, 'tiktok', :m, :fonte, :chave, :url, :nivel, 0, :dia, "
            "CAST(:turno AS mercado_turno), CAST(:estado AS mercado_fila_estado), "
            "CAST(:extra AS jsonb), (SELECT id FROM coleta_clientes WHERE token_id = :tok AND "
            ":reservar), CASE WHEN :reservar THEN now() + interval '30 minutes' END)"),
            {"id": tid, "tipo": tipo, "m": self.mercado, "fonte": fonte, "chave": chave,
             "url": url, "nivel": nivel, "dia": dia, "turno": turno,
             "estado": "reservada" if reservar else "pendente",
             "extra": json.dumps(extra or {}), "tok": self.token_id, "reservar": reservar})
        db.commit()
        return str(tid)

    # ---- payloads sintéticos ----

    @staticmethod
    def produto_id(i: int) -> str:
        return f"{7290000000000000000 + i}"

    @classmethod
    def url_produto(cls, i: int) -> str:
        return f"{URL_BASE}/product/{cls.produto_id(i)}"

    def campos_produto(self, i: int, dia_n: int, com_affiliate: bool = True,
                       titulo: str | None = None, imagens: list[bytes] | None = None,
                       vendidos: int | None = None, imagens_sha: list[str] | None = None) -> dict:
        passo = (20, 5, 12)[i % 3]
        vendidos = (1000 + i * 100 + dia_n * passo) if vendidos is None else vendidos
        shas = imagens_sha if imagens_sha is not None else [sha(a) for a in (imagens or [])]
        campos = {
            "redeProdutoId": self.produto_id(i), "urlCanonica": self.url_produto(i),
            "ficha": {
                "titulo": titulo or f"Produto {i}", "descricao": f"Descrição do produto {i}",
                "atributos": [{"nome": "Material", "valor": "Linho"}],
                "variantes": [{"redeVarianteId": f"v{i}a", "nome": "Bege / M",
                               "precoCentavos": 4990 + i * 100}],
                "argumentos": ["Frete grátis"], "selos": ["Mais vendido"],
                "categoria": {"redeCategoriaId": "cat789", "caminho": [
                    {"redeCategoriaId": "cat1", "nome": "Moda"},
                    {"redeCategoriaId": "cat45", "nome": "Feminino"},
                    {"redeCategoriaId": "cat789", "nome": "Shorts"}]},
                "loja": {"redeLojaId": "loja123", "nome": "Loja X", "oficial": True},
                "imagensSha": shas,
            },
            "paginaPublica": {
                "vendidos": {"valor": vendidos, "min": vendidos, "max": vendidos, "exato": True},
                "precoMinCentavos": 4990 + i * 100, "precoMaxCentavos": 5990 + i * 100,
                "precoOriginalCentavos": 7990, "moeda": "BRL", "nota": 4.8,
                "nAvaliacoes": 300 + dia_n, "estoqueVisivel": 230, "disponivel": True,
                "campos": {"freteGratis": True},
            },
        }
        if com_affiliate:
            campos["affiliate"] = {"comissaoBp": 1200, "nCriadores": 37 + i,
                                   "precoMinCentavos": 4990 + i * 100, "moeda": "BRL",
                                   "campos": {"planoAberto": True}}
        return campos

    def item(self, tarefa_id: str, campos: dict, dia: date, hora: int = 10,
             imagens: list[bytes] | None = None, fonte: str | None = None,
             bruto_extra: dict | None = None) -> dict:
        return {"tarefaId": tarefa_id, "status": "ok", "coletadoEm": coletado_em(dia, hora),
                "duracaoMs": 1234, "esquemaVersao": ESQUEMA, "fonte": fonte,
                "campos": campos, "bruto": bruto({"campos": campos, **(bruto_extra or {})}),
                "imagens": [sha(a) for a in (imagens or [])]}

    # ---- a semente padrão (US1, SC-001) ----

    def semear(self, db, produtos: int = 3, dias: int = 10, ate: date | None = None,
               imagens_por_produto: int = 0, ranking: bool = True) -> dict:
        """`produtos` × `dias` fotos (uma rodada por dia). O último produto não tem Affiliate.
        Devolve `{produtos: [redeProdutoId], dias: [date], tarefas: {...}}`."""
        ate = ate or datetime.now(UTC).astimezone(SP).date()
        dias_lista = [ate - timedelta(days=dias - 1 - n) for n in range(dias)]
        saida = {"produtos": [self.produto_id(i) for i in range(produtos)], "dias": dias_lista,
                 "imagens": {}}
        for n, dia in enumerate(dias_lista):
            self.abrir()
            itens = []
            for i in range(produtos):
                imgs = [png(i * 10 + k) for k in range(imagens_por_produto)] if n == 0 else []
                if imgs:
                    saida["imagens"][i] = [sha(a) for a in imgs]
                tid = self.tarefa(db, "produto", f"produto:{self.produto_id(i)}",
                                  self.url_produto(i), dia, reservar=True)
                campos = self.campos_produto(i, n, com_affiliate=(i != produtos - 1),
                                             imagens=imgs, imagens_sha=saida["imagens"].get(i))
                if imgs:
                    self.imagens(imgs, tid)
                itens.append(self.item(tid, campos, dia, imagens=imgs))
            if ranking:
                tid = self.tarefa(db, "ranking", "ranking:cat45:mais_vendidos:7d",
                                  f"{URL_BASE}/ranking/cat45", dia, nivel=3, fonte="affiliate",
                                  reservar=True)
                itens.append(self.item(tid, self.campos_ranking(produtos, n), dia, hora=11))
            r = self.itens(itens)
            assert all(x["status"] in ("gravado", "repetido") for x in r["resultados"]), r
            self.fechar()
        return saida

    def campos_ranking(self, produtos: int, dia_n: int, tipo: str = "mais_vendidos",
                       janela: str = "7d") -> dict:
        ordem = list(range(produtos))
        if dia_n % 2 == 1 and produtos > 1:  # muda a ordem em dias alternados (variação)
            ordem[0], ordem[1] = ordem[1], ordem[0]
        return {"rankingTipo": tipo, "janela": janela,
                "categoria": {"redeCategoriaId": "cat45", "caminho": [
                    {"redeCategoriaId": "cat1", "nome": "Moda"},
                    {"redeCategoriaId": "cat45", "nome": "Feminino"}]},
                "itens": [{"posicao": p + 1, "redeProdutoId": self.produto_id(i),
                           "urlCanonica": self.url_produto(i), "titulo": f"Produto {i}",
                           "valorExibido": f"{1000 - p * 100} vendidos", "valorNum": 1000 - p * 100,
                           "campos": {"comissaoBp": 1200}}
                          for p, i in enumerate(ordem)]}

    def campos_avaliacoes(self, i: int, n: int = 5, imagens: list[bytes] | None = None) -> dict:
        shas = [sha(a) for a in (imagens or [])]
        return {"redeProdutoId": self.produto_id(i), "pagina": 1, "totalPaginas": 1,
                "itens": [{"redeAvaliacaoId": f"av{i}-{k}", "autorRef": f"autor-{k}",
                           "texto": f"Avaliação {k} do produto {i}", "nota": 5 - (k % 3),
                           "dataAvaliacao": "2026-10-02", "variante": "Bege / M",
                           "imagensSha": shas if k == 0 else [], "curtidas": k, "campos": {}}
                          for k in range(n)]}

    def campos_videos(self, i: int, n: int = 3) -> dict:
        return {"redeProdutoId": self.produto_id(i),
                "itens": [{"posicao": k + 1, "redeVideoId": f"{7320000000000 + i * 10 + k}",
                           "autorHandle": f"criadora.{k}", "views": 100000 * (n - k),
                           "likes": 5000 * (n - k), "comentarios": 120, "compartilhamentos": 30,
                           "legenda": f"Legenda {k}", "publicadoEm": "2026-09-28T19:02:00-03:00",
                           "campos": {"duracaoS": 34}} for k in range(n)]}

    def campos_loja(self, novos: int = 2) -> dict:
        return {"redeLojaId": "loja123", "nome": "Loja X", "oficial": True,
                "url": f"{URL_BASE}/shop/loja123",
                "foto": {"nota": 4.7, "seguidores": 15800, "envioNoPrazoPct": 97.5,
                         "nProdutos": 84, "vendidosTotal": {"valor": 230000, "exato": False,
                                                            "min": 225000, "max": 234999}},
                "produtos": [{"redeProdutoId": self.produto_id(100 + k),
                              "urlCanonica": self.url_produto(100 + k), "titulo": f"Novo {k}",
                              "precoMinCentavos": 3990, "moeda": "BRL",
                              "vendidos": {"valor": 120, "exato": True}, "novo": True}
                             for k in range(novos)]}

    def campos_vitrine(self, ids: list[int]) -> dict:
        return {"itens": [{"redeProdutoId": self.produto_id(i), "urlCanonica": self.url_produto(i),
                           "titulo": f"Produto {i}", "adicionadoEm": "2026-09-30",
                           "campos": {"comissaoBp": 1200}} for i in ids]}

    @staticmethod
    def campos_categorias() -> dict:
        return {"categorias": [
            {"redeCategoriaId": "cat1", "nome": "Moda", "nivel": 1, "paiRedeId": None},
            {"redeCategoriaId": "cat45", "nome": "Feminino", "nivel": 2, "paiRedeId": "cat1"},
            {"redeCategoriaId": "cat789", "nome": "Shorts", "nivel": 3, "paiRedeId": "cat45"},
            {"redeCategoriaId": "cat2", "nome": "Casa", "nivel": 1, "paiRedeId": None}]}
