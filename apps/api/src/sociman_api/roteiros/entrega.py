"""A entrega do roteiro (research R13, FR-034): numa transação só, no `aplicar` do
`roteiro.acabamento`:
1. o conteúdo da 014 (vídeo próprio) com o vídeo HD, copiado no MinIO, título = nome do roteiro e
   `gerado_ia = true`, **sem destino** (aprovar, agendar e publicar continuam na 014/015);
2. a `roteiro_entregas` (só inserção) com a narração, a prévia, o acabamento, as posições e os
   motores (a atribuição do MiniMax);
3. o vínculo das cenas ao conteúdo (`cenas.usos.definir`, a 010), no nome de quem comandou o
   roteiro (Divergência 5: `cena_usos.criado_por` é humano); as cenas viram `usada`;
4. o roteiro `pronto` com o `conteudo_id`, e o `desuso_em` no acabamento (o conteúdo já tem a
   sua cópia, R12).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from sociman_api import history
from sociman_api.auth.deps import Actor
from sociman_api.cenas import schemas as cenas_schemas
from sociman_api.cenas import usos as cenas_usos
from sociman_api.conteudos import video_proprio
from sociman_api.geracao.models import Geracao, GeracaoCandidato
from sociman_api.roteiros import estado
from sociman_api.roteiros.models import ENTITY, Roteiro, RoteiroEntrega, RoteiroStatus

ATRIBUICAO_MINIMAX = ("Este vídeo usa o modelo MiniMax H3: a licença exige exibir \"MiniMax H3\" "
                      "em uso comercial.")


def entregar(db: Session, r: Roteiro, geracao: Geracao, candidato: GeracaoCandidato) -> uuid.UUID:
    """Cria o conteúdo e a entrega e deixa o roteiro `pronto`. Devolve o id do conteúdo."""
    autor = Actor(kind="user", user_id=r.comandado_por or geracao.created_by)
    ex = estado.extras(geracao)
    titulo = (r.nome or "Vídeo")[:video_proprio.TITULO_MAX]
    conteudo = video_proprio.create_de_objeto(
        db, autor, r.perfil_id, candidato.video_key, filename=f"roteiro-{r.id.hex[:8]}.mp4",
        titulo=titulo, gerado_ia=True)
    posicoes = [{"ordem": p["ordem"], "cenaId": p["cenaId"], "tomadaId": p["tomadaId"],
                 "keyframeImageId": p.get("keyframeImageId"), "motor": p.get("motor"),
                 "duracaoS": p["duracaoS"]} for p in ex.get("posicoes") or []]
    motores = sorted({p["motor"] for p in posicoes if p.get("motor")})
    db.add(RoteiroEntrega(
        roteiro_id=r.id, conteudo_id=conteudo.id, narracao_id=uuid.UUID(ex["narracaoId"]),
        montagem_geracao_id=uuid.UUID(ex["montagemGeracaoId"]),
        acabamento_geracao_id=geracao.id, posicoes=posicoes, motores=motores,
        created_by=autor.user_id))
    db.flush()
    cenas = list(dict.fromkeys(uuid.UUID(p["cenaId"]) for p in posicoes))
    cenas_usos.definir(db, autor, conteudo.id,
                       cenas_schemas.UsosIn(version=conteudo.version, cena_ids=cenas))
    before = history.snapshot(r)
    r.status = RoteiroStatus.pronto
    r.conteudo_id = conteudo.id
    r.avisos = [a for a in (r.avisos or []) if a.get("code") != "tomada_curta"]
    geracao.desuso_em = datetime.now(UTC)
    db.flush()
    history.record(db, autor, ENTITY, r, "updated", before, history.snapshot(r),
                   {"acao": "entregue", "conteudoId": str(conteudo.id),
                    "geracaoId": str(geracao.id), "motores": motores})
    return conteudo.id
