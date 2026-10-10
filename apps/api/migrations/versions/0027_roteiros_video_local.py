"""roteiros com vídeo local: roteiro, posições, narrações, entregas, padrões e pronúncias (spec 011)

Na ordem do data-model §Migration:
1. fora da transação (`autocommit_block`, antes dos CHECKs que citam os valores novos):
   `tomada_origem` + `geracao_local`, `image_kind` + `keyframe`, `geracao_alvo` + `cena`/`roteiro`
   e `geracao_motor` + `ffmpeg`;
2. os tipos `roteiro_formato`, `roteiro_modo`, `roteiro_status`, `roteiro_etapa` e `cena_motor`;
3. as 7 tabelas (`roteiros` sem a FK `narracao_id`, que fecha o ciclo com `roteiro_narracoes` no
   fim), o trigger `roteiro_entregas_so_insercao` e o índice único das pronúncias;
4. as colunas novas em `cenas` (8), `cena_tomadas` (6, com `video_key`/`miniatura_key`/`bytes`
   anuláveis e 3 CHECKs), `geracoes` (`desuso_em` e o índice), `geracao_candidatos` (7, vídeo) e
   `conteudos` (`gerado_ia`);
5. o `ck_geracoes_passo` com os 21 passos, o `ck_candidatos_midia` com o vídeo e a função do
   trigger `geracao_candidatos_midia` (vídeo nos passos de resultado vídeo, nada no plano).

Downgrade (só dev): recusa se houver roteiro, pronúncia, tomada local ou limpa, cena com keyframe,
geração dos 6 passos novos, candidato com vídeo, imagem `keyframe` ou conteúdo `gerado_ia`; senão
remove tudo na ordem inversa e volta os CHECKs e o trigger da 021. Os valores novos dos 4 enums
**ficam** (como a 0015, a 0022 e a 0023: recriar `geracao_motor` esbarra no índice parcial
`uq_geracoes_gpu_rodando`, que compara o motor com literais, e um valor sem uso é inofensivo).
Nenhum objeto do MinIO é tocado.

Revision ID: 0027_roteiros_video_local
Revises: 0026_uniao_mercado
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_roteiros_video_local"
down_revision: str | None = "0026_uniao_mercado"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Os 15 da 021 e os 6 da 011, na ordem de `geracao/passos.py` (o teste cruzado confere).
PASSOS = (
    "avatar.rosto_origem", "avatar.rosto_frontal", "avatar.rostos_34", "avatar.corpo_base",
    "avatar.look", "avatar.pose", "avatar.identidade",
    "voz.gravacao", "voz.design", "voz.teste",
    "produto.ficha", "produto.recorte", "produto.flat",
    "cenario.cena", "cenario.variacao",
    "roteiro.plano", "roteiro.narracao", "cena.keyframe", "cena.clipe", "roteiro.montagem",
    "roteiro.acabamento",
)
PASSOS_021 = PASSOS[:15]
PASSOS_011 = PASSOS[15:]
SEM_MIDIA = ("produto.ficha", "avatar.identidade", "roteiro.plano")
SEM_MIDIA_021 = ("produto.ficha", "avatar.identidade")
VIDEO = ("cena.clipe", "roteiro.montagem", "roteiro.acabamento")
AVISOS_POSICAO = ("tomada_curta", "cena_arquivada", "keyframe_pendente", "consentimento_revogado")
PORTOES_PADRAO = '{"texto": true, "narracao": true, "keyframes": true, "clipes": true, "final": true}'


def _enum(name: str, *valores: str) -> postgresql.ENUM:
    return postgresql.ENUM(*valores, name=name, create_type=False)


roteiro_formato = _enum("roteiro_formato", "voice_over")
roteiro_modo = _enum("roteiro_modo", "revisar", "automatico")
roteiro_status = _enum("roteiro_status", "rascunho", "planejando", "aguardando_texto", "narrando",
                       "aguardando_narracao", "gerando_keyframes", "aguardando_keyframes",
                       "gerando_clipes", "aguardando_clipes", "montando", "aguardando_final",
                       "finalizando", "pronto", "falhou")
roteiro_etapa = _enum("roteiro_etapa", "plano", "narracao", "keyframes", "clipes", "montagem",
                      "acabamento")
cena_motor = _enum("cena_motor", "minimax", "wan", "wan_qualidade", "ltx")
TIPOS = (roteiro_formato, roteiro_modo, roteiro_status, roteiro_etapa, cena_motor)
ENUMS_NOVOS = (("tomada_origem", "geracao_local"), ("image_kind", "keyframe"),
               ("geracao_alvo", "cena"), ("geracao_alvo", "roteiro"), ("geracao_motor", "ffmpeg"))

TABELAS = ("roteiro_entregas", "roteiro_narracoes", "roteiro_cenas", "roteiro_produtos",
           "roteiro_padroes", "pronuncias", "roteiros")


def _lista(valores: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


# A da 021 (0020), para o downgrade.
TRIGGER_FN_021 = f"""
CREATE OR REPLACE FUNCTION geracao_candidatos_midia() RETURNS trigger AS $$
DECLARE
    v_passo text;
