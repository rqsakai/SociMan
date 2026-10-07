# Handoff: revisão de UX tela a tela (SociMan)

**De:** sessão de 2026-10-06 (specs 009, 010, 013, 019, 020, 022 e 023 implementadas e commitadas)
**Para:** nova sessão de revisão de UX
**Repo:** `/home/sakai/Projects/tiktok-shop/SociMan`, branch `004-kit-de-marca-poc`. Último commit
`8b4c634` (023). O working tree está limpo, fora de `docs/insumos/`, que é do dono e **não deve ser
commitado sem ele pedir**.

## 1. Objetivo da próxima sessão
Revisar e enxugar a UX do SPA tela a tela, com os pedidos do dono abaixo, e entregar um layout conciso e
alinhado: espaçamento consistente entre blocos e sem vazios. A verificação é feita com **Playwright** e
com o plugin **impeccable**. Antes de codar, o dono decide se isto vira uma spec do Spec Kit (proposta:
`024-revisao-ux`) ou um ajuste sem spec (ver §3).

**Pedidos do dono (literais, resumidos):**
1. **Menu principal**, agrupado:
   - Início · Perfis
   - **Cortes** › Canais-fonte, Descobrir, Gerar cortes
   - Conteúdos · Calendário · Propostas dos agentes
   - **Analytics** › Métricas, Importar da agência (+ a página de Aprendizado, item 2)
   - **Configurações** › Assistente de IA, Usuários, Segurança, Publicação automática, Agentes (MCP)
   - Minha conta
2. **Perfil** (`/app/perfis/:id`): remover a aba **Cortes** e manter **Padrões de corte**. Tirar
   **Aprendizado** do perfil e transformá-lo numa página própria sob Analytics.
3. **Descobrir** (`/app/descobrir`): mostrar por que o vídeo tem aquela confiança (resumo do motivo e o
   **tema/assunto**) para ajudar a escolher.
4. **Gerar cortes** (`/app/envios`, aba Gerações): por envio, mostrar quantos clipes foram
   **aceitos, arquivados e pendentes**, e não só "pronto".
5. **Conteúdos** (`/app/conteudos`): trocar "Carregar mais" por **paginação numerada**.
6. **Propostas** (`/app/propostas`): a tela vazia não explica o que é. Falta estado vazio explicativo,
   porque as propostas só chegam depois que os agentes do OpenClaw forem ligados ao MCP.
7. **UX geral:** revisão completa com impeccable + Playwright. Exemplo citado: a tela de configuração do
   MCP tem muito espaço em branco e pouco espaço entre os blocos.

## 2. Estado atual
- **Pronto e em uso:** todas as telas acima existem e passam no e2e (84 testes; última suíte verde em
  2026-10-06).
- **Menu:** é plano, em `apps/web/src/components/shell/nav.ts`. A Sidebar não tem grupos.
- **Perfil:** abas em `apps/web/src/pages/perfis/tabs/` (`CortesTab`, `PadroesCorteTab`, …). O
  Aprendizado está em `pages/aprendizado/` (`Aprendizado.tsx` + `abas/`), na rota
  `/app/perfis/:id/aprendizado`, com links no perfil, em "O que funciona" e no detalhe do vídeo.
- **Descobrir:** `pages/descobrir/Descobrir.tsx`. A pontuação vem de `canais/` (006). A afinidade e os
  temas cortados vêm de `aprendizado/` (023); o tema do vídeo-fonte vem das palavras-chave, no cache
  `aprendizado_fonte_temas`.
- **Gerações:** `pages/envios/EnviosList.tsx` e `EnvioDetalhe.tsx`. Os estados dos cortes estão em
  `cortes.status` e `archived_at`; o destino aprovado está em `postagens.aprovado_em`.
- **Conteúdos:** `pages/conteudos/Conteudos.tsx`. Hoje tem "Carregar mais", com API por cursor em
  `conteudos/consulta.py`; paginação numerada pode exigir `total`/`offset` na API.
- **Propostas:** `pages/propostas/Propostas.tsx`.
- **MCP:** `pages/configuracoes/Agentes.tsx`.
- **Plugin impeccable** instalado (`impeccable@impeccable` 4.5.0), com a skill `impeccable:impeccable` e
  os agentes `impeccable:impeccable-finish-reviewer` e `impeccable:impeccable-documenter`.

## 3. Decisões em aberto
- **Spec ou não?** A constitution exige spec para feature. A reorganização de menu e as abas são
  ajuste de UX, mas os itens 3, 4 e 5 mudam dados e API (motivo e tema no Descobrir, contagens por envio,
  paginação com total). *Inclinação:* uma spec curta `024-revisao-ux`, com o clarify das perguntas
  abaixo.
- **Rotas antigas:** `/app/perfis/:id/aprendizado` vira `/app/aprendizado?perfil=…`? Manter redirect
  para não quebrar links e e2e.
- **Grupos do menu:** o grupo pode ser só rótulo (sempre aberto) ou colapsável com estado lembrado.
  Definir como fica no celular.
- **Paginação:** offset/limit com total (custo de `count(*)`) ou páginas de cursor. Definir o tamanho da
  página.
- **Descobrir, "por quê":** reaproveitar o diálogo "Por quê? (N pontos)" que já existe, mostrando o
  resumo na linha, ou criar uma coluna nova "Tema".

## 4. Skills a usar
- `impeccable:impeccable`, depois o agente `impeccable:impeccable-finish-reviewer` no fim (pedido do
  dono).
- `speckit-specify` → `speckit-clarify` → `speckit-plan` → `speckit-tasks` → `speckit-implement`, se
  virar spec.
- `superpowers:brainstorming`, antes de mexer no layout.
- `design:design-critique`, `design:accessibility-review`, `frontend-design:frontend-design`.
- Playwright MCP (`mcp__plugin_playwright_playwright__*`), para capturas em 1280 e 390 px.

## 5. Artefatos (só referências)
- **Regras do projeto:** `CLAUDE.md` (seções Frontend, Analytics, Armadilhas 4/6/11/18),
  `.specify/memory/constitution.md` (4.2.0).
- **Referência visual:** `docs/design/layout-referencia.md`. Paleta e gráficos:
  `docs/adr/0002-graficos-echarts.md`, `specs/019-analytics/research.md` (R11).
- **Specs relacionadas:**
  - 005 (UI base): `specs/005-ui-base/`.
  - 006 (Descobrir e Gerações): `specs/006-cortes-openshorts/`.
  - 009 (Propostas e MCP): `specs/009-mcp/`.
  - 014 (Conteúdos): `specs/014-central-de-conteudos/`.
  - 023 (Aprendizado): `specs/023-aprendizado/`.
- **Componentes:** `apps/web/src/components/shell/` (Sidebar, nav.ts, AppShell),
  `components/data-table/`, `components/ui/`.
- **e2e que dependem de menu e rotas:** `e2e/*.spec.ts`, que usam `nav(page, "…")` em `e2e/helpers.ts`.

## Cuidados (lições desta sessão)
- **O dono usa o app de dev ao vivo.** Coluna nova só entra no código junto com a migration aplicada.
  Não chamar rota que ainda não existe.
- **e2e:** sempre `flock /tmp/sociman-e2e.lock npm run test:e2e`. Rode a suíte final com o código
  **congelado**: edições no meio do teste recarregam o Vite da stack e2e e geram falsas falhas.
- **Commit e push só quando o dono pedir.** O push às vezes é bloqueado para o agente; nesse caso, o dono
  roda `! git push`.
