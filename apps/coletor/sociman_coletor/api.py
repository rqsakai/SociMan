"""Cliente da API de ingestão do SociMan (contracts/http-api.md, rotas C; protocolo `1`).

Único lugar do coletor que fala HTTP com o SociMan (`httpx`). Cabeçalhos em toda chamada:
`Authorization: Bearer scol_…`, `X-Sociman-Coleta-Protocolo: 1`, `X-Sociman-Coletor-Versao`,
`X-Sociman-Chrome-Versao` (quando conhecida) e `User-Agent: sociman-coletor/<semver>`. Nunca
envia `Origin` nem cookies (o jar é limpo a cada resposta e redirecionamentos não são seguidos).

Respostas do portão:
- 401 → `ParaServico("token_invalido", codigo_saida=4)`;
- 403 `escopo_coleta`/`coleta_suspensa` → `ParaServico(..., 4)`;
- 426 → `ParaServico("protocolo_coleta", 5)` com a mensagem do servidor ("atualize o coletor");
- 429 → espera `Retry-After` (ou 60 s) e repete, até `TENTATIVAS_429`;
- 503 `coleta_desligada`/`coleta_indisponivel` → `ColetaDesligada` (quem chama dorme 15 min).
"""

from __future__ import annotations

import gzip
import json
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime
from typing import Any

import httpx

from sociman_coletor import PROTOCOLO, __version__, modelos
from sociman_coletor.config import Config, Segredo

LOTE_ITENS_MAX = 10
LOTE_IMAGENS_MAX = 10
TENTATIVAS_429 = 5
ESPERA_429_PADRAO_S = 60
DORMIR_DESLIGADA_S = 15 * 60
ESPERA_COLETA_EM_ANDAMENTO_S = 5 * 60
TIMEOUT_S = 60.0
TIMEOUT_UPLOAD_S = 180.0
CODIGOS_SAIDA = {
    "token_invalido": 4,
    "escopo_coleta": 4,
    "coleta_suspensa": 4,
    "protocolo_coleta": 5,
}


class ErroApi(Exception):
    """Resposta de erro da API (`{"error": {"code", "message", "details"}}`)."""

    def __init__(
        self, status: int, codigo: str, mensagem: str = "", detalhes: dict[str, Any] | None = None
    ):
        super().__init__(f"{status} {codigo}: {mensagem}")
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhes = detalhes or {}


class ParaServico(ErroApi):
    """O serviço deve parar (token inválido, escopo, suspenso ou protocolo antigo)."""

    def __init__(
        self, status: int, codigo: str, mensagem: str = "", detalhes: dict[str, Any] | None = None
    ):
        super().__init__(status, codigo, mensagem, detalhes)
        self.codigo_saida = CODIGOS_SAIDA.get(codigo, 4)


class ColetaDesligada(ErroApi):
    """503 `coleta_desligada`/`coleta_indisponivel`: fechar a rodada se aberta e dormir 15 min."""


class ErroRede(Exception):
    """Falha de rede ou timeout ao falar com o SociMan."""


def _corpo_erro(resp: httpx.Response) -> tuple[str, str, dict[str, Any]]:
    try:
        corpo = resp.json()
    except ValueError:
        return f"http_{resp.status_code}", resp.text[:200], {}
    erro = corpo.get("error", corpo) if isinstance(corpo, dict) else {}
    if not isinstance(erro, dict):
        return f"http_{resp.status_code}", "", {}
    return (
        str(erro.get("code") or f"http_{resp.status_code}"),
        str(erro.get("message") or ""),
        dict(erro.get("details") or {}),
    )


