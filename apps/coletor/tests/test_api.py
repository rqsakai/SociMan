"""Protocolo com o SociMan falso (`httpx.MockTransport`): cabeçalhos, lotes ≤ 10, imagens antes
dos itens, 401/426 param, 429 espera, 409 `coleta_em_andamento` espera, `parar=true` fecha,
`continuarEm` retoma só depois de 60 min (relógio simulado). Sem Chrome: navegador falso."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import pytest

from sociman_coletor import __version__, api, log, modelos
from sociman_coletor.redes.tiktok_shop import ESQUEMA
from sociman_coletor.rodada import Coletor

from .fakes import (
    HOST_REDE,
    Cenario,
    NavegadorFalso,
    RelogioFalso,
    SocimanFalso,
    cenario_produto,
    rede_teste,
    sha,
)


def _cliente(cfg, token, sociman: SocimanFalso, relogio: RelogioFalso) -> api.ClienteApi:
    return api.ClienteApi(cfg, token, transport=sociman.transport, dormir=relogio.dormir)


def _item(tarefa_id: str, status: str = "ok") -> modelos.Item:
    return modelos.Item(
        tarefa_id=tarefa_id,
        status=status,
        coletado_em=datetime.now(UTC),
        esquema_versao=ESQUEMA,
        campos={"x": 1} if status == "ok" else None,
        erro_codigo=None if status == "ok" else "pagina_sem_campos",
    )


def _coletor(
    cfg, token, sociman: SocimanFalso, relogio: RelogioFalso, roteiro: dict[str, Cenario]
) -> tuple[Coletor, list[NavegadorFalso]]:
    rede = rede_teste()
    navegadores: list[NavegadorFalso] = []

    def fabrica(baixador):
        n = NavegadorFalso(baixador, rede, roteiro)
        navegadores.append(n)
        return n

    col = Coletor(
        cfg,
        token,
        rede,
        transport=sociman.transport,
        relogio=relogio,
        dormir=relogio.dormir,
        fabrica_navegador=fabrica,
        semente=1,
        batimento_s=3600,
    )
    return col, navegadores


# ---- cliente ----


def test_cabecalhos_em_toda_chamada(cfg, token, sociman, relogio):
    c = _cliente(cfg, token, sociman, relogio)
    c.fila(5)
    c.definir_chrome_versao("131.0.1.2")
    c.health()
    for _metodo, _caminho, h in sociman.chamadas:
        assert h["authorization"].startswith("Bearer scol_")
        assert h["x-sociman-coleta-protocolo"] == "1"
        assert h["x-sociman-coletor-versao"] == __version__
        assert h["user-agent"] == f"sociman-coletor/{__version__}"
        assert "origin" not in h and "cookie" not in h
    assert sociman.chamadas[-1][2]["x-sociman-chrome-versao"] == "131.0.1.2"
    assert sociman.filas[0] == {"limite": 5, "simular": False}
    c.fila(1, simular=True)
    assert sociman.filas[-1] == {"limite": 1, "simular": True}


def test_lotes_de_ate_dez_itens(cfg, token, sociman, relogio):
    c = _cliente(cfg, token, sociman, relogio)
    coleta = c.abrir(None, relogio())
    itens = [_item(f"t{i}") for i in range(25)]
    resp = c.enviar_itens(coleta.id, itens)
    assert [len(lote) for lote in sociman.lotes] == [10, 10, 5]
    assert len(resp.resultados) == 25 and all(r.status == "gravado" for r in resp.resultados)
    with pytest.raises(ValueError):
        c.enviar_itens(coleta.id, [])


def test_401_e_426_param_o_servico(cfg, token, sociman, relogio):
    c = _cliente(cfg, token, sociman, relogio)
    sociman.modo_401 = True
    with pytest.raises(api.ParaServico) as exc:
        c.fila(1)
    assert exc.value.codigo == "token_invalido" and exc.value.codigo_saida == 4
    sociman.modo_401 = False
    sociman.modo_426 = True
    with pytest.raises(api.ParaServico) as exc:
        c.fila(1)
    assert exc.value.codigo == "protocolo_coleta" and exc.value.codigo_saida == 5
    assert "Atualize" in exc.value.mensagem


def test_429_espera_retry_after_ou_60s(cfg, token, sociman, relogio):
    c = _cliente(cfg, token, sociman, relogio)
    sociman.n_429 = 2
    sociman.retry_after = "7"
    c.fila(1)
    assert relogio.dormidas == [7.0, 7.0]
    sociman.n_429 = 1
    sociman.retry_after = None
    c.fila(1)
    assert relogio.dormidas[-1] == 60.0


def test_503_desligada_e_409_fechada_idempotente(cfg, token, sociman, relogio):
    c = _cliente(cfg, token, sociman, relogio)
    coleta = c.abrir(None, relogio())
    assert c.fechar_rodada(coleta.id, modelos.Fim(motivo="fila_vazia")) is not None
    assert c.fechar_rodada(coleta.id, modelos.Fim(motivo="fila_vazia")) is None  # já fechada
    sociman.desligada = True
    with pytest.raises(api.ColetaDesligada):
        c.abrir(None, relogio())


def test_timeout_reenvia_o_lote_uma_vez(cfg, token, sociman, relogio):
    import httpx

    vez = {"n": 0}
    original = sociman.handler

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/itens"):
            vez["n"] += 1
            if vez["n"] == 1:
                raise httpx.ReadTimeout("lento")
        return original(req)

    c = api.ClienteApi(cfg, token, transport=httpx.MockTransport(handler), dormir=relogio.dormir)
    coleta = c.abrir(None, relogio())
    resp = c.enviar_itens(coleta.id, [_item("t1")])
    assert vez["n"] == 2 and resp.resultados[0].status == "gravado"


def test_sem_token_o_health_vai_sem_authorization(cfg, relogio):
    """`autoteste --sem-token`: nenhum `Authorization` (um token de mentira tomaria 401 do portão
    global do SociMan, até no `/api/health`); os outros cabeçalhos continuam."""
    import httpx

    visto: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        visto.update(req.headers)
        return httpx.Response(200, json={"status": "ok"})

    c = api.ClienteApi(cfg, None, transport=httpx.MockTransport(handler), dormir=relogio.dormir)
    assert c.health()["status"] == "ok"
    assert "authorization" not in visto
    assert visto["x-sociman-coleta-protocolo"] == str(api.PROTOCOLO)
    c.definir_chrome_versao("154.0")
    c.health()
    assert "authorization" not in visto and visto["x-sociman-chrome-versao"] == "154.0"


# ---- rodada completa com o navegador falso ----


def test_uma_vez_tres_paginas_gravadas_imagens_antes_dos_itens(cfg, token, sociman, relogio):
    roteiro = {}
    for pid in ("7291001", "7291002", "7291003"):
        url = f"{HOST_REDE}/product/{pid}"
        roteiro[url] = cenario_produto(pid)
        sociman.tarefa(
            "produto",
            url + "?src=x",
            f"produto:{pid}",
            "ambas",
            {"baixarImagens": True, "imagensMax": 9},
        )
    sociman.tarefa("produto", f"{HOST_REDE}/product/7291004", "produto:7291004")  # fora do limite
    col, navegadores = _coletor(cfg, token, sociman, relogio, roteiro)
    codigo = col.uma_vez(3)
    assert codigo == 0
    # 3 itens ok, todos gravados
    itens = [i for lote in sociman.lotes for i in lote]
    assert len(itens) == 3 and all(i["status"] == "ok" for i in itens)
    assert all(i["esquemaVersao"] == ESQUEMA and i["fonte"] == "ambas" for i in itens)
    # imagens antes dos itens, com sha conferido, e os shas citados no item
    assert sociman.ordem[:5] == ["abrir", "evento:iniciado", "imagens", "itens", "imagens"]
    manifesto, arquivos = sociman.imagens[0]
    assert [m["sha256"] for m in manifesto] == [sha(a) for a in arquivos]
    assert set(itens[0]["imagens"]) == {m["sha256"] for m in manifesto}
    assert (
        itens[0]["campos"]["ficha"]["imagensSha"]
        and itens[0]["campos"]["ficha"]["variantes"][0]["imagemSha"] in itens[0]["imagens"]
    )
    # bruto podado e comprimido; url canônica igual à da tarefa
    assert itens[0]["bruto"] and itens[0]["campos"]["urlCanonica"] == f"{HOST_REDE}/product/7291001"
    # pausas entre páginas pelo ritmo (relógio simulado): 3 pausas de 5..40 s
    pausas = [d for d in relogio.dormidas if 5 <= d <= 40]
    assert len(pausas) == 3
    # fim com motivo "limite", 3 páginas; Chrome fechado; só 3 URLs abertas, as da fila
    assert sociman.fins[-1]["motivo"] == "limite" and sociman.fins[-1]["paginas"] == 3
    assert sociman.fins[-1]["porTipo"] == {"produto": 3}
    assert navegadores[0].fechado == 1
    assert [a.split("?")[0] for a in navegadores[0].aberturas] == list(roteiro)
    assert sociman.coletas[list(sociman.coletas)[0]].estado == "encerrada"


def test_uma_vez_codigo_2_quando_ha_erro(cfg, token, sociman, relogio):
    url = f"{HOST_REDE}/product/7291001"
    roteiro = {url: Cenario(titulo="Shorts", interceptadas=[("u", {"data": {"nada": 1}})])}
    sociman.tarefa("produto", url, "produto:7291001")
    sociman.tarefa("busca_assunto", f"{HOST_REDE}/busca?q=x", "busca_assunto:x")
    col, _ = _coletor(cfg, token, sociman, relogio, roteiro)
    assert col.uma_vez(5) == 2
    itens = [i for lote in sociman.lotes for i in lote]
    assert [i["status"] for i in itens] == ["erro", "erro"]
    assert itens[0]["erroCodigo"] == "pagina_sem_campos"
    assert itens[1]["erroCodigo"] == "tipo_desconhecido"


def test_409_coleta_em_andamento_espera_5_min(cfg, token, sociman, relogio):
    url = f"{HOST_REDE}/product/7291001"
    sociman.tarefa("produto", url, "produto:7291001")
    sociman.coleta_em_andamento_n = 2
    col, _ = _coletor(cfg, token, sociman, relogio, {url: cenario_produto()})
    assert col.uma_vez(1) == 0
    assert relogio.dormidas[:2] == [300.0, 300.0]
    assert len(sociman.coletas) == 1


def test_parar_true_fecha_a_rodada(cfg, token, sociman, relogio):
    roteiro = {}
    for pid in ("7291001", "7291002", "7291003"):
        url = f"{HOST_REDE}/product/{pid}"
        roteiro[url] = cenario_produto(pid, com_affiliate=False)
        sociman.tarefa("produto", url, f"produto:{pid}")
    sociman.parar_apos_lote = 2
    col, nav = _coletor(cfg, token, sociman, relogio, roteiro)
    col.uma_vez(3)
    assert len(sociman.lotes) == 2 and len(nav[0].aberturas) == 2
    assert sociman.fins[-1]["motivo"] in ("fila_vazia", "orcamento")


def test_captcha_evento_pausa_e_retoma_60_min_depois_do_continuar(cfg, token, sociman, relogio):
    url_c = f"{HOST_REDE}/product/7291001"
    url_ok = f"{HOST_REDE}/product/7291002"
    roteiro = {
        url_c: Cenario(
            titulo="Verificação de segurança", redirecionar_para=f"{HOST_REDE}/verify/abc"
        ),
        url_ok: cenario_produto("7291002", com_affiliate=False),
    }
    sociman.tarefa("produto", url_c, "produto:7291001")
    sociman.tarefa("produto", url_ok, "produto:7291002")
    sociman.continuar_apos_batimentos = 3  # o dono clica "Continuar" no 3º batimento
    col, nav = _coletor(cfg, token, sociman, relogio, roteiro)
    inicio = relogio()
    codigo = col.uma_vez(2)
    assert codigo == 0
    tipos = [e["tipo"] for e in sociman.eventos]
    assert tipos == ["iniciado", "captcha", "retomou"]
    assert sociman.eventos[1]["detalhe"]["urlSemParametros"] == f"{HOST_REDE}/verify/abc"
    assert sociman.eventos[1]["detalhe"]["tipoTarefa"] == "produto"
    itens = [i for lote in sociman.lotes for i in lote]
    assert itens[0]["status"] == "captcha" and itens[1]["status"] == "ok"
    # retomou só depois de continuarEm + 60 min
    continuar = sociman.continuar_em
    assert continuar is not None
    assert relogio() - continuar >= timedelta(minutes=60)
    assert relogio() - inicio < timedelta(hours=2)
    # batimentos durante a pausa a cada 60 s com estado "pausada"
    assert all(b["estado"] == "pausada" for b in sociman.batimentos)
    assert len(sociman.batimentos) >= 60
    # o Chrome ficou aberto durante a pausa e só fechou no fim
    assert nav[0].fechado == 1 and sociman.fins[-1]["motivo"] == "limite"


def test_pausa_vencida_pelo_servidor_fecha_a_rodada(cfg, token, sociman, relogio):
    url_c = f"{HOST_REDE}/product/7291001"
    sociman.tarefa("produto", url_c, "produto:7291001")
    sociman.batimento_parar = {"parar": True, "motivo": "pausa_vencida"}
    col, _ = _coletor(
        cfg, token, sociman, relogio, {url_c: Cenario(titulo="x", iframes=["https://x/captcha/f"])}
    )
    col.uma_vez(1)
    assert sociman.fins[-1]["motivo"] == "pausa_vencida"
    assert [e["tipo"] for e in sociman.eventos] == ["iniciado", "captcha"]


def test_login_perdido_evento_e_item_redirecionada(cfg, token, sociman, relogio):
    url = f"{HOST_REDE}/product/7291001"
    sociman.tarefa("produto", url, "produto:7291001")
    sociman.batimento_parar = {"parar": True, "motivo": "pausa_vencida"}
    col, _ = _coletor(
        cfg,
        token,
        sociman,
        relogio,
        {url: Cenario(titulo="Entrar", redirecionar_para=f"{HOST_REDE}/login?next=x")},
    )
    col.uma_vez(1)
    assert [e["tipo"] for e in sociman.eventos] == ["iniciado", "login_perdido"]
    assert "?" not in sociman.eventos[1]["detalhe"]["urlSemParametros"]
    assert sociman.lotes[0][0]["erroCodigo"] == "redirecionada"


def test_bloqueio_suspeito_tres_429_recuo_24h(cfg, token, sociman, relogio):
    roteiro = {}
    for pid in ("7291001", "7291002", "7291003", "7291004"):
        url = f"{HOST_REDE}/product/{pid}"
        roteiro[url] = Cenario(status=429, titulo="Too many")
        sociman.tarefa("produto", url, f"produto:{pid}")
    col, nav = _coletor(cfg, token, sociman, relogio, roteiro)
    col.uma_vez(4)
    assert [e["tipo"] for e in sociman.eventos] == ["iniciado", "bloqueio_suspeito"]
    assert sociman.eventos[1]["detalhe"]["codigoHttp"] == 429
    assert len(nav[0].aberturas) == 3  # parou na 3ª recusa
    assert col.estado.recuo_ate == relogio() + timedelta(hours=24)
    itens = [i for lote in sociman.lotes for i in lote]
    assert all(i["erroCodigo"] == "http_4xx" for i in itens)


def test_layout_mudou_cinco_vazios(cfg, token, sociman, relogio):
    roteiro = {}
    for i in range(7):
        url = f"{HOST_REDE}/product/729100{i}"
        roteiro[url] = Cenario(titulo="Shorts", interceptadas=[("u", {"data": {}})])
        sociman.tarefa("produto", url, f"produto:729100{i}")
    col, nav = _coletor(cfg, token, sociman, relogio, roteiro)
    col.uma_vez(7)
    assert [e["tipo"] for e in sociman.eventos] == ["iniciado", "layout_mudou"]
    assert len(nav[0].aberturas) == 5
    assert col.estado.recuo_ate is not None


def test_parar_local_termina_a_tarefa_e_fecha_interrompida(
    cfg, token, sociman, relogio, dir_config
):
    roteiro = {}
    for pid in ("7291001", "7291002"):
        url = f"{HOST_REDE}/product/{pid}"
        roteiro[url] = cenario_produto(pid, com_affiliate=False)
        sociman.tarefa("produto", url, f"produto:{pid}")
    col, nav = _coletor(cfg, token, sociman, relogio, roteiro)
    original = nav_abrir = None

    def fabrica_com_parar(baixador):
        n = NavegadorFalso(baixador, col.rede, roteiro)
        goto = n.pagina.goto

        def goto_e_parar(url, **kw):
            r = goto(url, **kw)
            (dir_config / "PARAR").touch()  # o dono pede parada no meio da 1ª página
            return r

        n.pagina.goto = goto_e_parar
        return n

    col._fabrica_navegador = fabrica_com_parar
    assert col.uma_vez(2) == 3
    assert sociman.fins[-1]["motivo"] == "parar_local"
    assert sociman.coletas[list(sociman.coletas)[0]].estado == "interrompida"
    assert [e["tipo"] for e in sociman.eventos] == ["iniciado", "parar_local"]
    assert len(sociman.lotes) == 1  # a 1ª tarefa foi concluída; a 2ª não abriu
    del original, nav_abrir


def test_bruto_pessoal_local_nao_vai_ao_servidor(cfg, token, sociman, relogio, monkeypatch):
    """A poda normal limpa tudo o que conhece; para cobrir a saída `bruto_pessoal_local`
    (algo sobrou depois da poda), a verificação é forçada a acusar um resto."""
    from sociman_coletor import privacidade

    url = f"{HOST_REDE}/product/7291001"
    cen = cenario_produto("7291001", com_affiliate=False, com_pessoal=True)
    sociman.tarefa("produto", url, "produto:7291001")
    col, _ = _coletor(cfg, token, sociman, relogio, {url: cen})
    monkeypatch.setattr(privacidade, "verificar", lambda b: "data.product.seller.nickname")
    col.uma_vez(1)
    item = sociman.lotes[0][0]
    assert item["status"] == "erro" and item["erroCodigo"] == "bruto_pessoal_local"
    assert item["bruto"] is None and item["campos"] is None


def test_imagens_orcamento_esgotado_item_vai_mesmo_assim(cfg, token, sociman, relogio):
    url = f"{HOST_REDE}/product/7291001"
    sociman.tarefa("produto", url, "produto:7291001")
    sociman.imagens_orcamento_esgotado = True
    col, _ = _coletor(cfg, token, sociman, relogio, {url: cenario_produto()})
    assert col.uma_vez(1) == 0
    item = sociman.lotes[0][0]
    assert item["status"] == "ok" and item["imagens"] == []
    assert item["campos"]["ficha"]["imagensSha"] == []


def test_log_da_rodada_sem_dado_pessoal(cfg, token, sociman, relogio, capsys):
    destino = io.StringIO()
    log.configurar("INFO", cfg.log.arquivo, destino=destino)
    url = f"{HOST_REDE}/product/7291001"
    sociman.tarefa("produto", url + "?msToken=segredo&nick=@fulana", "produto:7291001", "ambas")
    col, _ = _coletor(cfg, token, sociman, relogio, {url: cenario_produto()})
    col.uma_vez(1)
    for h in log.obter().handlers:
        h.flush()
    textos = [destino.getvalue(), cfg.log.arquivo.read_text(), capsys.readouterr().out]
    for texto in textos:
        assert "scol_" not in texto
        assert "msToken" not in texto and "@fulana" not in texto
        assert "Tecido ótimo" not in texto and "Cookie" not in texto
        assert "Fulana" not in texto


def test_dry_run_nao_reserva_nem_abre(
    cfg, token, sociman, relogio, dir_config, capsys, monkeypatch
):
    from sociman_coletor import main

    sociman.tarefa("produto", f"{HOST_REDE}/product/7291001?x=1", "produto:7291001")
    original = api.ClienteApi
    monkeypatch.setattr(
        api,
        "ClienteApi",
        lambda c, t, **kw: original(c, t, transport=sociman.transport, dormir=relogio.dormir),
    )
    assert main.main(["--config-dir", str(dir_config), "dry-run", "--limite", "3"]) == 0
    saida = capsys.readouterr().out
    assert "produto" in saida and "/product/7291001" in saida and "?x=1" not in saida
    assert sociman.filas == [{"limite": 3, "simular": True}]
    assert not sociman.coletas


def test_versao(capsys):
    from sociman_coletor import main

    assert main.main(["--versao"]) == 0
    assert "0.1.0" in capsys.readouterr().out
