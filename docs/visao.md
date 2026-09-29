# SociMan: visão do produto (entrada para o Spec Kit)

> Rascunho do dono, 2026-09-28. Serve de entrada para `/speckit-constitution` e `/speckit-specify`. Nada aqui foi decidido em spec ainda.

## Problema
A agência (perfis de cortes e fábrica TikTok Shop) hoje é operada por agentes de IA no OpenClaw, que gravam markdown em `../shared/`. Os primeiros testes (ver `../docs/revisao-2026-09-28.md`) mostraram três problemas:
- **O resultado sai "cru":** sem identidade visual, logo, stickers ou gancho com estilo da conta.
- **O estado fica espalhado** em arquivos grandes, difíceis de consultar e de editar à mão.
- **O dono não tem uma interface** para ver e corrigir o que os agentes fazem.

## O que o SociMan é
Um **SPA (PWA) + API Python** para gerenciar as contas de mídia social **manualmente**, facilitando o que hoje é feito por IA. Um **servidor MCP** permite que qualquer IA (Claude Desktop, Claude Code, Codex, agentes do OpenClaw) leia e grave no mesmo backend.

## Domínio (primeiro recorte)
- **Contas sociais:** plataforma (TikTok, YouTube, Instagram…), @handle, nome, descrição/bio, logo, banner e status.
- **Identidade visual por conta (kit de marca):** paleta, fontes, estilo de legenda, estilo do cartão de gancho, marca d'água/logo, stickers, card final/CTA, bordões e nome de séries. Tudo em **tokens** que o produtor (OpenShorts/ffmpeg/HyperFrames) consiga aplicar.
- **Avatares:** personas (ex.: Achadinhos), imagens de referência e **poses**.
- **Cenas:** fundos e ambientes reutilizáveis, com imagem de referência e prompt.
- **Scripts:** roteiros por cena e por avatar (falas, ações, duração de até 8 s por cena para o Veo/Flow), com status.
- **Canais-fonte e vídeos:** canais de onde se tiram cortes (com status de direito `autorizado`, `programa-de-cortes`, `pendente` e evidência), vídeos cadastrados e **padrões/configurações de corte** por conta (duração, layout, estilo de legenda e gancho, hashtags).
- **Produtos (TikTok Shop):** cadastro e descrição de produtos, que a IA escreve via MCP.

## Integrações
- **MCP:** ferramentas para a IA cadastrar e buscar (criar descrição de produto, buscar vídeos, cadastrar vídeo para corte, ler o kit de marca). Os limites de escrita ainda precisam ser definidos.
- **OpenShorts** (`../openshorts`, API local): consumidor dos padrões de corte.
- **Agentes do OpenClaw:** passam a ler e escrever pelo MCP em vez de markdown solto (migração gradual).

## Princípios candidatos (para a constitution)
1. **Nenhum agente publica.** O SociMan não posta em rede social; quem posta é o dono.
2. **Direito primeiro.** Só vira corte o vídeo de um canal com status `autorizado` ou `programa-de-cortes`, e só o dono muda esse status.
3. **Marca em tokens, não em texto livre.** Todo item de identidade visual precisa ser aplicável por máquina e verificável pelo revisor.
4. **Segredos nunca no repositório** (`npm run check:secrets`). CSP estrita e nenhum segredo no bundle do SPA (herdados do volans).
5. **O contrato é a fonte única.** O OpenAPI do FastAPI gera o cliente tipado do SPA e as tools do MCP.
6. **Empírico:** teste antes de declarar pronto, com `pytest` + `npm run check:web` + e2e.
7. **Humano no controle:** o que a IA grava via MCP fica rastreável (autor, data) e reversível.

## Backlog de specs (ordem sugerida)
1. `001-auth` ✅ **especificada e implementada** (`specs/001-auth/`, 2026-09-29). Decisões:
   - **Sem cadastro público:** só o dono cria usuários, com senha provisória que precisa ser trocada no primeiro login.
   - **Verificação de e-mail obrigatória** antes do primeiro login. Os e-mails de dev são capturados pelo Mailpit.
   - **Papéis `dono` e `membro`:** o membro faz tudo, menos o que for reservado ao dono.
   - **Sessões e limites de tentativa no Redis** (constitution 1.1.0). Usuários e eventos ficam no Postgres.
   - **Log de eventos de segurança** com tela só para o dono. Todo registro guarda o autor.
   - **Contrato do SPA gerado do OpenAPI do FastAPI** (`npm run gen:contract`).
   - Pendência: o e2e ainda zera o banco de dev; separar num banco e numa API próprios.
2. `002-pwa`: modo PWA (manifest, ícones, service worker compatível com a CSP estrita).
3. `003-contas-sociais`: CRUD de contas, com upload de logo e banner (MinIO + imgproxy).
4. `004-kit-de-marca`: tokens visuais por conta.
5. `005-avatares-e-poses`
6. `006-cenas`
7. `007-scripts`: roteiros por cena e avatar.
8. `008-canais-fonte-e-videos`: canais-fonte, vídeos e padrões de corte.
9. `009-mcp`: servidor MCP sobre a API.
10. `010-produtos-shop`
11. `011-importacao`: migrar `../shared/perfis/*` e `../shared/shop/*` para o banco.
