"""Progresso real de um job do OpenShorts (FR-010a, emenda de 2026-09-29): puro, sem banco.

`interpretar({status, logs, queue, partial})` devolve a etapa em que o job está, o % da etapa
quando o OpenShorts o informa, "clipe N de M", a posição na fila, uma frase curta em pt-BR e um %
geral estimado e ponderado por etapa. As frases de log vêm do `main.py`, do
`transcribe_backends.py` e do `scene_detection.py` do OpenShorts (self-host: `logs` é a saída
crua do pipeline, uma linha por `\\n`; barras do tqdm e do yt-dlp chegam como uma linha com vários
trechos separados por `\\r`, e só quando a barra termina).

Robustez: linha desconhecida (ruído do TensorFlow, `UserWarning`, `[debug]` do yt-dlp, segmentos
da transcrição) não muda nada; sem nenhum marco reconhecido, a etapa é a `anterior`. Nada aqui
levanta exceção por causa do conteúdo dos logs.

Clipes: o OpenShorts gera até 3 em paralelo, na ordem do score. "Clipe N de M" é o próximo a
ficar pronto (prontos + 1), e o % da etapa é prontos ÷ previstos.
"""

import enum
import re
from dataclasses import dataclass
from typing import Any


class EnvioEtapa(enum.StrEnum):
    fila = "fila"
    baixando = "baixando"
    transcrevendo = "transcrevendo"
    escolhendo_momentos = "escolhendo_momentos"
    processando_clipes = "processando_clipes"
    legendas = "legendas"
    importando = "importando"
    concluido = "concluido"
    erro = "erro"


Etapa = EnvioEtapa  # nome curto aqui dentro; no OpenAPI, `EnvioEtapa`
ETAPAS = frozenset(e.value for e in Etapa)


# Faixa de cada etapa no % geral: (início, largura). A CPU passa mais tempo transcrevendo e
# gerando os clipes (job real de 2026-09-29: download 40 s, transcrição 6–13 min, escolha 1 min,
# ~4 min por clipe com 3 em paralelo).
FAIXAS: dict[Etapa, tuple[int, int]] = {
    Etapa.fila: (0, 0),
    Etapa.baixando: (0, 5),
    Etapa.transcrevendo: (5, 30),
    Etapa.escolhendo_momentos: (35, 5),
    Etapa.processando_clipes: (40, 50),
    Etapa.legendas: (90, 10),
    Etapa.importando: (90, 10),
    Etapa.concluido: (100, 0),
}
PIPELINE = (Etapa.baixando, Etapa.transcrevendo, Etapa.escolhendo_momentos,
            Etapa.processando_clipes)  # as etapas de um job `processing` no OpenShorts

ROTULO: dict[Etapa, str] = {
    Etapa.fila: "Na fila do OpenShorts",
    Etapa.baixando: "Baixando o vídeo",
    Etapa.transcrevendo: "Transcrevendo o vídeo",
    Etapa.escolhendo_momentos: "Escolhendo os momentos",
    Etapa.processando_clipes: "Cortando os clipes",
    Etapa.legendas: "Aplicando legendas do kit",
    Etapa.importando: "Importando",
    Etapa.concluido: "Pronto",
    Etapa.erro: "Erro",
}


@dataclass(frozen=True)
class Progresso:
    etapa: Etapa
    etapa_pct: int | None = None
    clipe_atual: int | None = None
    clipes_previstos: int | None = None
    posicao_fila: int | None = None
    mensagem: str = ""
    progresso_geral: int = 0


def geral(etapa: Etapa, fracao: float | None) -> int:
    """% geral estimado: início da faixa da etapa + a fração dela (0..1)."""
    inicio, largura = FAIXAS.get(etapa, (0, 0))
    f = min(max(fracao or 0.0, 0.0), 1.0)
    return int(min(100, max(0, inicio + largura * f)))


def _pct(value: Any) -> int | None:
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return None


