"""vídeo guiado: grade, quadros por cena, trechos por posição e a conversa (spec 031)

Na ordem do data-model:
1. os tipos `roteiro_tipo_video`, `conversa_estado`, `conversa_tipo`, `posicao_reuso` e
   `quadro_papel` (só tipos novos: nada fora da transação);
2. as colunas do guiado em `roteiros` (com o `ck_roteiros_guiado`: as 4 da grade juntas ou
   nenhuma) e em `roteiro_cenas` (trechos, reuso, motivo, aprovações e orçamento); a posição do
   guiado pode ficar sem fala (o `ck_roteiro_cenas_frases` passa a valer só na 011);
3. `roteiro_trechos` (a tomada de cada trecho, FK composta para a posição);
4. `trechos`/`origem_cena_id` em `cenas`, a `cena_quadros` (UNIQUE parcial por ordem entre os
   não arquivados) e `trecho`/`keyframe_fim_image_id` em `cena_tomadas`;
5. `roteiro_conversa` (só inserção, trigger `roteiro_conversa_so_insercao`);
6. o `ck_geracoes_passo` com os 23 passos e a função do trigger `geracao_candidatos_midia` com os
   2 passos novos de texto (sem mídia).

Downgrade (só dev): recusa se houver roteiro guiado, quadro, trecho, mensagem, cena com trechos
ou derivada, tomada de trecho ou geração dos 2 passos novos; senão remove tudo na ordem inversa e
volta o CHECK e o trigger da 0027. Nenhum objeto do MinIO é tocado.

Revision ID: 0028_video_guiado
Revises: 0027_roteiros_video_local
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_video_guiado"
down_revision: str | None = "0027_roteiros_video_local"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Os 21 da 0027 e os 2 da 031, na ordem de `geracao/passos.py` (o teste cruzado confere).
PASSOS = (
    "avatar.rosto_origem", "avatar.rosto_frontal", "avatar.rostos_34", "avatar.corpo_base",
    "avatar.look", "avatar.pose", "avatar.identidade",
    "voz.gravacao", "voz.design", "voz.teste",
    "produto.ficha", "produto.recorte", "produto.flat",
    "cenario.cena", "cenario.variacao",
    "roteiro.plano", "roteiro.narracao", "cena.keyframe", "cena.clipe", "roteiro.montagem",
    "roteiro.acabamento",
    "roteiro.perguntas", "roteiro.ajuste",
)
PASSOS_0027 = PASSOS[:21]
PASSOS_031 = PASSOS[21:]
SEM_MIDIA = ("produto.ficha", "avatar.identidade", "roteiro.plano", *PASSOS_031)
SEM_MIDIA_0027 = ("produto.ficha", "avatar.identidade", "roteiro.plano")
VIDEO = ("cena.clipe", "roteiro.montagem", "roteiro.acabamento")


def _enum(name: str, *valores: str) -> postgresql.ENUM:
    return postgresql.ENUM(*valores, name=name, create_type=False)


roteiro_tipo_video = _enum("roteiro_tipo_video", "avatar_pov")
conversa_estado = _enum("conversa_estado", "sem_perguntas", "perguntando", "respondida")
conversa_tipo = _enum("conversa_tipo", "pergunta", "resposta", "pedido_troca", "esclarecimento",
                      "aviso")
posicao_reuso = _enum("posicao_reuso", "total", "plano", "nova")
quadro_papel = _enum("quadro_papel", "inicio", "meio1", "meio2", "fim")
TIPOS = (roteiro_tipo_video, conversa_estado, conversa_tipo, posicao_reuso, quadro_papel)


def _lista(valores: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


def _trigger_fn(sem_midia: Sequence[str]) -> str:
    """A função da 0027 (só INSERT), com a lista dos passos sem mídia como parâmetro."""
    return f"""
CREATE OR REPLACE FUNCTION geracao_candidatos_midia() RETURNS trigger AS $$
DECLARE
    v_passo text;
