"""Leitor da TikTok (spec 016, T018, research R2), sempre contra a TikTok falsa (R17): campos
pedidos exatos, id como texto acima de 2^53, lote de 20, `scope_not_authorized` →
`SemPermissaoLeitura`, os 3 resultados do `status/fetch` e nenhum log com legenda ou link."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from sociman_api.publicacao import executor, registro
from sociman_api.publicacao.executor import Contexto
from sociman_api.publicacao.tiktok import leitor as modulo

BASE = 2**53 + 1000  # ids acima do inteiro seguro do JSON
AGORA = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
CAMPOS_VIDEO = ["id", "create_time", "share_url", "video_description", "title", "duration",
                "width", "height", "view_count", "like_count", "comment_count", "share_count"]


@pytest.fixture
def ctx(tiktok_fake):
    """Um token semeado para @um (sem usuário registrado: lê à vontade)."""
    access, _ = tiktok_fake.emitir_tokens("open-um")
    return Contexto(client=tiktok_fake.client(), token=lambda: access)


@pytest.fixture
def leitor():
    leitor = registro.leitor_para("tiktok")
    assert isinstance(leitor, modulo.LeitorTikTok)
    return leitor


def test_leitor_so_pelo_registro_e_so_na_tiktok():
    assert registro.leitor_para("tiktok") is registro.executor_para("tiktok").leitor
    assert registro.leitor_para("youtube") is None
    assert registro.leitor_para("nao-existe") is None


def test_stats_da_conta_com_os_campos_de_stats(tiktok_fake, ctx, leitor):
    tiktok_fake.seguidores("um", 1234, seguindo=5, curtidas=99)
    tiktok_fake.video("um", BASE, AGORA)
    tiktok_fake.video("um", BASE + 1, AGORA, publico=False)
    stats = leitor.stats_conta(ctx)
    assert stats == executor.StatsConta(seguidores=1234, seguindo=5, curtidas=99, videos=1)
    [pedido] = tiktok_fake.pedidos("user_info")
    assert pedido["fields"] == ["open_id", "follower_count", "following_count", "likes_count",
                                "video_count"]


def test_listar_campos_exatos_ids_como_texto_e_cursor(tiktok_fake, ctx, leitor):
    for n in range(25):
        tiktok_fake.video("um", BASE + n, AGORA - timedelta(hours=n), duracao=20 + n,
                          legenda=f"legenda {n}")
    tiktok_fake.video("outro", BASE + 100, AGORA)  # de outra conta: não vem
    tiktok_fake.video("um", BASE + 200, AGORA, publico=False)  # privado: não vem
    videos, cursor, mais = leitor.listar(ctx)
    assert len(videos) == 20 and mais
    assert [v.id for v in videos] == [str(BASE + n) for n in range(20)]
    assert all(isinstance(v.id, str) for v in videos)
    primeiro = videos[0]
    assert primeiro.criado_em == AGORA and primeiro.duracao_s == 20
    assert primeiro.legenda == "legenda 0" and primeiro.views == 0
    assert primeiro.url == f"https://www.tiktok.com/@um/video/{BASE}"
    resto, _, mais = leitor.listar(ctx, cursor)
    assert [v.id for v in resto] == [str(BASE + n) for n in range(20, 25)] and not mais
    pedidos = tiktok_fake.pedidos("video_list")
    assert all(p["fields"] == CAMPOS_VIDEO for p in pedidos)  # sem capa nem embed
    assert [p["cursor"] for p in pedidos] == [None, cursor]
    assert all(p["max_count"] == 20 for p in pedidos)


def test_consultar_lote_de_20_so_da_conta_e_contador_omitido(tiktok_fake, ctx, leitor):
    tiktok_fake.video("um", BASE, AGORA)
    tiktok_fake.video("um", BASE + 1, AGORA)
    tiktok_fake.video("outro", BASE + 2, AGORA)
    tiktok_fake.contadores(BASE, views=500, likes=None)  # a TikTok omite o like
    tiktok_fake.tornar_privado(BASE + 1)
    videos = leitor.consultar(ctx, [str(BASE), str(BASE + 1), str(BASE + 2)])
    assert [(v.id, v.views, v.likes) for v in videos] == [(str(BASE), 500, None)]
    assert tiktok_fake.pedidos("video_query")[0]["ids"] == [str(BASE), str(BASE + 1),
                                                            str(BASE + 2)]
    assert leitor.consultar(ctx, []) == []
    with pytest.raises(ValueError):
        leitor.consultar(ctx, [str(BASE + n) for n in range(21)])
    assert len(tiktok_fake.pedidos("video_query")) == 1  # nada saiu nos dois últimos


def test_sem_escopo_vira_sem_permissao_leitura(tiktok_fake, leitor):
    u = tiktok_fake.usuario("c", "um", escopos="user.info.basic,video.upload")
    access, _ = tiktok_fake.emitir_tokens(u.open_id)
    ctx = Contexto(client=tiktok_fake.client(), token=lambda: access)
    for chamada in (lambda: leitor.listar(ctx), lambda: leitor.consultar(ctx, ["1"]),
                    lambda: leitor.stats_conta(ctx)):
        with pytest.raises(executor.SemPermissaoLeitura) as exc:
            chamada()
        assert exc.value.codigo == "scope_not_authorized"
        assert isinstance(exc.value, executor.RecusaRede)
    # Com os escopos, lê.
    u2 = tiktok_fake.usuario("d", "dois", escopos="user.info.basic,user.info.stats,video.list")
    access2, _ = tiktok_fake.emitir_tokens(u2.open_id)
    ctx2 = Contexto(client=tiktok_fake.client(), token=lambda: access2)
    assert leitor.listar(ctx2) == ([], 0, False)
    assert leitor.stats_conta(ctx2).seguidores == 0


def test_token_invalido_so_na_lista_e_na_consulta(tiktok_fake, leitor):
    ctx = Contexto(client=tiktok_fake.client(), token=lambda: "act.desconhecido")
    with pytest.raises(executor.SemPermissaoLeitura):
        leitor.listar(ctx)
    with pytest.raises(executor.SemPermissaoLeitura):
        leitor.consultar(ctx, ["1"])
    with pytest.raises(executor.RecusaRede) as exc:  # user/info e status: recusa comum
        leitor.stats_conta(ctx)
    assert not isinstance(exc.value, executor.SemPermissaoLeitura)


def test_falhas_de_rede_sobem_tipadas(tiktok_fake, ctx, leitor):
    tiktok_fake.falhar_proximo("video_list", "5xx")
    with pytest.raises(executor.ConexaoIndisponivel):
        leitor.listar(ctx)
    tiktok_fake.falhar_proximo("video_query", "rate_limit_exceeded")
    with pytest.raises(executor.RecusaRede) as exc:
        leitor.consultar(ctx, ["1"])
    assert exc.value.codigo == "rate_limit_exceeded"
    tiktok_fake.falhar_proximo("user_info", "scope_not_authorized")
    with pytest.raises(executor.SemPermissaoLeitura):
        leitor.stats_conta(ctx)


def test_post_publicado_os_tres_resultados(tiktok_fake, ctx, leitor):
    tiktok_fake.rascunho_na_caixa("v_inbox_1")
    assert leitor.post_publicado(ctx, "v_inbox_1") == executor.Pendente("SEND_TO_USER_INBOX")
    tiktok_fake.publicar_rascunho("v_inbox_1", BASE + 7)
    assert leitor.post_publicado(ctx, "v_inbox_1") == executor.PostId(str(BASE + 7))

    # Um envio de verdade do fake que falhou no app.
    c = ctx.client
    init = c.api("POST", "/v2/post/publish/inbox/video/init/", token=ctx.token(), json={
        "source_info": {"source": "FILE_UPLOAD", "video_size": 4, "chunk_size": 4,
                        "total_chunk_count": 1}})["data"]
    c.put_parte(init["upload_url"], b"abcd", 0, 4)
    tiktok_fake.fail_reason_proximo = "file_format_check_failed"
    assert leitor.post_publicado(ctx, init["publish_id"]) == executor.Falhou(
        "file_format_check_failed")
    assert [p["publish_id"] for p in tiktok_fake.pedidos("status")] == [
        "v_inbox_1", "v_inbox_1", init["publish_id"]]


def test_nenhum_log_com_legenda_link_ou_token(tiktok_fake, ctx, leitor, caplog):
    caplog.set_level(logging.DEBUG)
    tiktok_fake.video("um", BASE, AGORA, legenda="Segredo da legenda #tag")
    videos, _, _ = leitor.listar(ctx)
    leitor.consultar(ctx, [videos[0].id])
    leitor.stats_conta(ctx)
    tiktok_fake.falhar_proximo("video_query", "scope_not_authorized")
    with pytest.raises(executor.SemPermissaoLeitura):
        leitor.consultar(ctx, [videos[0].id])
    for proibido in ("Segredo da legenda", videos[0].url, ctx.token(), str(BASE)):
        assert proibido not in caplog.text
    assert "POST /v2/video/list/" in caplog.text  # só método, caminho e status
