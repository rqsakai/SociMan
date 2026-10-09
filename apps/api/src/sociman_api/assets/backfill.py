"""As imagens de marca d'água e de fundo da 004 entram na biblioteca (research R2, SC-003).

Para cada `images` com `kind` em (`watermark`, `fundo`) sem `asset_files`, cria um asset de um
arquivo (`marca_dagua` ou `fundo`), com o autor e a data da imagem, o nome "Marca d'água N" ou
"Fundo N" na ordem de envio e a versão 1 (`system:migration`) no histórico. Os ids das imagens
não mudam: o kit e os cortes continuam válidos sem tocar em JSONB.

SQL puro sobre a conexão (a migration chama com `op.get_bind()`, o teste chama direto) e
idempotente: na segunda vez, o filtro "sem `asset_files`" não acha nada.
"""

import json
import uuid
from collections import defaultdict

from sqlalchemy import Connection, text

MIGRATION = "0005_assets"
ACTOR_KIND = "system:migration"
_TIPOS = {"watermark": ("marca_dagua", "Marca d'água"), "fundo": ("fundo", "Fundo")}


def _snapshot(tipo: str, name: str, file_id: uuid.UUID, image_id: uuid.UUID) -> dict:
    """O mesmo formato de `history.snapshot(asset)` (ver `Asset.__versioned_fields__`)."""
    return {
        "tipo": tipo, "name": name, "description": "", "tags": [], "prompt": None,
        "voice_tone": None, "image_rules": None, "primary_file_id": str(file_id),
        "archived": False,
        "files": [{"id": str(file_id), "image_id": str(image_id), "role": "arquivo",
                   "look": None, "uso": None, "label": None, "quando_usar": None, "notes": "",
                   "position": 0, "archived": False}],
    }


def backfill(conn: Connection) -> int:
    """Cria os assets que faltam e devolve quantos criou."""
    rows = conn.execute(text("""
        SELECT i.id, i.perfil_id, i.kind::text AS kind, i.created_at, i.created_by
          FROM images i LEFT JOIN asset_files f ON f.image_id = i.id
         WHERE i.kind IN ('watermark', 'fundo') AND f.id IS NULL
         ORDER BY i.perfil_id, i.kind, i.created_at, i.id
    """)).all()
    if not rows:
        return 0
    # A numeração continua depois dos assets que o perfil já tem daquele tipo.
    counts: dict[tuple, int] = defaultdict(int)
    for perfil_id, tipo, n in conn.execute(text(
            "SELECT perfil_id, tipo::text, count(*) FROM assets GROUP BY perfil_id, tipo")):
        counts[(perfil_id, tipo)] = n

    for image_id, perfil_id, kind, created_at, created_by in rows:
        tipo, prefix = _TIPOS[kind]
        counts[(perfil_id, tipo)] += 1
        name = f"{prefix} {counts[(perfil_id, tipo)]}"
        asset_id, file_id = uuid.uuid4(), uuid.uuid4()
        params = {"asset": asset_id, "file": file_id, "image": image_id, "perfil": perfil_id,
                  "tipo": tipo, "name": name, "at": created_at, "by": created_by}
        conn.execute(text("""
            INSERT INTO assets (id, perfil_id, tipo, name, version, created_at, created_by,
                                updated_at, updated_by)
            VALUES (:asset, :perfil, CAST(:tipo AS asset_tipo), :name, 1, :at, :by, :at, :by)
        """), params)
        conn.execute(text("""
            INSERT INTO asset_files (id, asset_id, image_id, role, position, created_at,
                                     created_by)
            VALUES (:file, :asset, :image, 'arquivo', 0, :at, :by)
        """), params)
        conn.execute(text("UPDATE assets SET primary_file_id = :file WHERE id = :asset"),
                     params)
        after = _snapshot(tipo, name, file_id, image_id)
        conn.execute(text("""
            INSERT INTO entity_versions (entity_type, entity_id, version, action, actor_kind,
                                         after, changed_fields, details)
            VALUES ('asset', :asset, 1, 'created', :actor, CAST(:after AS jsonb), :fields,
                    CAST(:details AS jsonb))
        """), {"asset": asset_id, "actor": ACTOR_KIND, "after": json.dumps(after),
               "fields": list(after),
               "details": json.dumps({"migracao": MIGRATION, "image_id": str(image_id)})})
    return len(rows)
