"""Gerador das opções (research R1–R4, R8, R9 e R14): `sociman gerador`, serviço próprio do compose.

Um advisory lock do Postgres (`0x50C2`) garante uma instância ativa. Com o lock, duas linhas:
- **linha GPU** (um job `comfyui` ou `tts` por vez, na ordem de pedido; o índice
  `uq_geracoes_gpu_rodando` garante no banco). Em cada volta:
  1. devolve à fila as `rodando` abandonadas (`requeue_stale`);
  2. se a RAM do ComfyUI não voltou a 12 GB ("travada"), tenta devolver de novo a cada 30 s e
     não pega nenhum job de GPU (FR-021);
  3. espia o próximo job; antes dele, solta o outro motor (`/unload` do shop-tts antes do
     ComfyUI; `/free` com `unload_models` antes do shop-tts, FR-022) e confere a GPU (`gpu.py`).
     GPU ocupada → toda a fila de GPU "Aguardando a GPU ficar livre" em +30 s, sem contar
     tentativa (FR-018, FR-020);
  4. job `comfyui`: sobe a RAM para 28 GB, roda as opções e, num `finally`, devolve 12 GB e
     confere (sucesso, falha, cancelamento e SIGTERM). Sem `DOCKERCTL_TOKEN`, não pega job
     `comfyui` ("Ajuste de memória do ComfyUI não configurado"), e os `tts` seguem;
- **linha Claude** (thread própria, um job por vez, sem conferir a GPU, FR-019).

Cada opção é gravada assim que fica pronta (R7). O heartbeat (5 s) também lê o status: uma
geração cancelada para o ComfyUI (`/interrupt` e `/queue delete`) e o resultado que chegar depois
é descartado (R9). SIGTERM devolve a geração à fila sem contar tentativa. **Nunca auto:** o
gerador só chama `Aplicador.aplicar` nos passos `sem_escolha` (teste-guarda).

O estado da linha (ativo, RAM travada) vai para o Redis com validade curta (`geracao:gerador`),
para o `GET /api/integracoes` mostrar sem expor nada.
"""

import json
import logging
import signal
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from sociman_api import datadir, imaging, storage
from sociman_api.auth.deps import Actor
from sociman_api.config import get_settings
from sociman_api.db import get_engine, get_sessionmaker
from sociman_api.errors import ApiError
from sociman_api.geracao import aplicadores, audios, erros, fila, gpu, motor_claude, passos
from sociman_api.geracao.comfyui import Cancelada, ComfyClient, get_comfy_client, run_bloco
from sociman_api.geracao.erros import MotorErro
from sociman_api.geracao.fila import Job
from sociman_api.geracao.memoria import MemoriaClient, MemoriaErro, get_memoria_client
from sociman_api.geracao.models import (
    MOTORES_GPU,
    Geracao,
    GeracaoCandidato,
    GeracaoMotor,
)
from sociman_api.geracao.shoptts import ShopTtsClient, get_shoptts_client
from sociman_api.ia.cliente import IaClient, get_ia_client
from sociman_api.perfis.models import Image, ImageKind

log = logging.getLogger("sociman.gerador")

LOCK_KEY = 0x50C2
HEARTBEAT_S = 5.0
IDLE_S = 2.0
ESPERA_LOCK_S = 5.0
TRAVADA_S = 30.0
ESTADO_KEY = "geracao:gerador"
ESTADO_TTL_S = 60
SEM_MEMORIA_CFG = "Ajuste de memória do ComfyUI não configurado"
SEM_RAM = "Não foi possível dar memória ao ComfyUI; tentando de novo"
HD_FORA = "O HD de dados não está disponível"
NAO_COUBE_TENTATIVAS = 3


class Parado(Exception):
    """O gerador foi parado (SIGTERM) no meio do job: a geração volta à fila sem contar."""


@dataclass
class Clientes:
    """Os clientes dos motores, por parâmetro (os testes passam os fakes)."""

    comfy: ComfyClient
    tts: ShopTtsClient
    memoria: MemoriaClient | None  # None = sem `DOCKERCTL_TOKEN` (R4)
    ia: Callable[[], IaClient | None] = field(default=get_ia_client)


