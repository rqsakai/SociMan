"""Identificador da voz no shop-tts (spec 025, research R11): derivado do `id`, estável, sem
coluna. O serviço aceita só `[a-z0-9_]{2,40}`; o `name` da voz (texto livre e renomeável) nunca é
usado lá, e o prefixo `v_` não colide com as vozes do pipeline (`vendedora_ana`)."""

import uuid


def tts_id(voz_id: uuid.UUID) -> str:
    return "v_" + voz_id.hex[:32]