BEGIN
    SELECT passo INTO v_passo FROM geracoes WHERE id = NEW.geracao_id;
    IF v_passo IN ({_lista(SEM_MIDIA_021)}) THEN
        IF NEW.image_id IS NOT NULL OR NEW.image_par_id IS NOT NULL
                OR NEW.audio_id IS NOT NULL THEN
            RAISE EXCEPTION 'geracao_candidatos: passo % não tem mídia', v_passo
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF v_passo = 'avatar.rostos_34' THEN
        IF NEW.image_id IS NULL OR NEW.image_par_id IS NULL OR NEW.audio_id IS NOT NULL THEN
            RAISE EXCEPTION 'geracao_candidatos: o avatar.rostos_34 exige o par de imagens'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        IF num_nonnulls(NEW.image_id, NEW.audio_id) <> 1 OR NEW.image_par_id IS NOT NULL THEN
            RAISE EXCEPTION 'geracao_candidatos: o passo % exige uma imagem ou um áudio', v_passo
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# Só INSERT (como na 0020): a revogação LGPD da 025 e a limpeza (R12) zeram a mídia depois.
TRIGGER_FN = f"""
CREATE OR REPLACE FUNCTION geracao_candidatos_midia() RETURNS trigger AS $$
DECLARE
    v_passo text;
BEGIN
    SELECT passo INTO v_passo FROM geracoes WHERE id = NEW.geracao_id;
    IF v_passo IN ({_lista(SEM_MIDIA)}) THEN
        IF num_nonnulls(NEW.image_id, NEW.image_par_id, NEW.audio_id, NEW.video_key) > 0 THEN
            RAISE EXCEPTION 'geracao_candidatos: passo % não tem mídia', v_passo
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF v_passo = 'avatar.rostos_34' THEN
        IF NEW.image_id IS NULL OR NEW.image_par_id IS NULL OR NEW.audio_id IS NOT NULL
                OR NEW.video_key IS NOT NULL THEN
            RAISE EXCEPTION 'geracao_candidatos: o avatar.rostos_34 exige o par de imagens'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF v_passo IN ({_lista(VIDEO)}) THEN
        IF NEW.video_key IS NULL OR num_nonnulls(NEW.image_id, NEW.image_par_id,
                                                 NEW.audio_id) > 0 THEN
            RAISE EXCEPTION 'geracao_candidatos: o passo % exige um vídeo', v_passo
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF v_passo = 'roteiro.narracao' THEN
        IF NEW.audio_id IS NULL OR num_nonnulls(NEW.image_id, NEW.image_par_id,
                                                NEW.video_key) > 0 THEN
            RAISE EXCEPTION 'geracao_candidatos: o roteiro.narracao exige um áudio'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF v_passo = 'cena.keyframe' THEN
        IF NEW.image_id IS NULL OR num_nonnulls(NEW.image_par_id, NEW.audio_id,
                                                NEW.video_key) > 0 THEN
            RAISE EXCEPTION 'geracao_candidatos: o cena.keyframe exige uma imagem'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        IF num_nonnulls(NEW.image_id, NEW.audio_id) <> 1 OR NEW.image_par_id IS NOT NULL
                OR NEW.video_key IS NOT NULL THEN
            RAISE EXCEPTION 'geracao_candidatos: o passo % exige uma imagem ou um áudio', v_passo
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

SO_INSERCAO_FN = """
CREATE FUNCTION roteiro_entregas_so_insercao() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'roteiro_entregas: só inserção (% recusado)', TG_OP
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;
"""


def _audit(ts) -> list[sa.Column]:
    return [
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
    ]


def _versionada(ts) -> list[sa.Column]:
    return [
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", ts),
        sa.Column("archived_by", sa.Uuid(), sa.ForeignKey("users.id")),
    ]


def _tabelas(ts) -> None:
    op.create_table(
        "roteiros",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("brief", sa.Text(), server_default="", nullable=False),
        sa.Column("avatar_id", sa.Uuid(), sa.ForeignKey("assets.id")),
        sa.Column("voz_id", sa.Uuid(), sa.ForeignKey("vozes.id")),
        sa.Column("formato", roteiro_formato, server_default="voice_over", nullable=False),
        sa.Column("frases", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"),
                  nullable=False),
        sa.Column("velocidade", sa.Numeric(3, 2), server_default=sa.text("1.08"),
                  nullable=False),
        sa.Column("modo", roteiro_modo, server_default="revisar", nullable=False),
        sa.Column("portoes", postgresql.JSONB(), server_default=sa.text(f"'{PORTOES_PADRAO}'"),
                  nullable=False),
        sa.Column("status", roteiro_status, server_default="rascunho", nullable=False),
        sa.Column("etapa_falhou", roteiro_etapa),
        sa.Column("erro_code", sa.Text()),
        sa.Column("erro_message", sa.Text()),
        sa.Column("avisos", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"),
                  nullable=False),
        sa.Column("comandado_por", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("narracao_id", sa.Uuid()),  # FK no fim (ciclo com roteiro_narracoes)
        sa.Column("montagem_geracao_id", sa.Uuid(), sa.ForeignKey("geracoes.id")),
        sa.Column("acabamento_geracao_id", sa.Uuid(), sa.ForeignKey("geracoes.id")),
        sa.Column("conteudo_id", sa.Uuid(), sa.ForeignKey("conteudos.id")),
        *_versionada(ts), *_audit(ts),
        sa.CheckConstraint("char_length(nome) BETWEEN 1 AND 120 AND nome = btrim(nome)",
                           name="ck_roteiros_nome"),
        sa.CheckConstraint("char_length(brief) <= 4000", name="ck_roteiros_brief"),
        sa.CheckConstraint("cardinality(frases) <= 60", name="ck_roteiros_frases"),
        sa.CheckConstraint("velocidade BETWEEN 0.90 AND 1.20", name="ck_roteiros_velocidade"),
        sa.CheckConstraint("(status = 'falhou') = (etapa_falhou IS NOT NULL)",
                           name="ck_roteiros_falhou"),
        sa.CheckConstraint("status = 'falhou' OR (erro_code IS NULL AND erro_message IS NULL)",
                           name="ck_roteiros_erro"),
        sa.CheckConstraint("status <> 'pronto' OR conteudo_id IS NOT NULL",
                           name="ck_roteiros_pronto"),
        sa.CheckConstraint("jsonb_typeof(portoes) = 'object' AND jsonb_typeof(avisos) = 'array'",
                           name="ck_roteiros_json"),
    )
    op.create_index("ix_roteiros_perfil_lista", "roteiros",
                    ["perfil_id", "archived_at", sa.text("updated_at DESC"), "id"])
    op.create_index("ix_roteiros_perfil_status", "roteiros", ["perfil_id", "status"],
                    postgresql_where=sa.text("archived_at IS NULL"))

    op.create_table(
        "roteiro_produtos",
        sa.Column("roteiro_id", sa.Uuid(), sa.ForeignKey("roteiros.id"), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False),
        sa.Column("produto_id", sa.Uuid(), sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("produto_variante_id", sa.Uuid(), sa.ForeignKey("produto_variantes.id")),
        sa.PrimaryKeyConstraint("roteiro_id", "ordem"),
        sa.CheckConstraint("ordem BETWEEN 0 AND 5", name="ck_roteiro_produtos_ordem"),
    )
    op.create_index("uq_roteiro_produtos", "roteiro_produtos",
                    ["roteiro_id", "produto_id", "produto_variante_id"], unique=True,
                    postgresql_nulls_not_distinct=True)
    op.create_index("ix_roteiro_produtos_produto", "roteiro_produtos", ["produto_id"])

    op.create_table(
        "roteiro_cenas",
        sa.Column("roteiro_id", sa.Uuid(), sa.ForeignKey("roteiros.id"), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False),
        sa.Column("cena_id", sa.Uuid(), sa.ForeignKey("cenas.id"), nullable=False),
        sa.Column("frases", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("inicio_s", sa.Numeric(7, 3)),
        sa.Column("duracao_s", sa.Numeric(7, 3)),
        sa.Column("tomada_id", sa.Uuid(), sa.ForeignKey("cena_tomadas.id")),
        sa.Column("aviso", sa.Text()),
        sa.PrimaryKeyConstraint("roteiro_id", "ordem"),
        sa.CheckConstraint("ordem >= 0", name="ck_roteiro_cenas_ordem"),
        sa.CheckConstraint("cardinality(frases) >= 1", name="ck_roteiro_cenas_frases"),
        sa.CheckConstraint("(inicio_s IS NULL) = (duracao_s IS NULL) AND "
                           "(inicio_s IS NULL OR (inicio_s >= 0 AND duracao_s > 0))",
                           name="ck_roteiro_cenas_tempos"),
        sa.CheckConstraint(f"aviso IS NULL OR aviso IN ({_lista(AVISOS_POSICAO)})",
                           name="ck_roteiro_cenas_aviso"),
    )
    op.create_index("ix_roteiro_cenas_cena", "roteiro_cenas", ["cena_id"])
    op.create_index("ix_roteiro_cenas_tomada", "roteiro_cenas", ["tomada_id"],
                    postgresql_where=sa.text("tomada_id IS NOT NULL"))

    op.create_table(
        "roteiro_narracoes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("roteiro_id", sa.Uuid(), sa.ForeignKey("roteiros.id"), nullable=False),
        sa.Column("geracao_id", sa.Uuid(), sa.ForeignKey("geracoes.id"), nullable=False),
        sa.Column("audio_id", sa.Uuid(), sa.ForeignKey("audios.id")),
        sa.Column("voz_id", sa.Uuid(), sa.ForeignKey("vozes.id"), nullable=False),
        sa.Column("texto_hash", sa.Text(), nullable=False),
        sa.Column("frases", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("tempos", postgresql.JSONB(), nullable=False),
        sa.Column("total_s", sa.Numeric(7, 3), nullable=False),
        sa.Column("similaridade", sa.Numeric(4, 3), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("velocidade", sa.Numeric(3, 2), nullable=False),
        sa.Column("desuso_em", ts),
        sa.Column("limpa_em", ts),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.CheckConstraint("audio_id IS NOT NULL OR limpa_em IS NOT NULL",
                           name="ck_narracoes_limpa"),
        sa.CheckConstraint("texto_hash ~ '^[0-9a-f]{64}$'", name="ck_narracoes_hash"),
        sa.CheckConstraint("total_s > 0 AND velocidade BETWEEN 0.90 AND 1.20",
                           name="ck_narracoes_numeros"),
        sa.CheckConstraint("jsonb_typeof(tempos) = 'array'", name="ck_narracoes_tempos"),
    )
    op.create_index("ix_roteiro_narracoes_roteiro", "roteiro_narracoes",
                    ["roteiro_id", sa.text("created_at DESC")])
    op.create_index("ix_roteiro_narracoes_desuso", "roteiro_narracoes", ["desuso_em"],
                    postgresql_where=sa.text("desuso_em IS NOT NULL AND limpa_em IS NULL"))
    op.create_index("ix_roteiro_narracoes_audio", "roteiro_narracoes", ["audio_id"],
                    postgresql_where=sa.text("audio_id IS NOT NULL"))

    op.create_table(
        "roteiro_entregas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("roteiro_id", sa.Uuid(), sa.ForeignKey("roteiros.id"), nullable=False),
        sa.Column("conteudo_id", sa.Uuid(), sa.ForeignKey("conteudos.id"), nullable=False,
                  unique=True),
        sa.Column("narracao_id", sa.Uuid(), sa.ForeignKey("roteiro_narracoes.id"),
                  nullable=False),
        sa.Column("montagem_geracao_id", sa.Uuid(), sa.ForeignKey("geracoes.id"),
                  nullable=False),
        sa.Column("acabamento_geracao_id", sa.Uuid(), sa.ForeignKey("geracoes.id"),
                  nullable=False),
        sa.Column("posicoes", postgresql.JSONB(), nullable=False),
        sa.Column("motores", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.CheckConstraint("jsonb_typeof(posicoes) = 'array'", name="ck_roteiro_entregas_posicoes"),
    )
    op.create_index("ix_roteiro_entregas_roteiro", "roteiro_entregas",
                    ["roteiro_id", sa.text("created_at DESC")])
    op.execute(SO_INSERCAO_FN)
    op.execute("CREATE TRIGGER roteiro_entregas_so_insercao BEFORE UPDATE OR DELETE ON "
               "roteiro_entregas FOR EACH ROW EXECUTE FUNCTION roteiro_entregas_so_insercao()")

    op.create_table(
        "roteiro_padroes",
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), primary_key=True),
        sa.Column("modo", roteiro_modo, nullable=False),
        sa.Column("portoes", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_audit(ts),
        sa.CheckConstraint("jsonb_typeof(portoes) = 'object'", name="ck_roteiro_padroes_portoes"),
    )

    op.create_table(
        "pronuncias",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("perfil_id", sa.Uuid(), sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("escrita", sa.Text(), nullable=False),
        sa.Column("falada", sa.Text(), nullable=False),
        *_versionada(ts), *_audit(ts),
        sa.CheckConstraint("char_length(escrita) BETWEEN 1 AND 60 AND escrita = btrim(escrita) "
                           "AND escrita !~ '[\\r\\n]'", name="ck_pronuncias_escrita"),
        sa.CheckConstraint("char_length(falada) BETWEEN 1 AND 60 AND falada = btrim(falada) "
                           "AND falada !~ '[\\r\\n]'", name="ck_pronuncias_falada"),
    )
    op.create_index("uq_pronuncias_escrita", "pronuncias", ["perfil_id", sa.text("lower(escrita)")],
                    unique=True, postgresql_where=sa.text("archived_at IS NULL"))
    op.create_index("ix_pronuncias_perfil", "pronuncias", ["perfil_id", "archived_at", "escrita"])

    op.create_foreign_key("fk_roteiros_narracao", "roteiros", "roteiro_narracoes",
                          ["narracao_id"], ["id"])


def _cenas_e_tomadas(ts) -> None:
    op.add_column("cenas", sa.Column("motor", cena_motor, server_default="minimax",
                                     nullable=False))
    op.add_column("cenas", sa.Column("largura", sa.SmallInteger(), server_default=sa.text("736"),
                                     nullable=False))
    op.add_column("cenas", sa.Column("altura", sa.SmallInteger(), server_default=sa.text("1280"),
                                     nullable=False))
    op.add_column("cenas", sa.Column("keyframe_inicial_id", sa.Uuid(), sa.ForeignKey(
        "images.id", name="fk_cenas_keyframe_inicial")))
    op.add_column("cenas", sa.Column("keyframe_final_id", sa.Uuid(), sa.ForeignKey(
        "images.id", name="fk_cenas_keyframe_final")))
    op.add_column("cenas", sa.Column("keyframe_instrucao", sa.Text()))
    # Sem FK (data-model): uma imagem apagada pela revogação vira "referência removida".
    op.add_column("cenas", sa.Column("keyframe_refs", postgresql.ARRAY(sa.Uuid()),
                                     server_default=sa.text("'{}'"), nullable=False))
    op.add_column("cenas", sa.Column("keyframe_geracao_id", sa.Uuid(), sa.ForeignKey(
        "geracoes.id", name="fk_cenas_keyframe_geracao")))
    op.add_column("cenas", sa.Column("duracao_max_s", sa.Numeric(4, 1)))
    op.create_check_constraint("ck_cenas_resolucao", "cenas",
                               "largura BETWEEN 256 AND 1920 AND altura BETWEEN 256 AND 1920 "
                               "AND largura % 16 = 0 AND altura % 16 = 0")
    op.create_check_constraint("ck_cenas_keyframe_instrucao", "cenas",
                               "keyframe_instrucao IS NULL OR char_length(keyframe_instrucao) "
                               "<= 2000")
    op.create_check_constraint("ck_cenas_keyframe_refs", "cenas",
                               "cardinality(keyframe_refs) <= 6")
    op.create_check_constraint("ck_cenas_keyframe", "cenas",
                               "(keyframe_final_id IS NULL AND keyframe_geracao_id IS NULL) "
                               "OR keyframe_inicial_id IS NOT NULL")
    op.create_check_constraint("ck_cenas_duracao_max", "cenas",
                               "duracao_max_s IS NULL OR duracao_max_s BETWEEN 1 AND 30")
    op.create_index("ix_cenas_keyframe_inicial", "cenas", ["keyframe_inicial_id"],
                    postgresql_where=sa.text("keyframe_inicial_id IS NOT NULL"))

    op.add_column("cena_tomadas", sa.Column("geracao_id", sa.Uuid(), sa.ForeignKey(
        "geracoes.id", name="fk_cena_tomadas_geracao")))
    op.add_column("cena_tomadas", sa.Column("keyframe_image_id", sa.Uuid(), sa.ForeignKey(
        "images.id", name="fk_cena_tomadas_keyframe")))
    op.add_column("cena_tomadas", sa.Column("motor", cena_motor))
    op.add_column("cena_tomadas", sa.Column("fps", sa.SmallInteger()))
    op.add_column("cena_tomadas", sa.Column("desuso_em", ts))
    op.add_column("cena_tomadas", sa.Column("limpa_em", ts))
    for col in ("video_key", "miniatura_key", "bytes"):
        op.alter_column("cena_tomadas", col, nullable=True)
    op.create_check_constraint(
        "ck_tomadas_origem_local", "cena_tomadas",
        "(origem = 'geracao_local') = (geracao_id IS NOT NULL AND keyframe_image_id IS NOT NULL "
        "AND motor IS NOT NULL)")
    op.create_check_constraint(
        "ck_tomadas_limpa", "cena_tomadas",
        "(video_key IS NOT NULL AND miniatura_key IS NOT NULL AND bytes IS NOT NULL) "
        "OR limpa_em IS NOT NULL")
    op.create_check_constraint("ck_tomadas_limpa_local", "cena_tomadas",
                               "limpa_em IS NULL OR origem = 'geracao_local'")
    op.create_check_constraint("ck_tomadas_fps", "cena_tomadas", "fps IS NULL OR fps IN (16, 24)")
    op.create_index("ix_cena_tomadas_desuso", "cena_tomadas", ["desuso_em"],
                    postgresql_where=sa.text("desuso_em IS NOT NULL AND limpa_em IS NULL"))
    op.create_index("ix_cena_tomadas_geracao", "cena_tomadas", ["geracao_id"],
                    postgresql_where=sa.text("geracao_id IS NOT NULL"))


def _geracoes(ts) -> None:
    op.add_column("geracoes", sa.Column("desuso_em", ts))
    op.create_index("ix_geracoes_desuso", "geracoes", ["desuso_em"],
                    postgresql_where=sa.text("desuso_em IS NOT NULL AND limpa_em IS NULL"))
    op.drop_constraint("ck_geracoes_passo", "geracoes", type_="check")
    op.create_check_constraint("ck_geracoes_passo", "geracoes", f"passo IN ({_lista(PASSOS)})")

    op.add_column("geracao_candidatos", sa.Column("video_key", sa.Text()))
    op.add_column("geracao_candidatos", sa.Column("video_miniatura_key", sa.Text()))
    for col in ("video_duracao_ms", "video_largura", "video_altura", "video_fps"):
        op.add_column("geracao_candidatos", sa.Column(col, sa.Integer()))
    op.add_column("geracao_candidatos", sa.Column("video_bytes", sa.BigInteger()))
    op.create_unique_constraint("uq_candidatos_video_key", "geracao_candidatos", ["video_key"])
    op.drop_constraint("ck_candidatos_midia", "geracao_candidatos", type_="check")
    op.create_check_constraint("ck_candidatos_midia", "geracao_candidatos",
                               "num_nonnulls(image_id, audio_id, video_key) <= 1")
    op.create_check_constraint("ck_candidatos_video", "geracao_candidatos",
                               "(video_key IS NULL) = (video_miniatura_key IS NULL)")
    op.execute(TRIGGER_FN)

    op.add_column("conteudos", sa.Column("gerado_ia", sa.Boolean(), server_default=sa.false(),
                                         nullable=False))


def upgrade() -> None:
    # 1.
    with op.get_context().autocommit_block():
        for tipo, valor in ENUMS_NOVOS:
            op.execute(f"ALTER TYPE {tipo} ADD VALUE IF NOT EXISTS '{valor}'")
    # 2.
    bind = op.get_bind()
    for tipo in TIPOS:
        tipo.create(bind, checkfirst=True)
    ts = sa.DateTime(timezone=True)
    # 3.
    _tabelas(ts)
    # 4. e 5.
    _cenas_e_tomadas(ts)
    _geracoes(ts)


RECUSA = f"""
SELECT EXISTS (SELECT 1 FROM roteiros) OR EXISTS (SELECT 1 FROM pronuncias)
    OR EXISTS (SELECT 1 FROM cena_tomadas WHERE origem::text = 'geracao_local'
               OR limpa_em IS NOT NULL)
    OR EXISTS (SELECT 1 FROM cenas WHERE keyframe_inicial_id IS NOT NULL
               OR keyframe_final_id IS NOT NULL OR keyframe_geracao_id IS NOT NULL)
    OR EXISTS (SELECT 1 FROM geracoes WHERE passo IN ({_lista(PASSOS_011)}))
    OR EXISTS (SELECT 1 FROM geracao_candidatos WHERE video_key IS NOT NULL)
    OR EXISTS (SELECT 1 FROM images WHERE kind::text = 'keyframe')
    OR EXISTS (SELECT 1 FROM conteudos WHERE gerado_ia)
