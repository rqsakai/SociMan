"""Agendador das tarefas periódicas (spec 006, research R1): `sociman agendador`.

Um processo por stack (serviço `agendador` do compose, a mesma imagem da API):
1. pega o advisory lock `0x50C1` do Postgres numa conexão dedicada. Sem o lock (outra instância
   ativa), espera sem trabalhar e tenta de novo;
2. com o lock, sobe uma thread por trilha (`sync`, `openshorts`, `importacao`, `lembretes`).
   Cada volta abre uma sessão própria, chama `rodar(db)` do módulo da trilha e faz o commit; uma
   exceção vai para o log (rollback) e a trilha segue na próxima volta, sem derrubar as outras;
3. SIGTERM ou SIGINT param as trilhas no fim da volta atual e soltam o lock.

O estado fica todo no Postgres (`status`, `next_*_at`): reiniciar retoma de onde parou. Uma
trilha pode ficar ociosa com um motivo (chave ausente, HD fora); o motivo vai para o log uma vez
a cada mudança.
"""

import logging
import signal
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session, sessionmaker

from sociman_api import datadir
from sociman_api.config import get_settings
from sociman_api.db import get_engine

log = logging.getLogger("sociman.agendador")

LOCK_KEY = 0x50C1
ESPERA_LOCK_S = 5.0  # sem o lock: tenta de novo a cada 5 s
VIGIA_LOCK_S = 30.0  # confere se a conexão do lock continua viva


@dataclass(frozen=True)
class Trilha:
    nome: str
    intervalo_s: float
    rodar: Callable[[Session], Any]
    # None = pode rodar; texto = motivo para ficar ociosa nesta volta.
    ociosa: Callable[[], str | None] = lambda: None


def _sem_youtube() -> str | None:
    if not get_settings().youtube_api_key.get_secret_value():
        return "YOUTUBE_API_KEY não configurada: nenhum canal é sincronizado"
    return None


def _sem_hd() -> str | None:
    if datadir.status().reason == "sem_sentinela":
        return "HD de dados sem o sentinela: nenhum envio é importado"
    return None


def _publicacao_ociosa() -> str | None:
    """Spec 015 (R6): a trilha `publicacao` só roda com o nível do servidor ligado, a chave dos
    tokens e o HD. Com ela ociosa, nenhum pedido sai para a rede (princípio I)."""
    from sociman_api.publicacao import cifra

    if not get_settings().publicacao_habilitada:
        return "PUBLICACAO_HABILITADA desligada no servidor: nada é enviado às redes"
    if not cifra.chave_configurada():
        return "chave dos tokens ausente (SOCIMAN_TOKENS_KEY): nada é enviado às redes"
    if datadir.status().reason == "sem_sentinela":
        return "HD de dados sem o sentinela: nada é enviado às redes"
    return None


def _metricas_ociosa() -> str | None:
    """Spec 016 (R3): a trilha `metricas` só lê. Não depende de `PUBLICACAO_HABILITADA`, do
    botão "Envios automáticos" nem do HD; só do próprio interruptor, do app e da chave."""
    from sociman_api.publicacao import cifra, conexoes

    if not get_settings().metricas_coleta_habilitada:
        return "METRICAS_COLETA_HABILITADA desligada no servidor: nenhuma métrica é coletada"
    if not conexoes.app_configurado():
        return "app da TikTok não configurado: nenhuma métrica é coletada"
    if not cifra.chave_configurada():
        return "chave dos tokens ausente (SOCIMAN_TOKENS_KEY): nenhuma métrica é coletada"
    return None


def trilhas_padrao() -> list[Trilha]:
    """As trilhas de R1 e a `publicacao` da 015, com os intervalos da config (import tardio
    dos módulos)."""
    from sociman_api.canais import sync
    from sociman_api.envios import acompanhamento, importacao
    from sociman_api.metricas import coleta as metricas
    from sociman_api.postagem import lembretes
    from sociman_api.publicacao import trilha as publicacao

    s = get_settings()
    return [
        Trilha("sync", s.agendador_sync_s, sync.rodar, _sem_youtube),
        Trilha("openshorts", s.agendador_openshorts_s, acompanhamento.rodar),
        Trilha("importacao", s.agendador_importacao_s, importacao.rodar, _sem_hd),
        Trilha("lembretes", s.agendador_lembretes_s, lembretes.rodar),
        Trilha("publicacao", s.agendador_publicacao_s, publicacao.rodar, _publicacao_ociosa),
        Trilha("metricas", s.agendador_metricas_s, metricas.rodar, _metricas_ociosa),  # 016
    ]