def _int_pos(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


# ---- marcos do log (a primeira regra que casa vence; ancoradas para não casar texto livre) ----

_RUIDO = re.compile(
    r"^(\[debug\]|\[youtube\]|\[info\]|\[Merger\]|W\d{4} |I\d{4} |INFO:|WARNING:|Title:|"
    r"\[\d+(\.\d+)?s -> |tensor = |Deleting original|original url)"
    r"|UserWarning|DeprecationWarning"
)
_DOWNLOAD_PCT = re.compile(r"^\[download\]\s+(\d+(?:\.\d+)?)%")
_BAIXANDO = re.compile(
    r"^(📥 Download|🔍 Debug: yt-dlp|\[download\]|🌐 |🍪 |⚠️ YOUTUBE_COOKIES|⚠️ +Download attempt)"
)
_BAIXADO = re.compile(r"^✅ (Video downloaded|Download succeeded)")
_PREPARANDO = re.compile(r"^(🎛️ +Choosing a layout|🎬 Layout:|✅ Enabled:|↕️ |"
                         r"✂️ (The downloaded source|Clipping the first))")
_TRANSCREVENDO_PCT = re.compile(r"^🎙️ Transcribing… (\d+)%")
_AGUARDANDO_ASR = re.compile(r"^🎙️ Waiting for a free transcription slot")
_TRANSCREVENDO = re.compile(r"^🎙️ +Transcribing (video|audio)")
_TRANSCRITO = re.compile(r"^(Detected language '|🧹 \[ASR\]|⏩ Reusing precomputed transcript|"
                         r"♻️ Reusing the transcript)")
_ESCOLHENDO = re.compile(r"^(🤖 +(Analyzing with|Model:)|🎥 +(Silent video|Model:)|🔇 )")
_JANELAS = re.compile(r"^Built \d+ scoring window")
_SHORTLIST = re.compile(r"^(Shortlisted \d+ window|Detail returned|Recovered \d+ clip|Kept the|"
                        r"Dropped \d+ clip|💰 )")
_ACHOU = re.compile(r"^🔥 Found (\d+) (?:viral )?clips")
_SEM_ANALISE = re.compile(r"^⏩ Skipping analysis")
_PROCESSANDO_CLIPE = re.compile(r"^🎬 Processing Clip (\d+):")
_CLIPE_PRONTO = re.compile(r"^✅ Clip (\d+) ready")
_CLIPE_FALHOU = re.compile(r"^❌ Clip (\d+) failed again")
_CENAS = re.compile(r"Analyzing Scenes:\s+(\d+)%")
_REENFILEIRADO = re.compile(r"^🔁 A temporary server problem interrupted")


@dataclass
class _Estado:
    etapa: Etapa | None = None
    pct: int | None = None
    aguardando_asr: bool = False
    sub: float = 0.0  # fração interna da escolha de momentos (sem % visível)
    previstos: int | None = None
    prontos: set[int] | None = None
    falhos: set[int] | None = None
    cenas_pct: int | None = None  # última barra de cenas, se ainda não terminou


def _trechos(line: Any) -> list[str]:
    """Os trechos de uma linha (barras do tqdm/yt-dlp: vários `\\r`); o último é o atual."""
    text = str(line) if line is not None else ""
    return [t.strip() for t in text.split("\r") if t.strip()]


def _ler_logs(logs: Any) -> _Estado:
    st = _Estado(prontos=set(), falhos=set())
    if not isinstance(logs, list):
        return st
    for line in logs:
        trechos = _trechos(line)
        if not trechos:
            continue
        atual = trechos[-1]
        if _RUIDO.search(atual):
            continue
        _aplicar(st, atual)
    return st


def _ir(st: _Estado, etapa: Etapa, pct: int | None = None) -> None:
    if st.etapa != etapa:
        st.aguardando_asr = False
        st.sub = 0.0
    st.etapa = etapa
    st.pct = pct


def _aplicar(st: _Estado, t: str) -> None:
    assert st.prontos is not None and st.falhos is not None
    if m := _DOWNLOAD_PCT.match(t):
        _ir(st, Etapa.baixando, _pct(m.group(1)))
    elif _BAIXADO.match(t):
        _ir(st, Etapa.baixando, 100)
    elif _BAIXANDO.match(t):
        if st.etapa != Etapa.baixando:
            _ir(st, Etapa.baixando)
    elif _PREPARANDO.match(t):
        _ir(st, Etapa.baixando, 100)
    elif m := _TRANSCREVENDO_PCT.match(t):
        _ir(st, Etapa.transcrevendo, _pct(m.group(1)))
    elif _AGUARDANDO_ASR.match(t):
        _ir(st, Etapa.transcrevendo, 0)
        st.aguardando_asr = True
    elif _TRANSCREVENDO.match(t):
        if st.etapa != Etapa.transcrevendo:
            _ir(st, Etapa.transcrevendo, 0)
    elif _TRANSCRITO.match(t):
        _ir(st, Etapa.transcrevendo, 100)
    elif _ESCOLHENDO.match(t):
        if st.etapa != Etapa.escolhendo_momentos:
            _ir(st, Etapa.escolhendo_momentos)
    elif _JANELAS.match(t):
        _ir(st, Etapa.escolhendo_momentos)
        st.sub = max(st.sub, 0.3)
    elif _SHORTLIST.match(t):
        _ir(st, Etapa.escolhendo_momentos)
        st.sub = max(st.sub, 0.6)
    elif m := _ACHOU.match(t):
        _ir(st, Etapa.processando_clipes)
        st.previstos = int(m.group(1))
    elif _SEM_ANALISE.match(t):
        _ir(st, Etapa.processando_clipes)
        st.previstos = st.previstos or 1
    elif _PROCESSANDO_CLIPE.match(t):
        _ir(st, Etapa.processando_clipes)
        st.cenas_pct = None
    elif m := _CLIPE_PRONTO.match(t):
        _ir(st, Etapa.processando_clipes)
        st.prontos.add(int(m.group(1)))
        st.cenas_pct = None
    elif m := _CLIPE_FALHOU.match(t):
        _ir(st, Etapa.processando_clipes)
        st.falhos.add(int(m.group(1)))
    elif m := _CENAS.search(t):
        pct = _pct(m.group(1))
        if st.etapa == Etapa.processando_clipes:
            st.cenas_pct = pct if pct is not None and pct < 100 else None
    elif _REENFILEIRADO.match(t):
        _ir(st, Etapa.fila)


def _clipes_prontos(status: dict[str, Any]) -> int:
    result = status.get("result")
    clips = result.get("clips") if isinstance(result, dict) else None
    return len(clips) if isinstance(clips, list) else 0


def _parcial(partial: Any) -> str:
    if isinstance(partial, dict):
        minutos = partial.get("processed_minutes")
        if isinstance(minutos, (int, float)) and not isinstance(minutos, bool) and minutos > 0:
            return f" (primeiros {minutos:g} min)"
    return ""


def _ultima_linha(logs: Any) -> str:
    if not isinstance(logs, list):
        return ""
    for line in reversed(logs):
        trechos = _trechos(line)
        if trechos:
            return trechos[-1][:300]
    return ""


def fila(posicao: int | None = None, mensagem: str | None = None) -> Progresso:
    texto = mensagem or (f"{ROTULO[Etapa.fila]} ({posicao}º)" if posicao else ROTULO[Etapa.fila])
    return Progresso(Etapa.fila, posicao_fila=posicao, mensagem=texto, progresso_geral=0)


def clipes(etapa: Etapa, feitos: int, total: int) -> Progresso:
    """Legendas e importação (trilha `importacao`): clipe N de M, % geral 90..100."""
    total = max(total, 0)
    atual = min(feitos + 1, total) if total else None
    pct = round(100 * feitos / total) if total else None
    mensagem = f"{ROTULO[etapa]} {atual} de {total}" if total and atual else ROTULO[etapa]
    return Progresso(etapa, etapa_pct=pct, clipe_atual=atual, clipes_previstos=total or None,
                     mensagem=mensagem, progresso_geral=geral(etapa, feitos / total if total else 0))


def interpretar(status: Any, anterior: Etapa | None = None) -> Progresso:
    """`status` é o JSON do `GET /api/status/{job}`; `anterior`, a última etapa gravada."""
    if not isinstance(status, dict):
        status = {}
    estado = status.get("status")
    logs = status.get("logs")
    queue = status.get("queue")
    posicao = _int_pos(queue.get("position")) if isinstance(queue, dict) else None

    if estado == "queued":
        return fila(posicao)
    if estado == "completed":
        n = _clipes_prontos(status)
        return Progresso(Etapa.importando, etapa_pct=0, clipe_atual=None,
                         clipes_previstos=n or None, mensagem="Importando os clipes",
                         progresso_geral=geral(Etapa.importando, 0))
    if estado == "failed":
        linha = _ultima_linha(logs)
        return Progresso(Etapa.erro, mensagem=(f"O OpenShorts falhou: {linha}" if linha
                                               else "O OpenShorts falhou"))

    st = _ler_logs(logs)
    assert st.prontos is not None and st.falhos is not None
    prontos_result = _clipes_prontos(status)
    if prontos_result:
        st.etapa = Etapa.processando_clipes  # há clipe pronto: a geração já começou
    # `processing` sem marco reconhecido: a etapa anterior, se era do pipeline.
    etapa = st.etapa if st.etapa in PIPELINE else anterior if anterior in PIPELINE else None
    sufixo = _parcial(status.get("partial"))

    if etapa == Etapa.processando_clipes:
        previstos = st.previstos
        feitos = max(len(st.prontos), prontos_result) + len(st.falhos - st.prontos)
        if previstos:
            feitos = min(feitos, previstos)
            atual = min(feitos + 1, previstos)
            pct = round(100 * feitos / previstos)
            mensagem = f"Cortando clipe {atual} de {previstos}"
            if st.cenas_pct is not None:
                mensagem += f" (cenas {st.cenas_pct}%)"
            return Progresso(etapa, etapa_pct=pct, clipe_atual=atual, clipes_previstos=previstos,
                             mensagem=mensagem + sufixo,
                             progresso_geral=geral(etapa, feitos / previstos))
        mensagem = f"{ROTULO[etapa]}: {feitos} pronto{'s' if feitos != 1 else ''}" if feitos \
            else ROTULO[etapa]
        return Progresso(etapa, mensagem=mensagem + sufixo, progresso_geral=geral(etapa, 0))

    if etapa == Etapa.transcrevendo:
        if st.aguardando_asr and not st.pct:
            return Progresso(etapa, etapa_pct=0, mensagem="Aguardando a vez de transcrever" + sufixo,
                             progresso_geral=geral(etapa, 0))
        pct = st.pct if st.etapa == etapa else None
        mensagem = f"{ROTULO[etapa]} {pct}%" if pct else ROTULO[etapa]
        return Progresso(etapa, etapa_pct=pct, mensagem=mensagem + sufixo,
                         progresso_geral=geral(etapa, (pct or 0) / 100))

    if etapa == Etapa.escolhendo_momentos:
        return Progresso(etapa, mensagem=ROTULO[etapa] + sufixo,
                         progresso_geral=geral(etapa, st.sub if st.etapa == etapa else 0))

    # baixando (ou "preparando", sem marco nenhum ainda)
    pct = st.pct if st.etapa == Etapa.baixando else None
    if etapa is None:
        mensagem = "Preparando o vídeo"
    elif pct == 100:
        mensagem = "Vídeo baixado, preparando"
    else:
        mensagem = f"{ROTULO[Etapa.baixando]} {pct}%" if pct else ROTULO[Etapa.baixando]
    return Progresso(Etapa.baixando, etapa_pct=pct, mensagem=mensagem + sufixo,
                     progresso_geral=geral(Etapa.baixando, (pct or 0) / 100))


# ---- gravar no envio e mostrar na API ----

def gravar(envio: Any, p: Progresso) -> None:
    """Copia o progresso para o envio (trilhas `openshorts` e `importacao`). O % geral não volta
    dentro do mesmo job; só a volta para a fila (job reenfileirado) o zera, e o erro o mantém.
    Sem etapa gravada (1ª leitura do job, ou um envio de antes da 0007 com a estimativa antiga), o
    % geral é o calculado."""
    primeira = envio.etapa is None
    envio.etapa = p.etapa.value
    envio.etapa_pct = p.etapa_pct
    envio.clipe_atual = p.clipe_atual
    envio.clipes_previstos = p.clipes_previstos
    envio.etapa_mensagem = p.mensagem[:300] or None
    if p.etapa == Etapa.fila:
        envio.progress = 0
        envio.openshorts_queue_pos = p.posicao_fila
    elif p.etapa != Etapa.erro:
        envio.progress = p.progresso_geral if primeira else max(envio.progress or 0,
                                                                  p.progresso_geral)
        envio.openshorts_queue_pos = None


def zerar(envio: Any) -> None:
    """Estado de progresso limpo (enviar, tentar de novo, enviar mesmo assim)."""
    envio.etapa = None
    envio.etapa_pct = None
    envio.clipe_atual = None
    envio.clipes_previstos = None
    envio.etapa_mensagem = None


@dataclass(frozen=True)
class Publico:
    etapa: Etapa | None
    etapa_pct: int | None
    clipe_atual: int | None
    clipes_previstos: int | None
    mensagem: str | None


def publico(envio: Any) -> Publico:
    """O que a API mostra: o gravado pelas trilhas enquanto o job anda; nos estados finais e na
    espera do SociMan, a etapa sai do `status` do envio."""
    status = str(getattr(envio.status, "value", envio.status))
    if status == "pronto":
        n = envio.clips_importados
        return Publico(Etapa.concluido, 100, None, envio.clips_total,
                       f"Pronto: {n} clipe{'s' if n != 1 else ''}")
    if status in ("falhou", "sem_clipes"):
        return Publico(Etapa.erro, None, None, envio.clipes_previstos,
                       envio.error_message or ROTULO[Etapa.erro])
    if status == "na_fila":
        return Publico(Etapa.fila, None, None, None, "Enviando ao OpenShorts")
    if status == "aguardando_openshorts":
        return Publico(Etapa.fila, None, None, None, "Aguardando o OpenShorts voltar")
    if status not in ("processando", "importando"):
        return Publico(None, None, None, None, None)
    etapa = Etapa(envio.etapa) if envio.etapa in ETAPAS else None
    if etapa is None:  # antes da primeira consulta
        if status == "importando":
            return Publico(Etapa.importando, None, None, envio.clips_total, "Importando os clipes")
        pos = envio.openshorts_queue_pos
        return Publico(Etapa.fila, None, None, None, fila(pos).mensagem)
    return Publico(etapa, envio.etapa_pct, envio.clipe_atual, envio.clipes_previstos,
                   envio.etapa_mensagem)

