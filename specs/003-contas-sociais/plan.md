# Implementation Plan: Perfis e contas sociais (003-contas-sociais)

**Branch**: `003-contas-sociais` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-contas-sociais/spec.md`

## Summary

Primeira spec de domínio do SociMan:
- **Perfis e contas:** cadastro de Perfis (slug imutável, nicho, bio, idioma, status) e das contas
  de cada perfil por plataforma, com @ e link normalizados e regras de unicidade.
- **Imagens:** logo e banner no MinIO, validados pelo conteúdo com Pillow e exibidos por URLs do
  imgproxy.
- **Histórico genérico** (`entity_versions`), reaproveitável pelas próximas specs:
  - toda mutação gera versão com autor e antes/depois;
  - nada é apagado; o registro é arquivado e pode ser restaurado;
  - o dono reverte para qualquer versão;
  - edição concorrente é detectada por controle otimista.

Detalhes em [research.md](research.md), [data-model.md](data-model.md),
[contracts/http-api.md](contracts/http-api.md) e [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Python 3.12 (API) · TypeScript 5 / React 19 (SPA)

**Primary Dependencies**: **novas na API:** `minio` (cliente S3), `Pillow` (validação de imagem) e `python-multipart` (upload). O SPA não recebe dependência nova.

**Storage**: PostgreSQL (`perfis`, `contas`, `images`, `entity_versions`); MinIO, bucket `sociman` (objetos imutáveis); imgproxy para os derivados em `/img`

**Testing**:
- pytest com Postgres, Redis e **MinIO reais** (bucket `sociman-test`);
- ruff;
- `check:web` (contrato regenerado);
- Playwright `e2e/perfis.spec.ts` (modo dev).

**Target Platform**: a mesma stack; o SPA também no modo casa (PWA da 002)

**Project Type**: web application (SPA + API)

**Performance Goals**: lista de perfis em menos de 1 s com miniaturas; upload de 5 MB em menos de 3 s na rede de casa

**Constraints**:
- sem DELETE;
- slug imutável;
- a CSP não muda (`/img` é `'self'`);
- o edge precisa aceitar corpo de até 6 MB em `/api` (hoje o limite é 1 MB, R7);
- o bucket fica privado (só o imgproxy lê).

**Scale/Scope**: poucas dezenas de perfis e contas; 19 endpoints; 3 telas novas (lista, novo, detalhe com abas)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação | Como |
|---|---|---|
| I. Nenhum agente publica | ✅ | contas são só registros; o teste-guarda T023 da 001 ganha `perfis`/`contas` sem nenhum termo de publicação |
| II. Direito primeiro | n/a | o status de direito é de canais-fonte (spec 008) |
| III. Marca em tokens | n/a (preparação) | o logo e o banner são arquivos; os tokens de marca vêm na 004, ligados ao Perfil |
| IV. Contrato é a fonte única | ✅ | as rotas novas regeneram o contrato; `check:contract` |
| V. Segurança e segredos | ✅ | o bucket fica privado; a imagem é validada pelo conteúdo, com limite de pixels; o limite de corpo fica no edge e na API; a chave do imgproxy vai para o `.env`, fora do git, e sem chave só vale o modo `unsafe` em dev, restrito ao bucket |
| VI. Testes antes de pronto | ✅ | a lista do quickstart §5 |
| VII. Humano no controle | ✅ **núcleo desta spec** | `entity_versions` com autor e antes/depois em toda mutação; sem DELETE (arquivar e restaurar); a reversão é do dono; o controle otimista evita sobrescrever sem saber |
| VIII. Simplicidade | ✅ com justificativa | três dependências Python (tabela abaixo); nenhum serviço novo (MinIO e imgproxy já estão no compose) |

**Reavaliação pós-design:** mantida.

## Project Structure

### Documentation (this feature)

```text
specs/003-contas-sociais/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── pyproject.toml                        # + minio, pillow, python-multipart
├── migrations/versions/0002_perfis.py
├── src/sociman_api/
│   ├── config.py                         # + S3_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET, IMGPROXY_KEY/SALT, IMG_PUBLIC_PATH
│   ├── history.py                        # record/snapshot/revert + EntityVersion (genérico, R1)
│   ├── storage.py                        # cliente MinIO (put/get; sem delete)
│   ├── imaging.py                        # validação Pillow + URLs imgproxy (assinadas ou unsafe em dev)
│   ├── perfis/
│   │   ├── models.py                     # Perfil, Conta, Image (+ enums)
│   │   ├── platforms.py                  # templates de link e extração de @
│   │   ├── schemas.py
│   │   ├── service.py                    # regras: slug, unicidade, versão otimista, arquivar/restaurar, imagens
│   │   ├── router_perfis.py
│   │   └── router_contas.py
│   └── main.py                           # inclui routers
└── tests/
    ├── unit/                             # platforms, slug, imaging (sem MinIO), history.diff
    └── integration/                      # perfis, contas, imagens (MinIO real), histórico/reversão, concorrência, sem DELETE

apps/web/src/
├── pages/perfis/{PerfisList,PerfilNovo,PerfilDetalhe}.tsx   # abas Dados | Contas | Histórico
├── components/{VersionHistory,ImageUpload,PlatformIcon,ProfileAvatar}.tsx
└── lib/perfis.ts                         # rótulos, formulários

docker/nginx/default.conf.template        # client_max_body_size 6m em /api/
docker-compose.yml                        # api: S3_* (dev), IMGPROXY_KEY/SALT via .env opcional; imgproxy idem
e2e/perfis.spec.ts
```

**Structure Decision**: o domínio fica em `sociman_api/perfis/`. Os serviços transversais
(`history`, `storage` e `imaging`) ficam na raiz do pacote, porque as próximas specs vão
reaproveitá-los.

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| `minio` | enviar os arquivos ao MinIO, que já está na stack | `boto3`: dependência maior, para o mesmo uso |
| `Pillow` | validar o formato real e as dimensões, e barrar decompression bomb (FR-008) | confiar na extensão ou no content-type: inseguro |
| `python-multipart` | o FastAPI exige para upload multipart | base64 em JSON: arquivo 33% maior e mais memória |
| `entity_versions` genérica | princípio VII para todas as specs de domínio, com uma só tela de histórico | tabela de histórico por entidade: duplicação a cada spec |
