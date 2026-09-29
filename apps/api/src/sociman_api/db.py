"""Engine e sessão do SQLAlchemy."""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from sociman_api.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    # hide_parameters: erros do SQLAlchemy não levam valores (ex.: password_hash) para o log
    return create_engine(get_settings().database_url, pool_pre_ping=True, hide_parameters=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependência FastAPI: uma sessão por requisição, commit no sucesso e rollback no erro."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# scope="function": o commit/rollback acontece ANTES de a resposta sair. No escopo padrão
# ("request") o FastAPI só fecha a dependência depois de enviar a resposta, e o SPA relia a
# lista antes do commit (bug visto no e2e: usuário criado não aparecia na tabela).
DbSession = Annotated[Session, Depends(get_db, scope="function")]
