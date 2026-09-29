from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from sociman_api import history as _history  # noqa: F401 — registra no metadata
from sociman_api.assets import models as _assets_models  # noqa: F401
from sociman_api.auth import models as _auth_models  # noqa: F401
from sociman_api.canais import models as _canais_models  # noqa: F401
from sociman_api.config import get_settings
from sociman_api.cortes import models as _cortes_models  # noqa: F401
from sociman_api.db import Base
from sociman_api.envios import models as _envios_models  # noqa: F401
from sociman_api.ia import models as _ia_models  # noqa: F401
from sociman_api.marca import models as _marca_models  # noqa: F401
from sociman_api.notificacoes import models as _notificacoes_models  # noqa: F401
from sociman_api.perfis import models as _perfis_models  # noqa: F401
from sociman_api.postagem import models as _postagem_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