def _datas_iso(obj: Any) -> Any:
    """`model_dump(mode="json")` já serializa; isto cobre dicts soltos."""
    if isinstance(obj, dict):
        return {k: _datas_iso(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_datas_iso(v) for v in obj]
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    return obj


class ClienteApi:
    """`transport` e `dormir` são injetáveis para o teste (`httpx.MockTransport`, relógio falso)."""

    def __init__(
        self,
        cfg: Config,
        token: Segredo,
        chrome_versao: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        dormir: Callable[[float], None] = time.sleep,
        tentativas_429: int = TENTATIVAS_429,
    ):
        self._token = token
        self._dormir = dormir
        self._tentativas_429 = tentativas_429
        self.chrome_versao = chrome_versao
        verify: bool | str = True
        if cfg.ca_cert is not None:
            verify = str(cfg.ca_cert)
        self._cliente = httpx.Client(
            base_url=cfg.api_url,
            verify=verify,
            timeout=httpx.Timeout(TIMEOUT_S, connect=15.0),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            headers=self._cabecalhos(),
        )

    # ---- infraestrutura ----

    def _cabecalhos(self) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self._token.revelar()}",
            "X-Sociman-Coleta-Protocolo": str(PROTOCOLO),
            "X-Sociman-Coletor-Versao": __version__,
            "User-Agent": f"sociman-coletor/{__version__}",
            "Accept": "application/json",
        }
        if self.chrome_versao:
            h["X-Sociman-Chrome-Versao"] = self.chrome_versao
        return h

    def definir_chrome_versao(self, versao: str | None) -> None:
        self.chrome_versao = versao
        self._cliente.headers.update(self._cabecalhos())

    def fechar(self) -> None:
        self._cliente.close()

    def _chamar(
        self,
        metodo: str,
        caminho: str,
        *,
        json_corpo: Any = None,
        params: dict[str, Any] | None = None,
        files: Any = None,
        data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        enviar = getattr(self._cliente, metodo.lower())
        kwargs: dict[str, Any] = {"params": params}
        if json_corpo is not None:
            kwargs["json"] = _datas_iso(json_corpo)
        if files is not None:
            kwargs["files"] = files
        if data is not None:
            kwargs["data"] = data
        if timeout is not None:
            kwargs["timeout"] = timeout
        for tentativa in range(self._tentativas_429 + 1):
            try:
                resp = enviar(caminho, **kwargs)
            except httpx.TimeoutException as exc:
                raise ErroRede("timeout ao falar com o SociMan") from exc
            except httpx.HTTPError as exc:
                raise ErroRede(f"falha de rede: {type(exc).__name__}") from exc
            finally:
                self._cliente.cookies.clear()
            if resp.status_code == 429 and tentativa < self._tentativas_429:
                self._dormir(self._espera_429(resp))
                continue
            return self._tratar(resp)
        raise ErroApi(429, "mcp_limite", "limite de chamadas")  # inalcançável

    @staticmethod
    def _espera_429(resp: httpx.Response) -> float:
        bruto = resp.headers.get("Retry-After")
        try:
            return float(bruto) if bruto else float(ESPERA_429_PADRAO_S)
        except ValueError:
            return float(ESPERA_429_PADRAO_S)

    @staticmethod
    def _tratar(resp: httpx.Response) -> httpx.Response:
        if resp.is_success:
            return resp
        codigo, mensagem, detalhes = _corpo_erro(resp)
        if resp.status_code == 401:
            raise ParaServico(401, "token_invalido", mensagem or "token recusado", detalhes)
        if resp.status_code == 403 and codigo in ("escopo_coleta", "coleta_suspensa"):
            raise ParaServico(403, codigo, mensagem, detalhes)
        if resp.status_code == 426:
            raise ParaServico(
                426,
                "protocolo_coleta",
                mensagem or "atualize o coletor: protocolo antigo",
                detalhes,
            )
        if resp.status_code == 503 and codigo in ("coleta_desligada", "coleta_indisponivel"):
            raise ColetaDesligada(503, codigo, mensagem, detalhes)
        raise ErroApi(resp.status_code, codigo, mensagem, detalhes)

    # ---- rotas C ----

    def health(self) -> dict[str, Any]:
        return self._chamar("GET", "/api/health").json()

    def fila(self, limite: int, simular: bool = False) -> modelos.Fila:
        params: dict[str, Any] = {"limite": limite}
        if simular:
            params["simular"] = "true"
        return modelos.Fila.model_validate(
            self._chamar("GET", "/api/coleta/fila", params=params).json()
        )

    def abrir(
        self,
        limites_locais: modelos.LimitesLocais | None,
        iniciada_em: datetime,
        chrome_versao: str | None = None,
    ) -> modelos.Coleta:
        corpo = modelos.AbrirColeta(
            versao_coletor=__version__,
            chrome_versao=chrome_versao or self.chrome_versao,
            protocolo=PROTOCOLO,
            limites_locais=limites_locais,
            iniciada_em=iniciada_em,
        )
        resp = self._chamar("POST", "/api/coleta/coletas", json_corpo=corpo.model_dump(mode="json"))
        return modelos.Coleta.model_validate(resp.json())

    def enviar_itens(self, coleta_id: str, itens: Sequence[modelos.Item]) -> modelos.RespostaItens:
        """Lotes de 1 a `LOTE_ITENS_MAX` itens. Timeout depois de enviado → reenvia o mesmo lote
        uma vez (o servidor responde `repetido`, FR-027). Junta as respostas; `parar` é o OR."""
        if not itens:
            raise ValueError("lote vazio")
        resultados: list[modelos.ResultadoItem] = []
        ultima: modelos.RespostaItens | None = None
        parar = False
        for inicio in range(0, len(itens), LOTE_ITENS_MAX):
            lote = itens[inicio : inicio + LOTE_ITENS_MAX]
            corpo = {"itens": [i.model_dump(mode="json") for i in lote]}
            resp = self._com_reenvio(
                lambda c=corpo, cid=coleta_id: self._chamar(
                    "POST",
                    f"/api/coleta/coletas/{cid}/itens",
                    json_corpo=c,
                    timeout=TIMEOUT_UPLOAD_S,
                )
            )
            ultima = modelos.RespostaItens.model_validate(resp.json())
            resultados.extend(ultima.resultados)
            parar = parar or ultima.parar
            if parar:
                break
        assert ultima is not None
        return modelos.RespostaItens(
            coleta_id=coleta_id,
            resultados=resultados,
            orcamento=ultima.orcamento,
            pausada_ate=ultima.pausada_ate,
            parar=parar,
        )

    @staticmethod
    def _com_reenvio(chamada: Callable[[], httpx.Response]) -> httpx.Response:
        try:
            return chamada()
        except ErroRede:
            return chamada()

    def enviar_imagens(
        self,
        coleta_id: str,
        imagens: Iterable[tuple[bytes, modelos.ManifestoImagem]],
    ) -> modelos.RespostaImagens:
        """`multipart/form-data` com até 10 arquivos (`arquivos`) e o `manifesto` (JSON)."""
        lista = list(imagens)
        aceitas: list[str] = []
        repetidas: list[str] = []
        recusadas: list[modelos.ImagemRecusada] = []
        orcamento = None
        for inicio in range(0, len(lista), LOTE_IMAGENS_MAX):
            lote = lista[inicio : inicio + LOTE_IMAGENS_MAX]
            files = [
                (
                    "arquivos",
                    (f"{m.sha256}", conteudo, m.content_type or "application/octet-stream"),
                )
                for conteudo, m in lote
            ]
            manifesto = json.dumps([m.model_dump(mode="json") for _, m in lote])
            resp = self._chamar(
                "POST",
                f"/api/coleta/coletas/{coleta_id}/imagens",
                files=files,
                data={"manifesto": manifesto},
                timeout=TIMEOUT_UPLOAD_S,
            )
            parcial = modelos.RespostaImagens.model_validate(resp.json())
            aceitas.extend(parcial.aceitas)
            repetidas.extend(parcial.repetidas)
            recusadas.extend(parcial.recusadas)
            orcamento = parcial.orcamento
            if any(r.motivo == "orcamento" for r in parcial.recusadas):
                break
        return modelos.RespostaImagens(
            aceitas=aceitas, repetidas=repetidas, recusadas=recusadas, orcamento=orcamento
        )

    def batimento(self, coleta_id: str, corpo: modelos.Batimento) -> modelos.RespostaBatimento:
        resp = self._chamar(
            "POST",
            f"/api/coleta/coletas/{coleta_id}/batimento",
            json_corpo=corpo.model_dump(mode="json"),
        )
        return modelos.RespostaBatimento.model_validate(resp.json())

    def fechar_rodada(self, coleta_id: str, fim: modelos.Fim) -> modelos.Coleta | None:
        """409 `coleta_fechada` é idempotente (a rodada já estava fechada): devolve None."""
        try:
            resp = self._chamar(
                "POST",
                f"/api/coleta/coletas/{coleta_id}/fim",
                json_corpo=fim.model_dump(mode="json"),
            )
        except ErroApi as exc:
            if exc.status == 409 and exc.codigo == "coleta_fechada":
                return None
            raise
        return modelos.Coleta.model_validate(resp.json())

    def evento(self, evento: modelos.Evento) -> modelos.RespostaEvento:
        resp = self._chamar(
            "POST", "/api/coleta/eventos", json_corpo=evento.model_dump(mode="json")
        )
        return modelos.RespostaEvento.model_validate(resp.json())

    def link_bruto(self, coleta_id: str, tarefa_id: str) -> modelos.BrutoLink:
        resp = self._chamar("GET", f"/api/coleta/coletas/{coleta_id}/bruto/{tarefa_id}")
        return modelos.BrutoLink.model_validate(resp.json())

    def baixar_bruto(self, link: modelos.Link) -> Any:
        """Baixa o bruto pelo link assinado (`/api/midia/<token>`) e devolve o JSON já aberto
        (aceita gzip com ou sem `Content-Encoding`)."""
        resp = self._chamar("GET", link.url, timeout=TIMEOUT_UPLOAD_S)
        conteudo = resp.content
        if conteudo[:2] == b"\x1f\x8b":
            conteudo = gzip.decompress(conteudo)
        return json.loads(conteudo.decode("utf-8"))

    # ---- leitura usada pelo `reprocessar` (contrato: `GET /api/coleta/coletas?de&ate`) ----

    def listar_coletas(self, de: date, ate: date) -> list[modelos.ColetaResumo]:
        itens: list[modelos.ColetaResumo] = []
        cursor: str | None = None
        for _ in range(200):
            params: dict[str, Any] = {"de": de.isoformat(), "ate": ate.isoformat(), "limite": 50}
            if cursor:
                params["cursor"] = cursor
            pagina = modelos.ColetasLista.model_validate(
                self._chamar("GET", "/api/coleta/coletas", params=params).json()
            )
            itens.extend(pagina.itens)
            cursor = pagina.proximo
            if not cursor:
                break
        return itens

    def detalhe_coleta(self, coleta_id: str) -> modelos.ColetaDetalhe:
        resp = self._chamar("GET", f"/api/coleta/coletas/{coleta_id}", params={"itensLimite": 1000})
        return modelos.ColetaDetalhe.model_validate(resp.json())