def clientes_padrao() -> Clientes:
    return Clientes(comfy=get_comfy_client(), tts=get_shoptts_client(),
                    memoria=get_memoria_client())


def _session() -> Session:
    return get_sessionmaker()()


def autor(job: Job) -> Actor:
    """Nos passos sem escolha, a versão do alvo tem como autor **quem pediu** (R10)."""
    from sociman_api.auth.models import User

    with _session() as db:
        user = db.get(User, job.created_by) if job.created_by else None
        if user is not None:
            db.expunge(user)
    return Actor(kind="user", user_id=job.created_by, user=user)


# ---- heartbeat ----

class _Heartbeat(threading.Thread):
    """Grava andamento e `heartbeat_at` a cada 5 s; `perdida` = cancelada ou devolvida."""

    def __init__(self, job: Job, interval: float = HEARTBEAT_S):
        super().__init__(name=f"heartbeat-{job.id}", daemon=True)
        self.job = job
        self.interval = interval
        self.progress = 0
        self.mensagem: str | None = None
        self.perdida = threading.Event()
        self._fim = threading.Event()

    def bater(self) -> bool:
        try:
            if not fila.heartbeat(self.job, self.progress, self.mensagem):
                self.perdida.set()
        except Exception:  # banco fora por um instante não derruba o job
            log.warning("heartbeat da geração %s falhou", self.job.id, exc_info=True)
        return not self.perdida.is_set()

    def run(self) -> None:
        while not self._fim.wait(self.interval):
            if not self.bater():
                return

    def parar(self) -> None:
        self._fim.set()
        if self.is_alive():
            self.join(timeout=5)


# ---- o job ----

