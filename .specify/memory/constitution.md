# Constitution do SociMan

## Core Principles

### I. Nenhum agente publica (INEGOCIÁVEL)
O SociMan, sua API e suas tools MCP NÃO DEVEM ter endpoint, integração, credencial nem job que
publique conteúdo em rede social. O sistema prepara, organiza e registra; quem posta é o dono.
Qualquer spec que proponha publicação automática é rejeitada.

**Por quê:** é uma regra de negócio da agência, e publicar sem revisão humana expõe as contas a
banimento e a problemas de direito autoral.

### II. Direito primeiro (INEGOCIÁVEL)
Só pode virar corte um vídeo de canal-fonte com status `autorizado` ou `programa-de-cortes`.
A regra DEVE ser aplicada no backend (API e MCP), não só na UI. Só um usuário humano com papel de
dono pode mudar o status de direito de um canal; um cliente MCP NÃO DEVE conseguir fazer isso.
Toda mudança de status DEVE registrar a evidência (link, print ou nota) e o autor.

**Por quê:** cortes de fonte não autorizada põem a agência em risco jurídico, e a decisão é
exclusiva do dono.

### III. Marca em tokens
A identidade visual de cada conta (paleta, fontes, legenda, cartão de gancho, marca d'água,
stickers, card final, bordões e séries) DEVE ser dado estruturado e validado por schema, aplicável
por máquina (OpenShorts, ffmpeg, HyperFrames) e verificável pelo revisor. Texto livre só pode
aparecer como nota e nunca como fonte da regra.

**Por quê:** o resultado "cru" dos primeiros testes veio de uma marca descrita em prosa, que
nenhuma ferramenta conseguia aplicar nem conferir.

### IV. O contrato é a fonte única
O OpenAPI gerado pelo FastAPI é a fonte única do contrato. O cliente tipado do SPA
(`packages/contract`) e as tools do MCP DEVEM ser gerados a partir dele. Tipos, rotas e schemas NÃO
DEVEM ser duplicados à mão, e a verificação automatizada DEVE acusar divergência entre o OpenAPI
e os artefatos gerados.

**Por quê:** SPA, MCP e agentes falam com o mesmo backend, e contratos copiados à mão divergem
em silêncio.

### V. Segurança e segredos
- Nenhum segredo no repositório nem no bundle do SPA (`npm run check:secrets`,
  `npm run check:bundle`).
- CSP estrita em produção, com `apps/web/vite.config.ts` e `docker/nginx/05-edge-mode.envsh`
  sincronizados (`npm run check:csp`).
- A API só é alcançada pelo edge, e sua porta NÃO DEVE ser publicada.
- As credenciais do compose servem só para dev e NÃO DEVEM ser usadas fora dele.

**Por quê:** a API confia em `X-Forwarded-*`, e o SPA roda num navegador que a IA e terceiros
podem inspecionar.

### VI. Empírico: testes antes de pronto
Nenhuma feature pode ser declarada pronta sem que passem: `uv run pytest`, `uv run ruff check .`,
`npm run check:web` e os testes e2e (Playwright) dos fluxos críticos que ela toca. Cada regra
inegociável (I, II e VII) DEVE ter teste automatizado no backend. A ordem de escrita (teste antes
ou depois do código) é livre, mas o teste acompanha a entrega.

**Por quê:** o dono trabalha de forma empírica, e "funcionou na minha máquina" não é evidência.

### VII. Humano no controle
Toda mutação, venha da UI ou do MCP, DEVE registrar o autor (usuário humano ou cliente MCP
identificado), a data e o estado anterior. Nada é apagado de fato (soft-delete), e o dono DEVE
poder ver o histórico e reverter uma mudança. Os limites do que o MCP pode escrever são
definidos na spec `009-mcp`, dentro deste princípio.

**Por quê:** agentes de IA escrevem no mesmo banco que o dono, e um erro de agente precisa ser
rastreável e desfeito sem perda.

### VIII. Simplicidade
YAGNI e um passo por vez. Nenhuma infraestrutura, dependência, serviço ou abstração nova entra sem
uma spec aprovada que precise dela. Complexidade além do mínimo DEVE ser justificada na seção
"Complexity Tracking" do `plan.md`.

**Por quê:** o projeto tem um dono só, e cada peça extra é manutenção que ninguém pediu.

## Restrições técnicas

- **Stack fixa:** SPA React 19 + Vite + Tailwind 4 (`apps/web`); API FastAPI com Python 3.12 e uv
  (`apps/api`); SQLAlchemy 2 + Alembic + PostgreSQL; Redis para estado efêmero (sessões de
  autenticação e limites de tentativa); MinIO + imgproxy para imagens; nginx como edge.
  Trocar ou adicionar um componente da stack é emenda desta constitution.
- **Ferramentas só de dev:** Mailpit captura os e-mails em desenvolvimento e testes e NÃO DEVE ser
  usado em produção.
- **Redis não é banco de registro:** dado que precisa sobreviver (usuários, eventos de segurança,
  histórico) fica no PostgreSQL; perder o Redis no máximo obriga os usuários a entrar de novo.
- **Banco:** toda mudança de schema passa por migration Alembic versionada.
- **Portas:** edge 8180/8543. NÃO usar 8000/5175 (OpenShorts) nem 18789 (OpenClaw).
- **Containers** rodam como UID 1000, e pastas de bind mount são criadas antes do `up`.
- **Referência:** `reference/` e `docs/reference/` são só consulta e NÃO DEVEM ser importados nem
  executados.
- **Idioma:** docs, specs, mensagens de commit e textos da UI em pt-BR.

## Fluxo de desenvolvimento

- **Spec Kit obrigatório:** `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` →
  `/speckit-tasks` → `/speckit-implement`. Nenhum código de feature sem spec aprovada pelo dono
  em `specs/NNN-nome/`.
- **Constitution Check:** o `plan.md` de cada spec DEVE conferir os oito princípios antes da
  pesquisa e de novo depois do design, e justificar qualquer exceção.
- **Um passo por vez:** comando mostrado, explicado em uma linha, executado e verificado antes do
  próximo.
- **Git:** commit e push só quando o dono pedir, com mensagens em pt-BR no imperativo.

## Governance

- Esta constitution prevalece sobre qualquer outra prática do projeto. A orientação do dia a dia
  (comandos, armadilhas) fica no `CLAUDE.md`, que NÃO DEVE contradizê-la.
- **Emendas:** feitas via `/speckit-constitution`, com aprovação explícita do dono e registro no
  Sync Impact Report.
- **Versionamento semântico:** MAJOR para remover ou redefinir um princípio; MINOR para um
  princípio ou seção nova, ou uma orientação ampliada de forma relevante; PATCH para redação e
  esclarecimentos.
- **Conformidade:** toda spec, plano e revisão de código verifica a aderência aos princípios.
  Uma violação dos princípios I, II ou VII bloqueia a entrega.

**Version**: 1.1.0 | **Ratified**: 2026-09-28 | **Last Amended**: 2026-09-28