BEGIN
    SELECT passo INTO v_passo FROM geracoes WHERE id = NEW.geracao_id;
    IF v_passo IN ({_lista(sem_midia)}) THEN
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
CREATE FUNCTION roteiro_conversa_so_insercao() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'roteiro_conversa: só inserção (% recusado)', TG_OP
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;
"""

CK_FRASES_0027 = "cardinality(frases) >= 1"
CK_FRASES = "cardinality(frases) >= 1 OR trechos IS NOT NULL"


def _roteiros(ts) -> None:
    op.add_column("roteiros", sa.Column("tipo_video", roteiro_tipo_video))
    op.add_column("roteiros", sa.Column("cenario_id", sa.Uuid(), sa.ForeignKey(
        "assets.id", name="fk_roteiros_cenario")))
    op.add_column("roteiros", sa.Column("duracao_alvo_s", sa.SmallInteger()))
    op.add_column("roteiros", sa.Column("trecho_base_s", sa.SmallInteger()))
    op.add_column("roteiros", sa.Column("conversa_estado", conversa_estado))
    op.create_check_constraint(
        "ck_roteiros_guiado", "roteiros",
        "num_nulls(tipo_video, cenario_id, duracao_alvo_s, trecho_base_s) IN (0, 4)")
    # A grade guardada (FR-033): base de 3 a 10 s e duração múltipla dela, de 1× a 12× (o teto do
    # `ROTEIRO_GRADE_MAX`; o do `.env` é conferido no service).
    op.create_check_constraint(
        "ck_roteiros_grade", "roteiros",
        "trecho_base_s IS NULL OR (trecho_base_s BETWEEN 3 AND 10 "
        "AND duracao_alvo_s % trecho_base_s = 0 "
        "AND duracao_alvo_s BETWEEN trecho_base_s AND 12 * trecho_base_s)")
    op.create_check_constraint("ck_roteiros_conversa", "roteiros",
                               "conversa_estado IS NULL OR tipo_video IS NOT NULL")
    op.create_index("ix_roteiros_cenario", "roteiros", ["cenario_id"],
                    postgresql_where=sa.text("cenario_id IS NOT NULL"))

    op.add_column("roteiro_cenas", sa.Column("trechos", sa.SmallInteger()))
    op.add_column("roteiro_cenas", sa.Column("reuso", posicao_reuso))
    op.add_column("roteiro_cenas", sa.Column("motivo", sa.Text()))
    op.add_column("roteiro_cenas", sa.Column("aprovado_keyframes_em", ts))
    op.add_column("roteiro_cenas", sa.Column("aprovado_keyframes_por", sa.Uuid(), sa.ForeignKey(
        "users.id", name="fk_roteiro_cenas_aprovado_keyframes")))
    op.add_column("roteiro_cenas", sa.Column("aprovado_clipe_em", ts))
    op.add_column("roteiro_cenas", sa.Column("aprovado_clipe_por", sa.Uuid(), sa.ForeignKey(
        "users.id", name="fk_roteiro_cenas_aprovado_clipe")))
    op.add_column("roteiro_cenas", sa.Column("orcamento_chars", sa.SmallInteger()))
    op.create_check_constraint("ck_roteiro_cenas_trechos", "roteiro_cenas",
                               "trechos IS NULL OR trechos BETWEEN 1 AND 3")
    op.create_check_constraint("ck_roteiro_cenas_motivo", "roteiro_cenas",
                               "motivo IS NULL OR char_length(motivo) <= 300")
    op.create_check_constraint(
        "ck_roteiro_cenas_aprovacoes", "roteiro_cenas",
        "(aprovado_keyframes_em IS NULL) = (aprovado_keyframes_por IS NULL) "
        "AND (aprovado_clipe_em IS NULL) = (aprovado_clipe_por IS NULL)")
    op.create_check_constraint("ck_roteiro_cenas_orcamento", "roteiro_cenas",
                               "orcamento_chars IS NULL OR orcamento_chars >= 0")
    op.drop_constraint("ck_roteiro_cenas_frases", "roteiro_cenas", type_="check")
    op.create_check_constraint("ck_roteiro_cenas_frases", "roteiro_cenas", CK_FRASES)

    op.create_table(
        "roteiro_trechos",
        sa.Column("roteiro_id", sa.Uuid(), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False),
        sa.Column("trecho", sa.SmallInteger(), nullable=False),
        sa.Column("tomada_id", sa.Uuid(), sa.ForeignKey("cena_tomadas.id")),
        sa.PrimaryKeyConstraint("roteiro_id", "ordem", "trecho"),
        sa.ForeignKeyConstraint(["roteiro_id", "ordem"],
                                ["roteiro_cenas.roteiro_id", "roteiro_cenas.ordem"],
                                name="fk_roteiro_trechos_posicao"),
        sa.CheckConstraint("trecho BETWEEN 0 AND 2", name="ck_roteiro_trechos_trecho"),
    )
    op.create_index("ix_roteiro_trechos_tomada", "roteiro_trechos", ["tomada_id"],
                    postgresql_where=sa.text("tomada_id IS NOT NULL"))


def _cenas(ts) -> None:
    op.add_column("cenas", sa.Column("trechos", sa.SmallInteger()))
    op.add_column("cenas", sa.Column("origem_cena_id", sa.Uuid(), sa.ForeignKey(
        "cenas.id", name="fk_cenas_origem")))
    op.create_check_constraint("ck_cenas_trechos", "cenas",
                               "trechos IS NULL OR trechos BETWEEN 1 AND 3")
    op.create_check_constraint("ck_cenas_origem", "cenas",
                               "origem_cena_id IS NULL OR origem_cena_id <> id")
    op.create_index("ix_cenas_origem", "cenas", ["origem_cena_id"],
                    postgresql_where=sa.text("origem_cena_id IS NOT NULL"))

    op.create_table(
        "cena_quadros",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cena_id", sa.Uuid(), sa.ForeignKey("cenas.id"), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False),
        sa.Column("papel", quadro_papel, nullable=False),
        sa.Column("instrucao", sa.Text(), server_default="", nullable=False),
        sa.Column("image_id", sa.Uuid(), sa.ForeignKey("images.id")),
        sa.Column("geracao_id", sa.Uuid(), sa.ForeignKey("geracoes.id")),
        sa.Column("provisorio", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("archived_at", ts),
        sa.Column("archived_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.CheckConstraint("ordem BETWEEN 0 AND 3", name="ck_cena_quadros_ordem"),
        sa.CheckConstraint("(ordem = 0) = (papel = 'inicio') AND (papel <> 'fim' OR ordem >= 1)",
                           name="ck_cena_quadros_papel"),
        sa.CheckConstraint("char_length(instrucao) <= 2000", name="ck_cena_quadros_instrucao"),
        sa.CheckConstraint("NOT provisorio OR image_id IS NOT NULL",
                           name="ck_cena_quadros_provisorio"),
    )
    op.create_index("uq_cena_quadros_ordem", "cena_quadros", ["cena_id", "ordem"], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL"))
    op.create_index("ix_cena_quadros_image", "cena_quadros", ["image_id"],
                    postgresql_where=sa.text("image_id IS NOT NULL"))
    op.create_index("ix_cena_quadros_geracao", "cena_quadros", ["geracao_id"],
                    postgresql_where=sa.text("geracao_id IS NOT NULL"))

    op.add_column("cena_tomadas", sa.Column("trecho", sa.SmallInteger()))
    op.add_column("cena_tomadas", sa.Column("keyframe_fim_image_id", sa.Uuid(), sa.ForeignKey(
        "images.id", name="fk_cena_tomadas_keyframe_fim")))
    op.create_check_constraint(
        "ck_tomadas_trecho", "cena_tomadas",
        "trecho IS NULL OR (trecho BETWEEN 0 AND 2 AND origem = 'geracao_local' "
        "AND keyframe_fim_image_id IS NOT NULL)")
    op.create_index("ix_cena_tomadas_trecho", "cena_tomadas", ["cena_id", "trecho"],
                    postgresql_where=sa.text("trecho IS NOT NULL"))


def _conversa(ts) -> None:
    op.create_table(
        "roteiro_conversa",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("roteiro_id", sa.Uuid(), sa.ForeignKey("roteiros.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("tipo", conversa_tipo, nullable=False),
        sa.Column("pergunta_id", sa.Text()),
        sa.Column("conteudo", postgresql.JSONB(), nullable=False),
        sa.Column("alvo", postgresql.JSONB()),
        sa.Column("ia_chamada_id", sa.Uuid(), sa.ForeignKey("ia_chamadas.id")),
        sa.Column("autor_tipo", sa.Text(), nullable=False),
        sa.Column("autor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", ts, server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("roteiro_id", "seq", name="uq_roteiro_conversa_seq"),
        sa.CheckConstraint("seq >= 1", name="ck_roteiro_conversa_seq"),
        sa.CheckConstraint("pergunta_id IS NULL OR char_length(pergunta_id) BETWEEN 1 AND 60",
                           name="ck_roteiro_conversa_pergunta"),
        sa.CheckConstraint("jsonb_typeof(conteudo) = 'object' AND "
                           "(alvo IS NULL OR jsonb_typeof(alvo) = 'object')",
                           name="ck_roteiro_conversa_json"),
        sa.CheckConstraint("autor_tipo IN ('user', 'system:roteiro') AND "
                           "(autor_tipo = 'user') = (autor_id IS NOT NULL)",
                           name="ck_roteiro_conversa_autor"),
    )
    op.execute(SO_INSERCAO_FN)
    op.execute("CREATE TRIGGER roteiro_conversa_so_insercao BEFORE UPDATE OR DELETE ON "
               "roteiro_conversa FOR EACH ROW EXECUTE FUNCTION roteiro_conversa_so_insercao()")


def _geracoes() -> None:
    op.drop_constraint("ck_geracoes_passo", "geracoes", type_="check")
    op.create_check_constraint("ck_geracoes_passo", "geracoes", f"passo IN ({_lista(PASSOS)})")
    op.execute(_trigger_fn(SEM_MIDIA))


def upgrade() -> None:
    bind = op.get_bind()
    for tipo in TIPOS:
        tipo.create(bind, checkfirst=True)
    ts = sa.DateTime(timezone=True)
    _roteiros(ts)
    _cenas(ts)
    _conversa(ts)
    _geracoes()


RECUSA = f"""
SELECT EXISTS (SELECT 1 FROM roteiros WHERE tipo_video IS NOT NULL OR conversa_estado IS NOT NULL)
    OR EXISTS (SELECT 1 FROM roteiro_cenas WHERE trechos IS NOT NULL OR reuso IS NOT NULL)
    OR EXISTS (SELECT 1 FROM roteiro_trechos) OR EXISTS (SELECT 1 FROM roteiro_conversa)
    OR EXISTS (SELECT 1 FROM cena_quadros)
    OR EXISTS (SELECT 1 FROM cenas WHERE trechos IS NOT NULL OR origem_cena_id IS NOT NULL)
    OR EXISTS (SELECT 1 FROM cena_tomadas WHERE trecho IS NOT NULL
               OR keyframe_fim_image_id IS NOT NULL)
    OR EXISTS (SELECT 1 FROM geracoes WHERE passo IN ({_lista(PASSOS_031)}))