class Executor:
    def __init__(self, clientes: Clientes, stop: threading.Event,
                 heartbeat_s: float = HEARTBEAT_S):
        self.c = clientes
        self.stop = stop
        self.heartbeat_s = heartbeat_s

    def _ja_gravadas(self, job: Job) -> set[int]:
        with _session() as db:
            return set(db.scalars(select(GeracaoCandidato.numero).where(
                GeracaoCandidato.geracao_id == job.id)))

    def _candidatos(self, job: Job) -> list[GeracaoCandidato]:
        with _session() as db:
            return list(db.scalars(select(GeracaoCandidato).where(
                GeracaoCandidato.geracao_id == job.id).order_by(GeracaoCandidato.numero)))

    def _conferir_referencias(self, job: Job, aplicador: aplicadores.Aplicador) -> list[bytes]:
        with _session() as db:
            g = db.get(Geracao, job.id)
            aplicador.conferir_referencias(db, g)
            imgs = [db.get(Image, uuid.UUID(r)) for r in job.params.get("referencias") or []]
            keys = [i.object_key for i in imgs if i is not None]
        return [aplicador.preparar_referencia(storage.get(k)) for k in keys]

    def _vivo(self, beat: _Heartbeat) -> Callable[[], bool]:
        """O `heartbeat` do `run_bloco`: False = parado (SIGTERM) ou cancelada (R9)."""
        return lambda: not self.stop.is_set() and beat.bater()

    def _checar(self, beat: _Heartbeat) -> None:
        if self.stop.is_set():
            raise Parado
        if beat.perdida.is_set():
            raise Cancelada

    def _gravar_imagem(self, job: Job, passo: passos.Passo, numero: int, seed: int | None,
                       pngs: list[bytes]) -> bool:
        kind = passo.image_kind or "imagem"
        infos = [imaging.validate_image(p, kind, max_bytes=20 * 1024 * 1024) for p in pngs]
        keys = [f"perfis/{job.perfil_id}/{uuid.uuid4()}.{i.ext}" for i in infos]
        for key, png, info in zip(keys, pngs, infos, strict=True):
            storage.put(key, png, info.content_type)  # HD conferido dentro (503/507)

        def gravar(db: Session) -> GeracaoCandidato:
            ids = []
            for key, info in zip(keys, infos, strict=True):
                img = Image(perfil_id=job.perfil_id, kind=ImageKind(kind), object_key=key,
                            content_type=info.content_type, bytes=info.bytes,
                            width=info.width, height=info.height, sha256=info.sha256,
                            created_by=job.created_by)
                db.add(img)
                db.flush()
                ids.append(img.id)
            cand = GeracaoCandidato(
                geracao_id=job.id, numero=numero, image_id=ids[0],
                image_par_id=ids[1] if len(ids) > 1 else None, seed=seed,
                metricas={"largura": infos[0].width, "altura": infos[0].height})
            db.add(cand)
            return cand
        return fila.gravar_candidato(job, gravar)

    def comfyui(self, job: Job, beat: _Heartbeat) -> None:
        passo = passos.get(job.passo)
        aplicador = aplicadores.para(job.passo)
        if passo is None or aplicador is None:
            raise MotorErro("internal", detalhe=f"passo {job.passo} sem aplicador")
        refs = self._conferir_referencias(job, aplicador)
        with _session() as db:
            g = db.get(Geracao, job.id)
            db.expunge(g)
        seeds = list(job.params.get("seeds") or [])
        feitas = self._ja_gravadas(job)
        n = job.n_opcoes
        for i in range(1, n + 1):
            self._checar(beat)
            if i in feitas:
                continue
            rotulo = "par" if passo.resultado == "par_imagem" else "opção"
            beat.progress, beat.mensagem = (i - 1) * 100 // n, f"Gerando {rotulo} {i} de {n}"
            beat.bater()
            seed = seeds[i - 1] if i - 1 < len(seeds) else None
            pngs = []
            for lado, entrada in enumerate(aplicador.entradas_comfyui(g, seed, refs)):
                try:
                    dados = run_bloco(self.c.comfy, g.params["bloco"], entrada,
                                      self._vivo(beat), nome_base=f"{job.id}_{i}_{lado}")
                except MotorErro as exc:
                    if exc.codigo == "internal" and "sem saída" in exc.detalhe:
                        log.warning("geração %s: opção %d sem saída", job.id, i)
                        pngs = []
                        break
                    raise
                pngs.append(aplicador.normalizar(dados))
            if not pngs:
                continue  # "veio 1 de 2" (edge case da spec)
            self._checar(beat)
            if not self._gravar_imagem(job, passo, i, seed, pngs):
                raise Cancelada
        self._concluir(job, passo, aplicador)

    def tts(self, job: Job, beat: _Heartbeat) -> None:
        passo = passos.get(job.passo)
        aplicador = aplicadores.para(job.passo)
        if passo is None or aplicador is None:
            raise MotorErro("internal", detalhe=f"passo {job.passo} sem aplicador")
        with _session() as db:
            g = db.get(Geracao, job.id)
            pedido = aplicador.pedido_tts(db, g)
            if pedido.get("op") == "register":
                key = audios_key(db, pedido["audio_id"])
        beat.mensagem = "Gerando a voz"
        beat.bater()
        op, n = pedido.get("op"), job.n_opcoes
        if op == "register":
            lote = self.c.tts.register(storage.get(key, bucket="audios"), "gravacao",
                                       nome=pedido["nome"], tom=pedido.get("tom", ""), n=n)
        elif op == "design":
            seeds = job.params.get("seeds") or [1]
            lote = self.c.tts.design(nome=pedido["nome"], descricao=pedido["descricao"], n=n,
                                     seed=seeds[0], texto=pedido.get("texto"))
        elif op == "tts":
            lote = self.c.tts.tts(pedido["corpo"])
        else:
            raise MotorErro("internal", detalhe=f"pedido tts desconhecido: {op}")
        lote_id = lote.get("lote_id") or ""
        try:
            self._checar(beat)
            self._gravar_lote(job, passo, lote, beat)
        finally:
            try:
                self.c.tts.apagar_lote(lote_id)
            except (MotorErro, ValueError):
                log.warning("não foi possível apagar o lote %s do shop-tts", lote_id)
        self._concluir(job, passo, aplicador)

    def _gravar_lote(self, job: Job, passo: passos.Passo, lote: dict[str, Any],
                     beat: _Heartbeat) -> None:
        lote_id = lote.get("lote_id") or ""
        if job.passo == "voz.teste" or lote.get("frases") is not None or lote.get("arquivo"):
            arquivo = lote.get("arquivo") or next(
                (f.get("arquivo") for f in lote.get("frases") or [] if f.get("arquivo")), None)
            if not arquivo:
                raise MotorErro("internal", "O motor não devolveu áudio", detalhe="sem arquivo")
            dados = self.c.tts.baixar(lote_id, arquivo)

            def gravar_teste(db: Session) -> GeracaoCandidato:
                a = audios.gravar_bytes(db, job.perfil_id, dados, job.created_by)
                cand = GeracaoCandidato(geracao_id=job.id, numero=1, audio_id=a.id,
                                        metricas={"segundos": a.duracao_ms / 1000,
                                                  "texto": job.params.get("texto")})
                db.add(cand)
                return cand
            if not fila.gravar_candidato(job, gravar_teste):
                raise Cancelada
            return
        for c in (lote.get("candidatos") or [])[:job.n_opcoes]:
            self._checar(beat)
            numero = int(c.get("n") or 0)
            dados = self.c.tts.baixar(lote_id, c["arquivo"])
            teste = self.c.tts.baixar(lote_id, c["teste"]) if c.get("teste") else None

            def gravar(db: Session, c=c, numero=numero, dados=dados,
                       teste=teste) -> GeracaoCandidato:
                a = audios.gravar_bytes(db, job.perfil_id, dados, job.created_by)
                t = audios.gravar_bytes(db, job.perfil_id, teste, job.created_by) \
                    if teste else None
                metricas = {"segundos": c.get("segundos"),
                            "similaridade": c.get("similaridade"),
                            "transcricao": c.get("transcricao"),
                            "teste_audio_id": str(t.id) if t else None}
                cand = GeracaoCandidato(geracao_id=job.id, numero=numero, audio_id=a.id,
                                        metricas=metricas)
                db.add(cand)
                return cand
            if not fila.gravar_candidato(job, gravar):
                raise Cancelada

    def claude(self, job: Job, beat: _Heartbeat) -> None:
        passo = passos.get(job.passo)
        aplicador = aplicadores.para(job.passo)
        if passo is None or aplicador is None:
            raise MotorErro("internal", detalhe=f"passo {job.passo} sem aplicador")
        beat.mensagem = "Escrevendo com o Claude"
        beat.bater()
        with _session() as db, db.begin():  # a chamada fica registrada, com erro ou não (R14)
            row = motor_claude.chamar(db, job, self.c.ia())
            chamada_id, proposta = row.id, row.proposta
            erro = motor_claude.erro_da_chamada(row)
        if erro is not None:
            if erro.mensagem == motor_claude.NAO_CONFIGURADO:  # sem ficar presa na fila (US4)
                fila.para_falhou(job, erro.codigo, erro.mensagem)
                return
            raise erro
        self._checar(beat)

        def gravar(db: Session) -> GeracaoCandidato:
            cand = GeracaoCandidato(geracao_id=job.id, numero=1,
                                    metricas={**(proposta or {}),
                                              "chamada_id": str(chamada_id)})
            db.add(cand)
            return cand
        if not fila.gravar_candidato(job, gravar):
            raise Cancelada
        self._concluir(job, passo, aplicador, chamada_id=chamada_id)

    def _concluir(self, job: Job, passo: passos.Passo, aplicador: aplicadores.Aplicador,
                  chamada_id: uuid.UUID | None = None) -> None:
        cands = self._candidatos(job)
        if not cands:
            raise MotorErro("internal", "O motor não devolveu nenhuma opção",
                            detalhe="nenhum candidato")
        if job.passo == "voz.teste":
            fila.para_entregue(job)
            return
        if passo.sem_escolha:  # FR-010 e FR-031: só estes vão direto ao alvo
            actor = autor(job)

            def aplicar(db: Session, g: Geracao, cand: GeracaoCandidato) -> None:
                aplicador.aplicar(db, actor, g, cand)
                if chamada_id is not None:
                    motor_claude.marcar_aplicada(db, chamada_id, job.created_by)
            fila.para_escolhido_auto(job, cands[0].id, aplicar)
            return
        veio = len(cands)
        fila.para_revisao(job, None if veio >= job.n_opcoes else f"Veio {veio} de {job.n_opcoes}")

    def executar(self, job: Job) -> str:
        """Roda o job já pego. Devolve como terminou (para o log e os testes)."""
        beat = _Heartbeat(job, self.heartbeat_s)
        beat.start()
        try:
            {GeracaoMotor.comfyui: self.comfyui, GeracaoMotor.tts: self.tts,
             GeracaoMotor.claude: self.claude}[job.motor](job, beat)
            return "ok"
        except Parado:
            fila.devolver(job)
            log.info("geração %s devolvida à fila (gerador parado)", job.id)
            return "devolvida"
        except Cancelada:
            if self.stop.is_set():
                fila.devolver(job)
                return "devolvida"
            log.info("geração %s cancelada ou retomada; resultado descartado", job.id)
            return "cancelada"
        except MotorErro as exc:
            log.warning("geração %s: %s (%s)", job.id, exc.codigo, exc.detalhe[-500:])
            efeito = erros.decidir(exc, job.attempts)
            if efeito.acao == "esperar":
                fila.para_espera(job, efeito.codigo, efeito.mensagem, efeito.depois,
                                 conta_tentativa=efeito.conta_tentativa)
                return "espera"
            fila.para_falhou(job, efeito.codigo, efeito.mensagem)
            return "falhou"
        except Exception as exc:  # qualquer outra falha vira "falhou", nunca some
            hd = datadir.status().reason == "sem_sentinela"
            if hd or (isinstance(exc, ApiError) and exc.status in (503, 507)):
                fila.para_falhou(job, "internal", HD_FORA if hd else exc.message)
                log.warning("geração %s: HD de dados indisponível", job.id)
                return "falhou"
            if isinstance(exc, ApiError) and exc.status == 400:  # imagem inválida do motor
                fila.para_falhou(job, "entrada_invalida", "O motor devolveu um arquivo inválido")
                return "falhou"
            log.exception("erro interno na geração %s", job.id)
            fila.para_falhou(job, "internal", erros.MENSAGENS["internal"])
            return "falhou"
        finally:
            beat.parar()


