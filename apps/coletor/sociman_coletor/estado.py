"""`estado.json`: reserva local do orçamento do dia e das pausas. Só contagens e datas; a verdade
é do servidor. `dataLocal` é corrigida pelo `agoraServidor`/`dataLocal` da fila (relógio errado).
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Estado(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True
    )

    data_local: date | None = None
    paginas_hoje: int = Field(default=0, ge=0)
    imagens_hoje: int = Field(default=0, ge=0)
    ultima_fila_em: datetime | None = None
    recuo_ate: datetime | None = None
    pausa_ate: datetime | None = None
    pid: int | None = None

    # Preenchido por `carregar`; fora do JSON.
    _caminho: Path | None = None

    @classmethod
    def carregar(cls, caminho: Path) -> Estado:
        est = cls()
        if caminho.exists():
            try:
                est = cls.model_validate_json(caminho.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                est = cls()  # arquivo corrompido: recomeça do zero (é só reserva local)
        est._caminho = caminho
        return est

    def salvar(self) -> None:
        if self._caminho is None:
            return
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._caminho.with_suffix(".tmp")
        tmp.write_text(self.model_dump_json(indent=1), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self._caminho)

    def virar_dia(self, data_servidor: date) -> None:
        """Novo dia local (pelo servidor): zera as contagens."""
        if self.data_local != data_servidor:
            self.data_local = data_servidor
            self.paginas_hoje = 0
            self.imagens_hoje = 0

    def contar_pagina(self) -> None:
        self.paginas_hoje += 1

    def contar_imagens(self, n: int) -> None:
        self.imagens_hoje += max(0, n)

    def em_recuo(self, agora: datetime) -> bool:
        return self.recuo_ate is not None and agora < self.recuo_ate

    def registrar_pid(self) -> None:
        self.pid = os.getpid()
