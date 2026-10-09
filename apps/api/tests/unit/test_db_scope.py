"""Regressão: a sessão do banco precisa commitar ANTES de a resposta sair.

No escopo padrão ("request") o FastAPI fecha a dependência com yield depois de enviar a
resposta; o SPA relia a lista antes do commit (usuário recém-criado sumia da tabela no e2e).
Por isso toda rota usa `DbSession` (scope="function") e ninguém declara `Depends(get_db)` direto.
"""

import typing
from pathlib import Path

from sociman_api import db

SRC = Path(db.__file__).parent


def test_db_session_usa_scope_function():
    [depends] = typing.get_args(db.DbSession)[1:]
    assert depends.dependency is db.get_db
    assert depends.scope == "function"


def test_ninguem_declara_get_db_fora_de_db_py():
    ofensores = [
        str(p.relative_to(SRC)) for p in SRC.rglob("*.py")
        if p.name != "db.py" and "Depends(get_db" in p.read_text()
    ]
    assert ofensores == []


def test_engine_nao_loga_parametros_sql():
    # erros do SQLAlchemy não podem levar valores (ex.: password_hash) para o log (T058)
    assert db.get_engine().hide_parameters is True