def audios_key(db: Session, audio_id: str) -> str:
    from sociman_api.geracao.models import Audio

    a = db.get(Audio, uuid.UUID(audio_id))
    if a is None:
        raise MotorErro("entrada_invalida", "A gravação de referência não existe mais")
    return a.object_key


# ---- linhas ----

class LinhaGpu:
    def __init__(self, clientes: Clientes, stop: threading.Event):
        self.c = clientes
        self.stop = stop
        self.executor = Executor(clientes, stop)
        self.travada = False
        self.sondagem: dict[str, str] = {}
        self.sondado_em = float("-inf")

    # RAM do ComfyUI (R4)
    def devolver_ram(self) -> bool:
        """Devolve 12 GB e confere. "Não coube" → `/free` no ComfyUI e tenta de novo."""
        if self.c.memoria is None:
            return True
        for tentativa in range(1, NAO_COUBE_TENTATIVAS + 1):
            try:
                self.c.memoria.devolver()
                self.travada = False
                return True
            except MemoriaErro as exc:
                log.error("RAM do ComfyUI não voltou a 12 GB (%s)", exc.motivo)
                if exc.motivo == "nao_coube" and tentativa < NAO_COUBE_TENTATIVAS:
                    try:
                        self.c.comfy.free(unload_models=True)
                    except MotorErro:
                        pass
                    continue
                break
        self.travada = True
        return False

    def conferir_ao_subir(self) -> None:
        """Ao iniciar: se a RAM não está em 12 GB, registra e devolve antes de qualquer job."""
        if self.c.memoria is None:
            return
        try:
            m = self.c.memoria.ler()
        except MemoriaErro as exc:
            log.error("não foi possível ler a RAM do ComfyUI (%s); linha GPU travada", exc.motivo)
            self.travada = True
            return
        if m.estado != "normal":
            log.error("a RAM do ComfyUI está em %d bytes ao iniciar; devolvendo", m.memoria_bytes)
            self.devolver_ram()

    def _soltar_outro(self, motor: GeracaoMotor) -> None:
        """FR-022: libera a VRAM do outro motor (falha aqui não impede: a VRAM é conferida)."""
        try:
            if motor == GeracaoMotor.comfyui:
                self.c.tts.unload()
            else:
                self.c.comfy.free(unload_models=True)
        except (MotorErro, ValueError):
            log.info("não foi possível soltar o outro motor antes de %s", motor.value)

    def _gpu_livre(self, motor: GeracaoMotor) -> gpu.Estado:
        with _session() as db:
            estado = gpu.gpu_livre(db, motor, self.c.comfy)
        if estado == "fora" and motor == GeracaoMotor.tts:
            # Sem o ComfyUI, ele não ocupa a GPU: vale o que o shop-tts informa, se informar.
            try:
                livre_mb = self.c.tts.health().get("vram_free_mb")
            except MotorErro:
                return "fora"
            if livre_mb is None or float(livre_mb) / 1024 >= gpu.piso_gb(motor):
                return "livre"
            return "pouca_vram"
        return estado

    def volta(self) -> str | None:
        """Uma volta. None = nada feito (espera curta); texto = o que aconteceu."""
        fila.requeue_stale()
        if self.travada:
            return "travada" if not self.devolver_ram() else "destravada"
        if datadir.status().reason == "sem_sentinela":
            return None
        motores = set(MOTORES_GPU)
        if self.c.memoria is None:
            motores.discard(GeracaoMotor.comfyui)
            fila.marcar_mensagem({GeracaoMotor.comfyui}, SEM_MEMORIA_CFG)
        nxt = fila.proxima(motores)
        if nxt is None:
            return None
        self._soltar_outro(nxt.motor)
        estado = self._gpu_livre(nxt.motor)
        if estado in ("openshorts", "pouca_vram"):
            fila.aguardar_gpu(motores)
            return "aguardando_gpu"
        job = fila.claim(nxt.id)
        if job is None:
            return None
        log.info("geração %s (%s, %s): tentativa %d", job.id, job.passo, job.motor.value,
                 job.attempts)
        if estado == "fora":  # o ComfyUI não respondeu na conferência da VRAM (R3)
            efeito = erros.decidir(MotorErro("servico_fora"), job.attempts)
            if efeito.acao == "esperar":
                fila.para_espera(job, efeito.codigo, efeito.mensagem, efeito.depois)
            else:
                fila.para_falhou(job, efeito.codigo, efeito.mensagem)
            return "servico_fora"
        if job.motor != GeracaoMotor.comfyui:
            return self.executor.executar(job)
        try:
            self.c.memoria.subir()
        except MemoriaErro as exc:
            log.error("não foi possível subir a RAM do ComfyUI (%s)", exc.motivo)
            efeito = erros.decidir(MotorErro("servico_fora", SEM_RAM), job.attempts)
            if efeito.acao == "esperar":
                fila.para_espera(job, "servico_fora", SEM_RAM, efeito.depois)
            else:
                fila.para_falhou(job, efeito.codigo, efeito.mensagem)
            self.devolver_ram()
            return "sem_ram"
        try:
            return self.executor.executar(job)
        finally:
            self.devolver_ram()

    def run(self) -> None:
        self.conferir_ao_subir()
        while not self.stop.is_set():
            espera = IDLE_S
            try:
                r = self.volta()
                if r == "travada":
                    espera = TRAVADA_S
                elif r is not None and r != "aguardando_gpu":
                    espera = 0
            except Exception:  # a linha não morre por uma falha passageira
                log.exception("falha na linha GPU do gerador")
                espera = get_settings().worker_poll_s
            publicar_estado(self)
            if espera:
                self.stop.wait(espera)


