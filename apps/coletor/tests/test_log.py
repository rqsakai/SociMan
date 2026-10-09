"""Filtro de privacidade do log: token, cookie, sessão, @ e texto longo não passam (FR-021)."""

import io
import logging

from sociman_coletor import log


def _logger_com_destino() -> tuple[logging.Logger, io.StringIO]:
    destino = io.StringIO()
    logger = log.configurar("INFO", None, destino=destino)
    return logger, destino


def test_linhas_limpas_passam():
    logger, destino = _logger_com_destino()
    logger.info("resultado tarefa=%s status=%s codigo=%s", "uuid-1", "gravado", None)
    logger.info("abriu status=%s url=%s", 200, "https://rede.sintetica.test/product/7291001")
    saida = destino.getvalue()
    assert "gravado" in saida and "/product/7291001" in saida


def test_token_cookie_sessao_arroba_e_texto_longo_nao_passam():
    logger, destino = _logger_com_destino()
    logger.info("Authorization: Bearer scol_abc_%s", "x" * 43)
    logger.info("Set-Cookie: sessionid=123")
    logger.info("cookie=%s", "abc")
    logger.info("criador @fulana.achados postou")
    logger.info("texto da avaliacao: %s", "muito bom " * 40)
    logger.info("url com query %s", "https://rede.sintetica.test/product/1?msToken=abc")
    saida = destino.getvalue()
    assert "scol_" not in saida
    assert "sessionid" not in saida and "Cookie" not in saida and "cookie=" not in saida
    assert "@fulana" not in saida
    assert "muito bom" not in saida
    assert "msToken" not in saida and "?" not in saida.split("recusada")[0]
    assert saida.count("linha recusada pelo filtro de privacidade") == 6


def test_motivos():
    assert log.motivo_recusa("scol_x") == "token"
    assert log.motivo_recusa("Cookie: a") == "cookie"
    assert log.motivo_recusa("sessionid=1") == "sessao"
    assert log.motivo_recusa("@a") == "arroba"
    assert log.motivo_recusa("email a@b") == "arroba"
    assert log.motivo_recusa("x" * 201) == "tamanho"
    assert log.motivo_recusa("https://h/p?q=1") == "query"
    assert log.motivo_recusa("tarefa=uuid tipo=produto n=3") is None


def test_arquivo_de_log_tambem_filtra(tmp_path):
    arquivo = tmp_path / "coletor.log"
    logger = log.configurar("INFO", arquivo, destino=io.StringIO())
    logger.info("token scol_%s", "y" * 50)
    logger.info("paginas=%d", 3)
    for h in logger.handlers:
        h.flush()
    texto = arquivo.read_text()
    assert "scol_" not in texto and "paginas=3" in texto


def test_url_sem_query():
    assert log.url_sem_query("https://h/p/1?x=1#f") == "https://h/p/1"