"""


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(RECUSA)).scalar():
        raise RuntimeError("downgrade da 0028 recusado: há roteiros guiados, quadros, trechos, "
                           "conversas, cenas derivadas ou gerações da 031")
    op.execute(_trigger_fn(SEM_MIDIA_0027))
    op.drop_constraint("ck_geracoes_passo", "geracoes", type_="check")
    op.create_check_constraint("ck_geracoes_passo", "geracoes",
                               f"passo IN ({_lista(PASSOS_0027)})")

    op.execute("DROP TRIGGER roteiro_conversa_so_insercao ON roteiro_conversa")
    op.execute("DROP FUNCTION roteiro_conversa_so_insercao()")
    op.drop_table("roteiro_conversa")

    op.drop_index("ix_cena_tomadas_trecho", table_name="cena_tomadas")
    op.drop_constraint("ck_tomadas_trecho", "cena_tomadas", type_="check")
    op.drop_column("cena_tomadas", "keyframe_fim_image_id")
    op.drop_column("cena_tomadas", "trecho")
    op.drop_table("cena_quadros")
    op.drop_index("ix_cenas_origem", table_name="cenas")
    op.drop_constraint("ck_cenas_origem", "cenas", type_="check")
    op.drop_constraint("ck_cenas_trechos", "cenas", type_="check")
    op.drop_column("cenas", "origem_cena_id")
    op.drop_column("cenas", "trechos")

    op.drop_table("roteiro_trechos")
    op.drop_constraint("ck_roteiro_cenas_frases", "roteiro_cenas", type_="check")
    op.create_check_constraint("ck_roteiro_cenas_frases", "roteiro_cenas", CK_FRASES_0027)
    for ck in ("ck_roteiro_cenas_orcamento", "ck_roteiro_cenas_aprovacoes",
               "ck_roteiro_cenas_motivo", "ck_roteiro_cenas_trechos"):
        op.drop_constraint(ck, "roteiro_cenas", type_="check")
    for col in ("orcamento_chars", "aprovado_clipe_por", "aprovado_clipe_em",
                "aprovado_keyframes_por", "aprovado_keyframes_em", "motivo", "reuso", "trechos"):
        op.drop_column("roteiro_cenas", col)

    op.drop_index("ix_roteiros_cenario", table_name="roteiros")
    for ck in ("ck_roteiros_conversa", "ck_roteiros_grade", "ck_roteiros_guiado"):
        op.drop_constraint(ck, "roteiros", type_="check")
    for col in ("conversa_estado", "trecho_base_s", "duracao_alvo_s", "cenario_id",
                "tipo_video"):
        op.drop_column("roteiros", col)

    for tipo in reversed(TIPOS):
        tipo.drop(bind)