class LinhaClaude:
    def __init__(self, clientes: Clientes, stop: threading.Event):
        self.stop = stop
        self.executor = Executor(clientes, stop)

    def volta(self) -> str | None:
        nxt = fila.proxima({GeracaoMotor.claude})
        if nxt is None:
            return None
        job = fila.claim(nxt.id)
        return self.executor.executar(job) if job is not None else None

    def run(self) -> None:
        while not self.stop.is_set():
            espera = IDLE_S
            try:
                if self.volta() is not None:
                    espera = 0
            except Exception:
                log.exception("falha na linha Claude do gerador")
                espera = get_settings().worker_poll_s
            if espera:
                self.stop.wait(espera)


# ---- estado para as integrações ----

SONDA_S = 30.0  # o ComfyUI, o shop-tts e a GPU são sondados no máximo a cada 30 s


def _sondar(linha: LinhaGpu) -> dict[str, str]:
    s = get_settings()
    out: dict[str, str] = {}
    if not s.comfyui_url.strip():
        out["comfyui"] = "nao_configurado"
    else:
        try:
            linha.c.comfy.system_stats()
            out["comfyui"] = "ok"
        except MotorErro:
            out["comfyui"] = "fora"
    if not s.shop_tts_url.strip():
        out["shopTts"] = "nao_configurado"
    else:
        try:
            linha.c.tts.health()
            out["shopTts"] = "ok"
        except MotorErro:
            out["shopTts"] = "fora"
    with _session() as db:
        g = gpu.gpu_livre(db, GeracaoMotor.comfyui, linha.c.comfy)
    out["gpu"] = "desconhecida" if g == "fora" else g
    return out


