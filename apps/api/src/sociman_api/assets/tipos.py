"""Regras por tipo de asset (research R3, data-model "Validação por tipo").

O `image_kind` é a classe técnica da imagem (validação e onde ela pode entrar no kit e no
corte); o tipo do asset é a classificação do usuário. Cenário é `fundo` e sticker é
`watermark`: o kit, os cortes e os links de mídia aceitam as imagens da biblioteca sem mudar.
"""

from sociman_api.assets.models import AssetTipo, FileRole
from sociman_api.perfis.models import ImageKind

MAX_BYTES = 20 * 1024 * 1024  # rotas da biblioteca (as da 004 continuam com 5 MB)
TOO_LARGE = "Imagem grande demais (máximo 40 megapixels)"

IMAGE_KIND: dict[AssetTipo, ImageKind] = {
    AssetTipo.avatar: ImageKind.avatar,
    AssetTipo.cenario: ImageKind.fundo,
    AssetTipo.fundo: ImageKind.fundo,
    AssetTipo.sticker: ImageKind.watermark,
    AssetTipo.marca_dagua: ImageKind.watermark,
    AssetTipo.imagem: ImageKind.imagem,
}

ROLES: dict[AssetTipo, tuple[FileRole, ...]] = {
    AssetTipo.avatar: (FileRole.referencia, FileRole.pose, FileRole.kit),  # kit: spec 025
    AssetTipo.cenario: (FileRole.referencia, FileRole.kit, FileRole.variacao),
    AssetTipo.fundo: (FileRole.arquivo,),
    AssetTipo.sticker: (FileRole.arquivo,),
    AssetTipo.marca_dagua: (FileRole.arquivo,),
    AssetTipo.imagem: (FileRole.arquivo,),
}

# Tipos de um arquivo só: enviar um segundo dá 400; arquivar o único pede arquivar o asset.
SINGLE_FILE = frozenset({AssetTipo.fundo, AssetTipo.sticker, AssetTipo.marca_dagua,
                         AssetTipo.imagem})

# Tipos que o atalho "um arquivo = um asset" aceita (avatar e cenário têm campos próprios).
SHORTCUT = SINGLE_FILE

# Campos que só valem em alguns tipos (os demais tipos os deixam nulos).
FIELD_TIPOS: dict[str, frozenset[AssetTipo]] = {
    "prompt": frozenset({AssetTipo.avatar, AssetTipo.cenario}),
    "voice_tone": frozenset({AssetTipo.avatar}),
    "image_rules": frozenset({AssetTipo.avatar}),
}

# Campos do arquivo por papel (`look` só em referência de avatar).
FILE_FIELD_ROLES: dict[str, frozenset[FileRole]] = {
    "look": frozenset({FileRole.referencia}),
    "uso": frozenset({FileRole.referencia}),
    "label": frozenset({FileRole.pose, FileRole.variacao}),  # variação: spec 025
    "quando_usar": frozenset({FileRole.pose}),
}

LABELS: dict[AssetTipo, str] = {
    AssetTipo.avatar: "Avatar",
    AssetTipo.cenario: "Cenário",
    AssetTipo.fundo: "Fundo",
    AssetTipo.sticker: "Sticker",
    AssetTipo.marca_dagua: "Marca d'água",
    AssetTipo.imagem: "Imagem",
}


def transparency_message(tipo: AssetTipo) -> str:
    if tipo == AssetTipo.sticker:
        return "O sticker precisa ter fundo transparente"
    return "A imagem precisa ter fundo transparente"
