"""Pronúncias e o hash da narração (research R10 e R15): funções puras, sem banco.

`aplicar` espelha o `_pron` do shop-tts (`../comfyui-docker/tts_service/app.py`): cada par do
dicionário, na ordem, troca a palavra inteira (sem diferenciar maiúsculas) pela grafia falada e
preserva a inicial maiúscula; chave que começa com `_` é comentário. O serviço aplica a mesma regra
na entrada do TTS; aqui ela só entra no hash, para dizer se a narração ficou desatualizada.
"""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from uuid import UUID


def aplicar(texto: str, dic: Mapping[str, str]) -> str:
    for escrita, falada in dic.items():
        if escrita.startswith("_") or not falada:
            continue

        def troca(m: re.Match[str], falada: str = falada) -> str:
            return falada[0].upper() + falada[1:] if m.group(0)[0].isupper() else falada

        texto = re.sub(rf"(?<!\w){re.escape(escrita)}(?!\w)", troca, texto, flags=re.IGNORECASE)
    return texto


def hash_atual(frases: Sequence[str], dic: Mapping[str, str], voz_id: UUID | str,
               ref_audio_id: UUID | str | None, velocidade: Decimal | float | str) -> str:
    """sha256 do que muda o áudio: as frases já com as pronúncias, a voz, a referência da voz e a
    velocidade (com 2 casas, igual ao `numeric(3,2)` do banco)."""
    carga = {"frases": [aplicar(f, dic) for f in frases], "voz": str(voz_id),
             "ref": str(ref_audio_id) if ref_audio_id is not None else None,
             "velocidade": f"{Decimal(str(velocidade)):.2f}"}
    bruto = json.dumps(carga, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(bruto.encode()).hexdigest()