def publicar_estado(linha: LinhaGpu, agora: float | None = None) -> None:
    """O estado para o `GET /api/integracoes` (a API não alcança a rede `gpu-local`)."""
    import time

    agora = time.monotonic() if agora is None else agora
    try:
        if agora - linha.sondado_em >= SONDA_S:
            linha.sondagem = _sondar(linha)
            linha.sondado_em = agora
        from sociman_api.redis import get_redis

        memoria = "nao_configurado" if linha.c.memoria is None else (
            "travada" if linha.travada else "ok")
        get_redis().set(ESTADO_KEY, json.dumps({**linha.sondagem, "memoriaComfyui": memoria}),
                        ex=ESTADO_TTL_S)
    except Exception:  # o Redis fora não para o gerador
        log.debug("não foi possível publicar o estado do gerador", exc_info=True)


def estado() -> dict[str, Any] | None:
    """O que o gerador publicou há menos de 1 min (None = parado)."""
    try:
        from sociman_api.redis import get_redis

        raw = get_redis().get(ESTADO_KEY)
    except Exception:  # noqa: BLE001 — Redis fora: vale como gerador parado
        return None
    return json.loads(raw) if raw else None


# ---- processo ----

def _registrar_modelos() -> None:
    from sociman_api.agendador import _registrar_modelos as base
    from sociman_api.assets import models as _assets  # noqa: F401
    from sociman_api.geracao import models as _geracao  # noqa: F401
    from sociman_api.ia import models as _ia  # noqa: F401
    from sociman_api.produtos import aplicadores as _produtos  # noqa: F401 — spec 012

    base()


