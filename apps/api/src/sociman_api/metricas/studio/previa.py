"""Pré-visualização (research R4; data-model "Estado efêmero" e "Contagens").

Arquivos → formato → datas → conta e @ → contagens contra o valor efetivo → avisos. O resultado
da leitura (poucos KB, sem os arquivos) vai para o Redis em `studio:previa:<uuid>`, por 30 min e
de uso único (`consumir` faz `GETDEL`). Nada vai para o PostgreSQL, o MinIO ou o disco.

A `base` é a impressão da série no momento da leitura (importações ativas com a versão e o 1º
dia coberto): o confirmar recalcula sob o lock da série e recusa se mudou.

**Público (spec 022, R5 e R8):** as seções de público vão em `publico[]` (as da 020 continuam em
`secoes[]`), com a foto datada (`publico.data_foto`), o pico da atividade e os totais dos
espectadores. A seção só com o cabeçalho é "vazia": não entra nas linhas do Redis, só em
`vazias`; um envio só de vazias é recusado (`studio_sem_dados`). O ano das seções diárias segue
`datas.ORDEM_ANCORA`.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sociman_api.auth.deps import Actor
from sociman_api.auth.models import User
from sociman_api.errors import ApiError
from sociman_api.metricas.models import Serie
from sociman_api.metricas.studio import arquivos, datas, efetivo, formato, publico, schemas
from sociman_api.metricas.studio.formato import (
    ATIVIDADE,
    ESPECTADORES,
    FOTOS,
    GENERO,
    PUBLICO,
    SEGUIDORES,
    TERRITORIOS,
    VISAO_GERAL,
    Leitura,
    Problema,
)
from sociman_api.metricas.studio.models import Importacao, ImportacaoEstado
from sociman_api.perfis.models import Conta, Perfil, Platform
from sociman_api.redis import get_redis

TTL = timedelta(minutes=30)
CHAVE = "studio:previa:{}"
PROBLEMAS_MAX = 50
AMOSTRA_PONTA = 5
DIVERGENCIA_MAX = 0.30
PERIODO_LONGO_DIAS = 366
CAMPOS = {VISAO_GERAL: ("views", "visitas_perfil", "likes", "comments", "shares"),
          SEGUIDORES: ("seguidores", "seguidores_dif")}
# A coluna de SHA de cada seção (o confirmar usa o mesmo mapa).
SHA = {VISAO_GERAL: "sha_visao_geral", SEGUIDORES: "sha_seguidores", GENERO: "sha_genero",
       TERRITORIOS: "sha_territorios", ATIVIDADE: "sha_atividade",
       ESPECTADORES: "sha_espectadores"}
ROTULOS = {VISAO_GERAL: "Visão geral", SEGUIDORES: "Seguidores", GENERO: "Gênero",
           TERRITORIOS: "Territórios", ATIVIDADE: "Atividade dos seguidores",
           ESPECTADORES: "Espectadores"}
VAZIA = ("Ainda sem dados de público: a TikTok libera esses dados quando a conta tem mais "
         "seguidores (cerca de 100).")
SEM_DADOS = ("Os arquivos vieram sem dados de público: a TikTok libera esses dados quando a conta "
             "tem mais seguidores (cerca de 100). Reimporte quando a conta crescer.")
INDISPONIVEL = "Esta pré-visualização já foi usada ou expirou; envie os arquivos de novo"
DESATUALIZADA = "Os dados da conta mudaram desde a pré-visualização; envie os arquivos de novo"


# ---- conta e série ----

def serie_viva(db: Session, conta: Conta) -> Serie:
    serie = None
    if conta.platform == Platform.tiktok:
        serie = db.scalar(select(Serie).where(Serie.conta_id == conta.id,
                                              Serie.anonimizada_em.is_(None)))
    if serie is None:
        raise ApiError(409, "serie_indisponivel",
                       "Esta conta não tem métricas ativas: o histórico do Studio só entra numa "
                       "conta TikTok conectada com métricas.", details={"contaId": str(conta.id)})
    return serie


def conta_or_404(db: Session, conta_id: uuid.UUID) -> Conta:
    conta = db.get(Conta, conta_id)
    if conta is None:
        raise ApiError(404, "not_found", "Conta não encontrada")
    return conta


def base(db: Session, serie_id: uuid.UUID) -> dict[str, Any]:
    ativas = db.execute(select(Importacao.id, Importacao.version).where(
        Importacao.serie_id == serie_id, Importacao.estado == ImportacaoEstado.ativa)
        .order_by(Importacao.id)).all()
    primeiro = efetivo.primeiro_dia_coberto(db, [serie_id])[serie_id]
    return {"ativas": [[str(i), v] for i, v in ativas],
            "primeiroDiaCoberto": primeiro.isoformat() if primeiro else None}


# ---- leitura ----

@dataclass
class SecaoLida:
    leitura: Leitura
    arquivo: arquivos.Arquivo
    sha: str
    dias: list[date]  # um por linha, na ordem
    ano_origem: str  # nome_zip | deduzido
    com_ano: bool  # as datas do arquivo já trazem o ano (sem dedução)


@dataclass
class PublicoLido:
    """Uma seção de público lida e validada (spec 022)."""

    leitura: Leitura
    arquivo: arquivos.Arquivo
    sha: str
    itens: list[publico.Item]  # gênero e territórios
    linhas: list[dict[str, Any]]  # atividade {dia, hora, ativos}; espectadores {dia, …}
    ano_origem: str = "deduzido"
    com_ano: bool = False


def _onde(p: Problema) -> str:
    if p.celula:
        return f"{p.arquivo}, célula {p.celula}"
    return f"{p.arquivo}, linha {p.linha}" if p.linha is not None else p.arquivo


def _invalido(problemas: list[Problema]) -> ApiError:
    primeiros = problemas[:PROBLEMAS_MAX]
    linhas = "; ".join(
        _onde(p) + (f", {p.coluna}" if p.coluna else "")
        + (f" = \"{p.valor}\"" if p.valor is not None else "") + f": {p.motivo}"
        for p in primeiros[:3])
    mais = f" (e mais {len(problemas) - 3})" if len(problemas) > 3 else ""
    return ApiError(400, "studio_invalido",
                    f"O arquivo tem problemas e não foi importado: {linhas}{mais}.",
                    details={"problemas": [p.json() for p in primeiros],
                             "total": len(problemas)})


def _datas_erro(arquivo: str, motivo: str) -> ApiError:
    return ApiError(400, "studio_datas", f"{arquivo}: {motivo}",
                    details={"arquivo": arquivo, "motivo": motivo})


def _ler_datas(leitura: Leitura, problemas: list[Problema]) -> list[datas.DataLida]:
    lidas: list[datas.DataLida] = []
    for linha in leitura.linhas:
        d = datas.ler_data(linha.dia_bruto)
        if d is None:
            problemas.append(Problema(leitura.arquivo, linha.numero, formato.NOMES["dia"],
                                      linha.dia_bruto, "data inválida",
                                      linha.celulas.get("dia")))
        else:
            lidas.append(d)
    if lidas and len({d.ano is None for d in lidas}) > 1:
        problemas.append(Problema(leitura.arquivo, None, formato.NOMES["dia"], None,
                                  "datas com e sem ano no mesmo arquivo"))
    return lidas


def _leitura(a: arquivos.Arquivo, c: arquivos.Csv) -> Leitura:
    nome = a.nome if a.tipo in ("csv", "xlsx") else f"{a.nome}/{c.entrada}"
    if c.lida is not None:
        return formato.ler_linhas(nome, c.lida.cabecalho, c.lida.linhas, c.lida.celulas,
                                  c.lida.inicio)
    return formato.ler(nome, c.dados)


def _resolver(ds: list[datas.DataLida], hoje: date,
              ancoras: list[tuple[list[datas.DataLida], list[date], str]]
              ) -> tuple[list[date], str]:
    """Os anos de uma seção de público: com ano, como veio; senão, pelos dias da 1ª seção já
    resolvida que contém todos (`mesmo_mapa`), ou deduzidos (R4)."""
    if ds[0].ano is not None:
        return datas.com_ano(ds), "deduzido"
    for ref, anos, origem in ancoras:
        mapeados = datas.mesmo_mapa(ds, ref, anos)
        if mapeados is not None:
            return mapeados, origem
    return datas.deduzir(ds, hoje), "deduzido"


def ler(conta: Conta, uploads: list[arquivos.Upload], hoje: date
        ) -> tuple[list[arquivos.Arquivo], dict[str, SecaoLida], dict[str, PublicoLido],
                   list[tuple[str, arquivos.Arquivo]]]:
    """Lê e valida o envio inteiro (US2). Recusa por `ApiError` antes de qualquer prévia.
    Devolve (arquivos, seções da 020, seções de público, vazias)."""
    tz = efetivo.tz()
    enviados = arquivos.ler_envio(uploads)
    lidos = [arquivos.ler_arquivo(e, tz) for e in enviados]
    handle_conta = datas.normalizar_handle(conta.handle)
    for a in lidos:
        if a.handle is not None and a.handle != handle_conta:
            raise ApiError(400, "studio_conta_diferente",
                           f"O arquivo é de @{a.handle}, não de @{handle_conta}.",
                           details={"arquivo": a.nome, "handleArquivo": a.handle,
                                    "handleConta": handle_conta})

    leituras: list[tuple[Leitura, arquivos.Arquivo, str]] = []
    for a in lidos:
        for c in a.csvs:
            leituras.append((_leitura(a, c), a, c.sha))
    secoes = [lt.secao for lt, _, _ in leituras]
    if len(set(secoes)) != len(secoes):
        raise ApiError(400, "studio_arquivos",
                       "A mesma seção veio duas vezes: envie um ZIP de cada (Visão geral, "
                       "Seguidores e Espectadores).", details={"recebidos": len(uploads)})
    vazias = sorted(((lt.secao, a) for lt, a, _ in leituras if lt.vazia),
                    key=lambda v: PUBLICO.index(v[0]))
    cheias = [(lt, a, sha) for lt, a, sha in leituras if not lt.vazia]
    if not cheias:
        raise ApiError(400, "studio_sem_dados", SEM_DADOS,
                       details={"secoes": [secao for secao, _ in vazias]})

    problemas: list[Problema] = []
    lidas = {lt.secao: _ler_datas(lt, problemas) for lt, _, _ in cheias
             if lt.secao not in FOTOS}
    pub: dict[str, PublicoLido] = {}
    atividades: list[publico.Atividade] = []
    for lt, a, sha in cheias:
        problemas.extend(lt.problemas)
        if lt.secao in FOTOS:
            itens, ps = publico.ler_distribuicao(lt)
            problemas.extend(ps)
            pub[lt.secao] = PublicoLido(lt, a, sha, itens, [])
        elif lt.secao in (ATIVIDADE, ESPECTADORES):
            if lt.secao == ATIVIDADE:
                atividades, ps = publico.ler_atividade(lt)
                problemas.extend(ps)
            pub[lt.secao] = PublicoLido(lt, a, sha, [], [])
    if problemas:
        raise _invalido(problemas)

    out: dict[str, SecaoLida] = {}
    for secao in (VISAO_GERAL, SEGUIDORES):  # a visão geral primeiro: ela ancora o ano
        achada = next(((lt, a, sha) for lt, a, sha in cheias if lt.secao == secao), None)
        if achada is None:
            continue
        lt, a, sha = achada
        ds = lidas[secao]
        nome = a.nome_zip
        try:
            if ds[0].ano is not None:
                dias, origem = datas.com_ano(ds), "deduzido"
            elif secao == VISAO_GERAL and nome is not None and nome.secao == VISAO_GERAL:
                dias, origem = datas.pelo_nome(ds, nome.inicio, nome.fim), "nome_zip"  # type: ignore[arg-type]
            else:
                dias, origem = None, "deduzido"
                vg = out.get(VISAO_GERAL)
                if vg is not None and vg.ano_origem == "nome_zip":
                    dias = datas.mesmo_mapa(ds, lidas[VISAO_GERAL], vg.dias)
                    origem = "nome_zip" if dias is not None else "deduzido"
                if dias is None:
                    dias = datas.deduzir(ds, hoje)
        except datas.DatasErro as e:
            raise _datas_erro(lt.arquivo, str(e)) from None
        futuros = [Problema(lt.arquivo, linha.numero, formato.NOMES["dia"], linha.dia_bruto,
                            f"data futura ({dia:%d/%m/%Y})", linha.celulas.get("dia"))
                   for linha, dia in zip(lt.linhas, dias, strict=True) if dia > hoje]
        problemas.extend(futuros)
        out[secao] = SecaoLida(lt, a, sha, dias, origem, ds[0].ano is not None)

    # público diário: espectadores e depois atividade, ancorados na 1ª seção já resolvida (R4)
    ancoras = [(lidas[s], out[s].dias, out[s].ano_origem) for s in (VISAO_GERAL, SEGUIDORES)
               if s in out]
    for secao in (ESPECTADORES, ATIVIDADE):
        p = pub.get(secao)
        if p is None:
            continue
        lt = p.leitura
        if secao == ESPECTADORES:
            ds = lidas[secao]
            linhas_dia = [(ln.numero, ln.dia_bruto, ln.celulas.get("dia")) for ln in lt.linhas]
        else:
            por_linha = {ln.numero: ln for ln in lt.linhas}
            todas = [datas.ler_data(x.dia_bruto) for x in atividades]
            ds = datas.dias_distintos(todas)  # type: ignore[arg-type]
            linhas_dia = [(x.linha, x.dia_bruto, por_linha[x.linha].celulas.get("dia"))
                          for x in atividades]
        try:
            dias, origem = _resolver(ds, hoje, ancoras)
        except datas.DatasErro as e:
            raise _datas_erro(lt.arquivo, str(e)) from None
        mapa = dict(zip(ds, dias, strict=True))
        if secao == ESPECTADORES:
            dias_linhas = dias
            p.linhas = [{"dia": d, "total": ln.valores["espectadores"],
                         "novos": ln.valores.get("espectadores_novos"),
                         "recorrentes": ln.valores.get("espectadores_recorrentes")}
                        for ln, d in zip(lt.linhas, dias, strict=True)]
        else:
            dias_linhas = [mapa[t] for t in todas]  # type: ignore[index]
            p.linhas = [{"dia": d, "hora": x.hora, "ativos": x.ativos}
                        for x, d in zip(atividades, dias_linhas, strict=True)]
        p.ano_origem, p.com_ano = origem, ds[0].ano is not None
        problemas.extend(Problema(lt.arquivo, numero, formato.NOMES["dia"], bruto,
                                  f"data futura ({dia:%d/%m/%Y})", celula)
                         for (numero, bruto, celula), dia in zip(linhas_dia, dias_linhas,
                                                                 strict=True) if dia > hoje)
        ancoras.append((ds, dias, origem))
    if problemas:
        raise _invalido(problemas)
    return lidos, out, pub, vazias


# ---- contagens ----

def _numeros(secao: str, valores: dict[str, int | None]) -> tuple:
    return tuple(valores.get(c) for c in CAMPOS[secao])


def _valor_efetivo(secao: str, dia: efetivo.DiaEfetivo | None):
    if dia is None:
        return None
    return dia.visao_geral if secao == VISAO_GERAL else dia.seguidores


def _ja_importada(db: Session, serie_id: uuid.UUID, secao: str, sha: str
                  ) -> schemas.JaImportada | None:
    coluna = getattr(Importacao, SHA[secao])
    achada = db.execute(select(Importacao, User.name)
                        .join(User, User.id == Importacao.criada_por)
                        .where(Importacao.serie_id == serie_id,
                               Importacao.estado == ImportacaoEstado.ativa, coluna == sha)
                        .order_by(Importacao.criada_em, Importacao.id)).first()
    if achada is None:
        return None
    imp, nome = achada
    return schemas.JaImportada(importacao_id=imp.id, em=imp.criada_em, por=nome)


def _aviso(codigo: str, mensagem: str, **detalhes: Any) -> schemas.Aviso:
    return schemas.Aviso(codigo=codigo, mensagem=mensagem, detalhes=detalhes or None)  # type: ignore[arg-type]


def montar(db: Session, actor: Actor, conta: Conta, uploads: list[arquivos.Upload],
           agora: datetime | None = None) -> schemas.PreviaStudio:
    agora = agora or datetime.now(UTC)
    hoje = agora.astimezone(efetivo.tz()).date()
    serie = serie_viva(db, conta)
    lidos, secoes, pub, vazias = ler(conta, uploads, hoje)
    perfil = db.get(Perfil, conta.perfil_id)
    foto = _data_foto(secoes, pub, hoje)

    dias_pub = [ln["dia"] for p in pub.values() for ln in p.linhas]
    validos = [d for s in secoes.values() for d in s.dias if d != hoje] \
        + [d for d in dias_pub if d != hoje] + ([foto[0]] if foto else [])
    todos = [d for s in secoes.values() for d in s.dias] + dias_pub \
        + ([foto[0]] if foto else [])
    de, ate = min(validos or todos), max(validos or todos)
    efetivos = efetivo.dias(db, [serie.id], de, ate).get(serie.id, {})
    primeiro = efetivo.primeiro_dia_coberto(db, [serie.id])[serie.id]
    api = efetivo.api_por_dia(db, [serie.id], de, ate)[serie.id] if primeiro else {}

    secoes_out, avisos, guardar = [], [], {}
    for secao, s in secoes.items():
        cont = {"gravados": 0, "iguais": 0, "divergentes": 0, "coletados": 0}
        ignorados, amostra, linhas = [], [], []
        studio_soma = api_soma = 0
        for linha, dia in zip(s.leitura.linhas, s.dias, strict=True):
            numeros = _numeros(secao, linha.valores)
            if dia == hoje:
                situacao = "ignorado"
                ignorados.append(dia)
            else:
                cont["gravados"] += 1
                linhas.append({"dia": dia.isoformat(),
                               **{c: linha.valores.get(c) for c in CAMPOS[secao]}})
                atual = _valor_efetivo(secao, efetivos.get(dia))
                if efetivo.coberto(dia, primeiro):
                    situacao = "coletado"
                    cont["coletados"] += 1
                    d_api = api.get(dia)
                    if secao == VISAO_GERAL and d_api is not None and d_api.tem_dado:
                        studio_soma += numeros[0]
                        api_soma += d_api.views
                    elif secao == SEGUIDORES and d_api is not None \
                            and d_api.seguidores_fim is not None:
                        studio_soma += numeros[0]
                        api_soma += d_api.seguidores_fim
                elif atual is not None:
                    igual = atual.numeros() == numeros
                    situacao = "igual" if igual else "divergente"
                    cont["iguais" if igual else "divergentes"] += 1
                else:
                    situacao = "novo"
            amostra.append(schemas.LinhaAmostra(dia=dia, situacao=situacao,
                                                **dict(zip(CAMPOS[secao], numeros,
                                                           strict=True))))
        presentes = set(s.dias)
        faltando = [d for d in efetivo.intervalo(s.dias[0], s.dias[-1]) if d not in presentes]
        if len(amostra) > 2 * AMOSTRA_PONTA:
            amostra = amostra[:AMOSTRA_PONTA] + amostra[-AMOSTRA_PONTA:]
        gravaveis = [ln for ln, d in zip(s.leitura.linhas, s.dias, strict=True) if d != hoje]
        if secao == VISAO_GERAL:
            def soma(campo: str, ls=gravaveis) -> int | None:
                vs = [ln.valores.get(campo) for ln in ls]
                return sum(v for v in vs if v is not None) \
                    if any(v is not None for v in vs) else None
            totais: Any = schemas.TotaisVisaoGeral(
                views=soma("views") or 0, visitas_perfil=soma("visitas_perfil"),
                likes=soma("likes"), comments=soma("comments"), shares=soma("shares"))
        else:
            seg = [ln.valores["seguidores"] or 0 for ln in gravaveis] or [0]
            totais = schemas.TotaisSeguidores(seguidores_inicio=seg[0], seguidores_fim=seg[-1],
                                              ganhos=seg[-1] - seg[0])
        ja = _ja_importada(db, serie.id, secao, s.sha)
        contagens = schemas.ContagensPrevia(**cont, faltando=faltando, ignorados=ignorados)
        secoes_out.append(schemas.SecaoPrevia(
            secao=secao, ja_importada=ja, contagens=contagens, totais=totais,
            colunas=schemas.Colunas(reconhecidas=s.leitura.reconhecidas,
                                    ausentes=s.leitura.ausentes,
                                    ignoradas=s.leitura.ignoradas),
            amostra=amostra))
        guardar[secao] = {"sha": s.sha, "anoOrigem": s.ano_origem, "linhas": linhas,
                          "contagens": {**cont, "faltando": len(faltando),
                                        "ignorados": len(ignorados)}}

        rotulo = "Visão geral" if secao == VISAO_GERAL else "Seguidores"
        if api_soma and abs(studio_soma - api_soma) / api_soma > DIVERGENCIA_MAX:
            pct = round(abs(studio_soma - api_soma) / api_soma, 4)
            avisos.append(_aviso(
                "diverge_da_coleta",
                f"{rotulo}: os números não batem com a coleta ({pct:.0%} de diferença nos dias "
                f"em comum); confira se o arquivo é desta conta.",
                secao=secao, diferencaPct=pct, studio=studio_soma, coleta=api_soma))
        if ignorados:
            avisos.append(_aviso("dia_incompleto",
                                 f"{rotulo}: o dia de hoje ({hoje:%d/%m}) está incompleto e "
                                 "não será gravado.", secao=secao))
        if faltando:
            lista = ", ".join(f"{d:%d/%m}" for d in faltando[:10])
            avisos.append(_aviso("dias_faltando",
                                 f"{rotulo}: faltam {len(faltando)} dias no arquivo: {lista}"
                                 + ("…" if len(faltando) > 10 else "") + ".",
                                 secao=secao, dias=len(faltando)))
        if s.ano_origem == "deduzido" and not s.com_ano:
            avisos.append(_aviso("ano_deduzido",
                                 f"{rotulo}: o arquivo não traz o ano, e ele foi deduzido "
                                 f"({s.dias[0]:%d/%m/%Y} a {s.dias[-1]:%d/%m/%Y}); confira o "
                                 "período.", secao=secao))
        if s.leitura.ausentes:
            avisos.append(_aviso("colunas_ausentes",
                                 f"{rotulo}: sem as colunas {', '.join(s.leitura.ausentes)}; "
                                 "esses valores ficam sem dado.", secao=secao,
                                 colunas=s.leitura.ausentes))
        if s.leitura.provisorio:
            avisos.append(_aviso("cabecalho_provisorio",
                                 f"{rotulo}: o cabeçalho em português ainda não foi conferido "
                                 "com um arquivo real; confira os números na amostra.",
                                 secao=secao))
    publico_out, avisos_pub, guardar_pub = _publico(db, serie.id, pub, vazias, foto, hoje)
    avisos.extend(avisos_pub)
    if (ate - de).days + 1 > PERIODO_LONGO_DIAS:
        avisos.append(_aviso("periodo_longo",
                             f"O período tem {(ate - de).days + 1} dias (mais de um ano).",
                             dias=(ate - de).days + 1))

    origens = {s.ano_origem for s in secoes.values()} \
        | {p.ano_origem for s, p in pub.items() if s not in FOTOS}
    if not origens and foto:  # só fotos: o ano do FollowerHistory usado na data
        origens = {foto[2]}
    ano_origem = origens.pop() if len(origens) == 1 else ("misto" if origens else "deduzido")
    exige = any(a.handle is None for a in lidos)
    novas = [x for x in secoes_out if x.ja_importada is None and x.contagens.gravados] + [
        x for x in publico_out if not x.vazia and x.ja_importada is None
        and x.contagens is not None and x.contagens.gravados]
    previa_id = uuid.uuid4()
    estado = {
        "userId": str(actor.user_id), "contaId": str(conta.id), "serieId": str(serie.id),
        "criadaEm": agora.isoformat(), "exigeConfirmacaoConta": exige, "anoOrigem": ano_origem,
        "secoes": guardar, "nomesArquivos": [a.nome for a in lidos],
        "base": base(db, serie.id),
        "publico": guardar_pub, "vazias": [secao for secao, _ in vazias],
    }
    get_redis().set(CHAVE.format(previa_id), json.dumps(estado), ex=int(TTL.total_seconds()))
    return schemas.PreviaStudio(
        previa_id=previa_id, expira_em=agora + TTL,
        conta=schemas.ContaPrevia(id=conta.id, handle=datas.normalizar_handle(conta.handle),
                                  perfil=perfil.name if perfil else ""),
        arquivos=[schemas.ArquivoPrevia(nome=a.nome, tipo=a.tipo,  # type: ignore[arg-type]
                                        secao=secao, handle=a.handle,  # type: ignore[arg-type]
                                        ignorados=a.ignorados)
                  for a in lidos if (secao := _secao_do_arquivo(a, secoes, pub, vazias))],
        periodo=schemas.PeriodoPrevia(de=de, ate=ate, ano_origem=ano_origem),  # type: ignore[arg-type]
        secoes=secoes_out, avisos=avisos, exige_confirmacao_conta=exige,
        pode_confirmar=bool(novas), publico=publico_out)


# ---- público (spec 022) ----

def _secao_do_arquivo(a: arquivos.Arquivo, secoes: dict[str, SecaoLida],
                      pub: dict[str, PublicoLido], vazias: list[tuple[str, arquivos.Arquivo]]
                      ) -> str | None:
    """A seção que o arquivo representa na lista: a da 020 (um ZIP de Seguidores continua
    `seguidores`), senão os espectadores, senão a 1ª de público lida dele."""
    daqui = [s for s, x in secoes.items() if x.arquivo is a]
    daqui += [s for s, x in pub.items() if x.arquivo is a] + [s for s, x in vazias if x is a]
    for s in (VISAO_GERAL, SEGUIDORES, ESPECTADORES, *PUBLICO):
        if s in daqui:
            return s
    return None


def _data_foto(secoes: dict[str, SecaoLida], pub: dict[str, PublicoLido], hoje: date
               ) -> tuple[date, str, str] | None:
    """(data, origem, anoOrigem) das fotos do envio (FR-012, resposta A): o dia seguinte ao
    último do `FollowerHistory.csv` do **mesmo ZIP** de alguma foto, limitado a hoje; senão, o
    dia da importação. None sem foto. As duas fotos do envio usam a mesma data."""
    fotos = [p for s, p in pub.items() if s in FOTOS]
    if not fotos:
        return None
    seg = secoes.get(SEGUIDORES)
    if seg is not None and any(p.arquivo is seg.arquivo and p.arquivo.tipo == "zip"
                               for p in fotos):
        dia, origem = publico.data_foto(seg.dias, hoje)
        return dia, origem, seg.ano_origem
    dia, origem = publico.data_foto(None, hoje)
    return dia, origem, "deduzido"


def _resumo_foto(atual: dict[str, float | None], efetiva: efetivo.Foto | None) -> str:
    if efetiva is None:
        return "novo"
    return "igual" if efetiva.itens == atual else "divergente"


def _publico(db: Session, serie_id: uuid.UUID, pub: dict[str, PublicoLido],
             vazias: list[tuple[str, arquivos.Arquivo]], foto: tuple[date, str, str] | None,
             hoje: date) -> tuple[list[schemas.SecaoPublicoPrevia], list[schemas.Aviso],
                                  dict[str, Any]]:
    out: list[schemas.SecaoPublicoPrevia] = []
    avisos: list[schemas.Aviso] = []
    guardar: dict[str, Any] = {}
    for secao in PUBLICO:
        p = pub.get(secao)
        if p is None:
            if any(s == secao for s, _ in vazias):
                out.append(schemas.SecaoPublicoPrevia(secao=secao, vazia=True, mensagem=VAZIA))  # type: ignore[arg-type]
                avisos.append(_aviso("secao_vazia", f"{ROTULOS[secao]}: {VAZIA}", secao=secao))
            continue
        lt, rotulo = p.leitura, ROTULOS[secao]
        ja = _ja_importada(db, serie_id, secao, p.sha)
        colunas = schemas.Colunas(reconhecidas=lt.reconhecidas, ausentes=lt.ausentes,
                                  ignoradas=lt.ignoradas)
        if secao in FOTOS:
            assert foto is not None
            data, origem, ano = foto
            tipo = efetivo.TIPO_DA_SECAO[secao]
            atual = {i.rotulo: i.pct for i in p.itens}
            efetiva = next((f for f in efetivo.fotos(db, [serie_id], tipo, data).get(serie_id, [])
                            if f.data_foto == data), None)
            situacao = _resumo_foto(atual, efetiva)
            sem = sum(i.pct is None for i in p.itens)
            n = len(p.itens)
            cont = {"gravados": n, "iguais": n if situacao == "igual" else 0,
                    "divergentes": n if situacao == "divergente" else 0, "semDado": sem}
            itens = sorted(p.itens, key=lambda i: (-(i.pct or 0), i.rotulo))
            out.append(schemas.SecaoPublicoPrevia(
                secao=secao, vazia=False, ja_importada=ja, data_foto=data,  # type: ignore[arg-type]
                data_foto_origem=origem, situacao=situacao,  # type: ignore[arg-type]
                itens=[schemas.PublicoItemPrevia(
                    rotulo=i.rotulo, rotulo_exibicao=publico.rotulo_exibicao(secao, i.rotulo),
                    pct=i.pct) for i in itens],
                colunas=colunas,
                contagens=schemas.PublicoContagensPrevia(gravados=n, iguais=cont["iguais"],
                                                         divergentes=cont["divergentes"],
                                                         sem_dado=sem)))
            guardar[secao] = {"sha": p.sha, "dataFoto": data.isoformat(),
                              "dataFotoOrigem": origem, "anoOrigem": ano,
                              "itens": [{"rotulo": i.rotulo, "pct": i.pct} for i in itens],
                              "contagens": cont}
            if origem == "importacao" and not any(a.codigo == "data_foto_importacao"
                                                  for a in avisos):
                avisos.append(_aviso(
                    "data_foto_importacao",
                    f"Data da foto = dia da importação ({data:%d/%m/%Y}); confira se o arquivo "
                    "foi baixado hoje.", dataFoto=data.isoformat()))
        else:
            gravaveis = [ln for ln in p.linhas if ln["dia"] != hoje]
            ignorados = sorted({ln["dia"] for ln in p.linhas if ln["dia"] == hoje})
            dias_ = sorted({ln["dia"] for ln in p.linhas})
            presentes = set(dias_)
            faltando = [d for d in efetivo.intervalo(dias_[0], dias_[-1]) if d not in presentes]
            de_s, ate_s = (min(ln["dia"] for ln in gravaveis), max(ln["dia"] for ln in gravaveis)) \
                if gravaveis else (dias_[0], dias_[-1])
            iguais = divergentes = 0
            sem = lt.sem_dado
            pico = totais = amostra = None
            if secao == ATIVIDADE:
                efetivos = efetivo.atividade(db, [serie_id], de_s, ate_s).get(serie_id, {})
                for ln in gravaveis:
                    e = efetivos.get((ln["dia"], ln["hora"]))
                    if e is not None:
                        if e.ativos == ln["ativos"]:
                            iguais += 1
                        else:
                            divergentes += 1
                com = [ln for ln in gravaveis if ln["ativos"] is not None]
                if com:
                    top = max(com, key=lambda ln: (ln["ativos"], ln["dia"], -ln["hora"]))
                    pico = schemas.PublicoPico(dia=top["dia"], hora=top["hora"],
                                               ativos=top["ativos"])
            else:
                efetivos_e = efetivo.espectadores(db, [serie_id], de_s, ate_s).get(serie_id, {})
                amostra = []
                for ln in p.linhas:
                    e = efetivos_e.get(ln["dia"])
                    numeros = (ln["total"], ln["novos"], ln["recorrentes"])
                    if ln["dia"] == hoje:
                        situacao = "ignorado"
                    elif e is None:
                        situacao = "novo"
                    elif e.numeros() == numeros:
                        situacao, iguais = "igual", iguais + 1
                    else:
                        situacao, divergentes = "divergente", divergentes + 1
                    amostra.append(schemas.PublicoLinhaEspectadores(
                        dia=ln["dia"], total=ln["total"], novos=ln["novos"],
                        recorrentes=ln["recorrentes"], situacao=situacao))  # type: ignore[arg-type]
                if len(amostra) > 2 * AMOSTRA_PONTA:
                    amostra = amostra[:AMOSTRA_PONTA] + amostra[-AMOSTRA_PONTA:]

                def _vals(campo: str, gravaveis=gravaveis) -> list[int]:
                    return [ln[campo] for ln in gravaveis if ln[campo] is not None]

                def _media(vs: list[int]) -> float | None:
                    return round(sum(vs) / len(vs), 1) if vs else None

                novos = _vals("novos")
                totais = schemas.PublicoTotaisEspectadores(
                    novos=sum(novos) if novos else None, media_total=_media(_vals("total")),
                    media_recorrentes=_media(_vals("recorrentes")))
                soma = [ln["dia"] for ln in gravaveis
                        if None not in (ln["total"], ln["novos"], ln["recorrentes"])
                        and ln["total"] != ln["novos"] + ln["recorrentes"]]
                if soma:
                    lista = ", ".join(f"{d:%d/%m}" for d in soma[:10])
                    avisos.append(_aviso(
                        "espectadores_soma",
                        f"Espectadores: em {len(soma)} dia(s) o total não é novos + recorrentes "
                        f"({lista}); os números ficam como vieram.",
                        dias=[d.isoformat() for d in soma]))
            cont = {"gravados": len(gravaveis), "iguais": iguais, "divergentes": divergentes,
                    "ignorados": len(ignorados), "semDado": sem}
            if secao == ESPECTADORES:
                cont["faltando"] = len(faltando)
            out.append(schemas.SecaoPublicoPrevia(
                secao=secao, vazia=False, ja_importada=ja,  # type: ignore[arg-type]
                periodo=schemas.PublicoPeriodoSecao(de=de_s, ate=ate_s,
                                                    ano_origem=p.ano_origem),  # type: ignore[arg-type]
                pico=pico, totais=totais, amostra=amostra, colunas=colunas,
                contagens=schemas.PublicoContagensPrevia(
                    gravados=len(gravaveis), iguais=iguais, divergentes=divergentes,
                    sem_dado=sem, faltando=faltando, ignorados=ignorados)))
            guardar[secao] = {"sha": p.sha, "anoOrigem": p.ano_origem,
                              "linhas": [{**ln, "dia": ln["dia"].isoformat()}
                                         for ln in gravaveis],
                              "contagens": cont}
            if ignorados:
                avisos.append(_aviso("dia_incompleto",
                                     f"{rotulo}: o dia de hoje ({hoje:%d/%m}) está incompleto e "
                                     "não será gravado.", secao=secao))
            if faltando:
                lista = ", ".join(f"{d:%d/%m}" for d in faltando[:10])
                avisos.append(_aviso("dias_faltando",
                                     f"{rotulo}: faltam {len(faltando)} dias no arquivo: {lista}"
                                     + ("…" if len(faltando) > 10 else "") + ".",
                                     secao=secao, dias=len(faltando)))
            if p.ano_origem == "deduzido" and not p.com_ano:
                avisos.append(_aviso("ano_deduzido",
                                     f"{rotulo}: o arquivo não traz o ano, e ele foi deduzido "
                                     f"({dias_[0]:%d/%m/%Y} a {dias_[-1]:%d/%m/%Y}); confira o "
                                     "período.", secao=secao))
            if lt.ausentes:
                avisos.append(_aviso("colunas_ausentes",
                                     f"{rotulo}: sem as colunas {', '.join(lt.ausentes)}; esses "
                                     "valores ficam sem dado.", secao=secao, colunas=lt.ausentes))
        if sem := (guardar[secao]["contagens"]["semDado"]):
            avisos.append(_aviso("sem_dado",
                                 f"{rotulo}: {sem} valor(es) sem dado no arquivo (a TikTok não "
                                 "informou); ficam como \"sem dado\", nunca como zero.",
                                 secao=secao, quantidade=sem))
        if lt.provisorio:
            avisos.append(_aviso("cabecalho_provisorio",
                                 f"{rotulo}: o cabeçalho em português ainda não foi conferido "
                                 "com um arquivo real; confira os números na amostra.",
                                 secao=secao))
    return out, avisos, guardar


# ---- consumo (confirmar) ----

def ler_estado(previa_id: uuid.UUID, actor: Actor, conta: Conta) -> dict[str, Any]:
    """O estado guardado, sem consumir: 410 se não existe ou é de outro dono ou conta (sem
    apagar a prévia dos outros)."""
    bruto = get_redis().get(CHAVE.format(previa_id))
    if not bruto:
        raise ApiError(410, "previa_indisponivel", INDISPONIVEL)
    estado = json.loads(bruto)
    if estado.get("userId") != str(actor.user_id) or estado.get("contaId") != str(conta.id):
        raise ApiError(410, "previa_indisponivel", INDISPONIVEL)
    return estado


def consumir(previa_id: uuid.UUID) -> None:
    """Uso único: só quem apaga a chave segue (o 2º clique recebe 410)."""
    if not get_redis().getdel(CHAVE.format(previa_id)):
        raise ApiError(410, "previa_indisponivel", INDISPONIVEL)