def _registrar_modelos() -> None:
    """Fora da API, nada mais registra as tabelas das FKs (como no worker da 004)."""
    from sociman_api import history  # noqa: F401
    from sociman_api.auth import models as _auth  # noqa: F401
    from sociman_api.canais import models as _canais  # noqa: F401
    from sociman_api.conteudos import models as _conteudos  # noqa: F401 — spec 014
    from sociman_api.cortes import models as _cortes  # noqa: F401
    from sociman_api.envios import models as _envios  # noqa: F401
    from sociman_api.marca import models as _marca  # noqa: F401
    from sociman_api.metricas import models as _metricas  # noqa: F401 — spec 016
    from sociman_api.notificacoes import models as _notificacoes  # noqa: F401
    from sociman_api.perfis import models as _perfis  # noqa: F401
    from sociman_api.postagem import models as _postagem  # noqa: F401
    from sociman_api.publicacao import models as _publicacao  # noqa: F401 — spec 015


class _Laco(threading.Thread):
    def __init__(self, trilha: Trilha, sessions: sessionmaker[Session], stop: threading.Event):
        super().__init__(name=f"trilha-{trilha.nome}", daemon=True)
        self.trilha = trilha
        self.sessions = sessions
        self.stop = stop
        self.voltas = 0
        self.erros = 0
        self._motivo: str | None = None

    def volta(self) -> None:
        motivo = self.trilha.ociosa()
        if motivo != self._motivo:
            if motivo:
                log.warning("trilha %s ociosa: %s", self.trilha.nome, motivo)
            else:
                log.info("trilha %s ativa", self.trilha.nome)
            self._motivo = motivo
        if motivo:
            return
        with self.sessions() as db:
            try:
                self.trilha.rodar(db)
                db.commit()
            except Exception:
                db.rollback()
                raise

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                self.volta()
            except Exception:  # uma volta com erro não derruba a trilha nem o processo
                self.erros += 1
                log.exception("falha na trilha %s", self.trilha.nome)
            self.voltas += 1
            self.stop.wait(self.trilha.intervalo_s)


class Agendador:
    def __init__(self, trilhas: Sequence[Trilha] | None = None, engine: Engine | None = None,
                 lock_key: int = LOCK_KEY, espera_lock_s: float = ESPERA_LOCK_S,
                 vigia_s: float = VIGIA_LOCK_S):
        self.engine = engine or get_engine()
        self.trilhas = list(trilhas) if trilhas is not None else trilhas_padrao()
        self.lock_key = lock_key
        self.espera_lock_s = espera_lock_s
        self.vigia_s = vigia_s
        self.lacos: list[_Laco] = []
        self.com_lock = threading.Event()

    def _pegar_lock(self, stop: threading.Event) -> Connection | None:
        """Conexão dedicada com o lock, ou None se `stop` chegou antes."""
        avisou = False
        while not stop.is_set():
            conn: Connection | None = None
            try:
                conn = self.engine.connect()
                ok = conn.execute(text("SELECT pg_try_advisory_lock(:k)"),
                                  {"k": self.lock_key}).scalar()
                conn.commit()  # o lock é de sessão: sobrevive ao fim da transação
                if ok:
                    return conn
                conn.close()
                if not avisou:
                    log.info("outra instância do agendador tem o lock; esperando sem trabalhar")
                    avisou = True
            except Exception:
                if conn is not None:
                    conn.close()
                log.warning("banco indisponível para o lock do agendador", exc_info=True)
            stop.wait(self.espera_lock_s)
        return None

    def _soltar_lock(self, conn: Connection) -> None:
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": self.lock_key})
            conn.commit()
        except Exception:  # conexão já perdida: o lock caiu com ela
            log.warning("não foi possível soltar o lock explicitamente", exc_info=True)
        finally:
            conn.close()
            self.com_lock.clear()

    def _lock_vivo(self, conn: Connection) -> bool:
        try:
            conn.execute(text("SELECT 1"))
            conn.commit()
            return True
        except Exception:
            log.exception("conexão do lock perdida; parando as trilhas para pegar o lock de novo")
            return False

    def run(self, stop: threading.Event) -> None:
        """Até `stop`: pega o lock, roda as trilhas e, se o lock cair, recomeça."""
        sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        while not stop.is_set():
            conn = self._pegar_lock(stop)
            if conn is None:
                return
            self.com_lock.set()
            parar_trilhas = threading.Event()
            self.lacos = [_Laco(t, sessions, parar_trilhas) for t in self.trilhas]
            for laco in self.lacos:
                laco.start()
            log.info("agendador pronto (lock ok): trilhas %s",
                     ", ".join(t.nome for t in self.trilhas))
            while not stop.wait(self.vigia_s):
                if not self._lock_vivo(conn):
                    break
            parar_trilhas.set()
            for laco in self.lacos:
                laco.join()
            self._soltar_lock(conn)


def main() -> None:
    """`sociman agendador`: SIGTERM ou SIGINT param as trilhas e soltam o lock."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _registrar_modelos()
    stop = threading.Event()

    def _stop(signum: int, _frame: Any) -> None:
        log.info("sinal %s: parando as trilhas no fim da volta atual", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    s = get_settings()
    log.info("agendador no ar (OpenShorts em %s; YouTube %s; HD em %s)", s.openshorts_url,
             "configurado" if s.youtube_api_key.get_secret_value() else "sem chave", s.data_dir)
    Agendador().run(stop)
    log.info("agendador parado")