def _pegar_lock(engine: Engine, stop: threading.Event):
    avisou = False
    while not stop.is_set():
        conn = None
        try:
            conn = engine.connect()
            ok = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
            conn.commit()
            if ok:
                return conn
            conn.close()
            if not avisou:
                log.info("outro gerador tem o lock; esperando sem trabalhar")
                avisou = True
        except Exception:
            if conn is not None:
                conn.close()
            log.warning("banco indisponível para o lock do gerador", exc_info=True)
        stop.wait(ESPERA_LOCK_S)
    return None


def run(stop: threading.Event, clientes: Clientes | None = None,
        engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    conn = _pegar_lock(engine, stop)
    if conn is None:
        return
    try:
        clientes = clientes or clientes_padrao()
        gpu_linha, claude_linha = LinhaGpu(clientes, stop), LinhaClaude(clientes, stop)
        t = threading.Thread(target=claude_linha.run, name="linha-claude", daemon=True)
        t.start()
        log.info("gerador pronto (lock ok): ComfyUI em %s; shop-tts em %s; memória %s",
                 clientes.comfy.base_url, clientes.tts.base_url,
                 "configurada" if clientes.memoria else "NÃO configurada (sem jobs comfyui)")
        gpu_linha.run()
        t.join(timeout=30)
    finally:
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            conn.commit()
        except Exception:
            log.warning("não foi possível soltar o lock do gerador", exc_info=True)
        conn.close()


def main() -> None:
    """`sociman gerador`: SIGTERM ou SIGINT devolvem a geração atual à fila e param."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _registrar_modelos()
    stop = threading.Event()

    def _stop(signum: int, _frame: Any) -> None:
        log.info("sinal %s: parando depois de devolver a geração atual à fila", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    run(stop)
    log.info("gerador parado")