"""


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(RECUSA)).scalar():
        raise RuntimeError("downgrade da 0027 recusado: há roteiros, pronúncias, tomadas locais, "
                           "keyframes, gerações ou vídeos da 011")
    # 5. e 4. (na ordem inversa)
    op.drop_column("conteudos", "gerado_ia")
    op.execute(TRIGGER_FN_021)
    op.drop_constraint("ck_candidatos_video", "geracao_candidatos", type_="check")
    op.drop_constraint("ck_candidatos_midia", "geracao_candidatos", type_="check")
    op.create_check_constraint("ck_candidatos_midia", "geracao_candidatos",
                               "num_nonnulls(image_id, audio_id) <= 1")
    op.drop_constraint("uq_candidatos_video_key", "geracao_candidatos", type_="unique")
    for col in ("video_bytes", "video_fps", "video_altura", "video_largura", "video_duracao_ms",
                "video_miniatura_key", "video_key"):
        op.drop_column("geracao_candidatos", col)
    op.drop_constraint("ck_geracoes_passo", "geracoes", type_="check")
    op.create_check_constraint("ck_geracoes_passo", "geracoes",
                               f"passo IN ({_lista(PASSOS_021)})")
    op.drop_index("ix_geracoes_desuso", table_name="geracoes")
    op.drop_column("geracoes", "desuso_em")

    op.drop_index("ix_cena_tomadas_geracao", table_name="cena_tomadas")
    op.drop_index("ix_cena_tomadas_desuso", table_name="cena_tomadas")
    for ck in ("ck_tomadas_fps", "ck_tomadas_limpa_local", "ck_tomadas_limpa",
               "ck_tomadas_origem_local"):
        op.drop_constraint(ck, "cena_tomadas", type_="check")
    for col in ("video_key", "miniatura_key", "bytes"):
        op.alter_column("cena_tomadas", col, nullable=False)
    for col in ("limpa_em", "desuso_em", "fps", "motor", "keyframe_image_id", "geracao_id"):
        op.drop_column("cena_tomadas", col)

    op.drop_index("ix_cenas_keyframe_inicial", table_name="cenas")
    for ck in ("ck_cenas_duracao_max", "ck_cenas_keyframe", "ck_cenas_keyframe_refs",
               "ck_cenas_keyframe_instrucao", "ck_cenas_resolucao"):
        op.drop_constraint(ck, "cenas", type_="check")
    for col in ("duracao_max_s", "keyframe_geracao_id", "keyframe_refs", "keyframe_instrucao",
                "keyframe_final_id", "keyframe_inicial_id", "altura", "largura", "motor"):
        op.drop_column("cenas", col)

    # 3.
    op.drop_constraint("fk_roteiros_narracao", "roteiros", type_="foreignkey")
    op.execute("DROP TRIGGER roteiro_entregas_so_insercao ON roteiro_entregas")
    op.execute("DROP FUNCTION roteiro_entregas_so_insercao()")
    for tabela in TABELAS:
        op.drop_table(tabela)
    # 2. (os valores do passo 1 ficam: ver o docstring)
    for tipo in reversed(TIPOS):
        tipo.drop(bind)
