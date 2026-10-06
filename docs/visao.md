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
1. **Publicação só com decisão humana** (constitution 4.0.0): o SociMan só envia rascunho ou publica para uma postagem aprovada e agendada por um dono; nenhum agente/IA/MCP publica.
2. **Direito é responsabilidade do dono** (constitution 3.0.0): o sistema registra o status informativo do canal-fonte, avisa e guarda o histórico, mas não bloqueia.
3. **Marca em tokens, não em texto livre.** Todo item de identidade visual precisa ser aplicável por máquina e verificável pelo revisor.
4. **Segredos nunca no repositório** (`npm run check:secrets`). Nenhum segredo no bundle do SPA. CSP com `script-src` estrito; o `style-src` aceita `'unsafe-inline'` por causa dos componentes shadcn/Radix (ver `docs/adr/0001`, constitution 2.0.0).
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
   - Resolvido (2026-09-29): o e2e roda numa stack efêmera própria (`docker-compose.e2e.yml`) e não toca mais o banco de dev.
2. `002-pwa` ✅ **implementada** (`specs/002-pwa/`, 2026-09-29). Decisões:
   - **HTTPS por CA própria da casa** (`scripts/certs-casa.sh`), instalada em cada aparelho.
   - **Endereço fixo** `https://192.168.86.47:8543`. O HTTP pelo IP redireciona para o HTTPS.
   - **Modo casa = build de produção** (`npm run casa:up`); não há service worker em dev.
   - **O service worker guarda só os arquivos da interface** (sem `/api`, sem tokens). Tem a tela
     "Sem conexão" e o aviso de versão nova.
   - **iPhone:** melhor esforço.
3. `003-contas-sociais` ✅ **implementada** (`specs/003-contas-sociais/`, 2026-09-29). Decisões:
   - **Perfil** (marca da agência) agrupa as **contas por plataforma**. O slug é fixo depois de
     criado.
   - **Histórico genérico** (`entity_versions`), reaproveitado pelas próximas specs: autor e
     antes/depois em toda mutação, arquivar em vez de apagar, e reversão só pelo dono.
   - **Logo e banner** no MinIO, validados pelo conteúdo, públicos na rede de casa via `/img`.
   - **Testes da API numa stack efêmera** (`npm run test:api`).
4. `004-kit-de-marca` ✅ **implementada** (`specs/004-kit-de-marca/`, 2026-09-29). Decisões:
   - **Kit em tokens** por perfil (paleta, legenda, gancho, marca d'água, card final, bordões, séries), versionado.
   - **Fontes próprias** e fontes padrão com licença OFL.
   - **Exportação** para o gerador de cortes (legenda e preset de gancho mais próximo).
   - **Aplicação da marca** por um worker com ffmpeg: gancho, marca d'água e card final por cima dos últimos segundos.
   - **O MinIO inteiro fica no HD**, com sentinela.
5. `005-ui-base` ✅ **implementada** (`specs/005-ui-base/`, 2026-09-29): shadcn/ui + TanStack Table
   com layout de painel (ADR 0001: `style-src 'unsafe-inline'`).
6. `006-cortes-openshorts` ✅ **implementada** (`specs/006-cortes-openshorts/`, 2026-09-29). Absorve o
   antigo item `008-canais-fonte-e-videos`. Decisões:
   - **Canais-fonte** próprios e de parceiros, com status de direito informativo (princípio II 3.0.0):
     aviso para `sem_acordo` e envio avulso, histórico de todo envio, sem bloqueio.
   - **Descoberta** de todos os vídeos do canal (API do YouTube, cota controlada) com nota explicável.
   - **Envio ao OpenShorts** local (legenda do kit, sem `auto_hook`); os clipes voltam como cortes em
     `revisao`. Serviço `agendador` (sync, acompanhamento, importação e lembretes).
   - **Textos de postagem pelo Claude**, uma postagem por conta de destino, calendário e aviso
     "Hora de postar" com o app aberto. **O SociMan não publica** (princípio I).
   - Fora: rascunho/postagem no TikTok (spec futura; exige emendar o princípio I).
7. `007-assets-do-perfil` ✅ **implementada** (`specs/007-assets-do-perfil/`, 2026-09-29). Decisões:
   - **Biblioteca por perfil:** avatares (looks, poses, descrição fixa para prompt), cenários, fundos,
     stickers, marcas d'água e imagens; os fundos e marcas d'água da 004 migraram sem perda.
   - **Só o kit bloqueia arquivar**; o uso em cortes é informativo. Link estável e download do original.
8. `008-assistente-ia` ✅ **implementada** (`specs/008-assistente-ia/`, 2026-09-29; falta validar com o Claude real, T050).
   Decisões:
   - **"Melhorar com IA"** em 13 tipos de campo (avatar, cenário, asset, perfil, kit, postagem), com
     instrução opcional, proposta + explicação, Outra versão e Descartar.
   - **Aplicar salva direto** só aquele campo (autor humano, selo "com ajuda da IA" no histórico); o
     que foi digitado nos outros campos não se perde.
   - **Bordões e séries:** lista de sugestões com seleção e "Gerar mais" (sem repetir aceitos/rejeitados).
   - **Regras por tipo de campo** editáveis pelo dono, com histórico e "voltar ao padrão"; registro de
     chamadas e resumo de custo do mês. As sugestões da 006 migraram para o mesmo registro.
9. `009-mcp`: servidor MCP sobre a API (o número fica, porque a constitution e as specs citam a `009-mcp`).
10. `010-cenas`
11. `011-scripts`: roteiros por cena e avatar.
12. `012-produtos-shop`
13. `013-importacao`: migrar `../shared/perfis/*` e `../shared/shop/*` para o banco.
14. `014-central-de-conteudos` ✅ **implementada** (`specs/014-central-de-conteudos/`, 2026-09-30). Tela Conteúdos com todo
   vídeo publicável (cortes, vídeos próprios; depois avatar/afiliado), estado por conta, aprovação (donos aprovam,
   membros pedem), agendamento com modos, intervalo mínimo por conta, sequência com prévia, e a proposta do
   OpenShorts (título, descrição, gancho) pré-preenchendo os textos.
15. `015-tiktok-rascunho` ✅ **implementada** (`specs/015-tiktok-rascunho/`, 2026-09-30; constitution 4.0.0): conectar
   contas TikTok (só donos, login pelo IP da casa), **criar rascunho** e **publicar** no horário ou "agora",
   com legenda obrigatória (descrição + hashtags), sem envio duplicado e com interruptor geral. Teste real no
   sandbox: rascunho entregue no app (`SEND_TO_USER_INBOX`). Publicar sai só "Só eu" até a auditoria da TikTok.
   Pesquisa em `docs/pesquisa/publicacao-redes.md`.
16. `016-metricas-tiktok` ✅ **implementada** (`specs/016-metricas-tiktok/`, 2026-09-30): série temporal das métricas
   públicas da conta e dos vídeos (views, curtidas, comentários, compartilhamentos, seguidores), vínculo do post
   com o conteúdo do SociMan, telas de desempenho e exportação do dataset para ML. Etapa 2 (alcance, retenção,
   audiência pela API for Business) fica para depois. Pesquisa em `docs/pesquisa/metricas-tiktok.md`.
17. `017-guia-de-comunicacao` ✅ **implementada** (`specs/017-guia-de-comunicacao/`, 2026-09-30; falta a suíte e2e inteira 2x e a validação com o Claude real): guia de voz por perfil e
   por conta (tom, regras, vocabulário, proibidas, emojis, hashtags fixas, até 5 exemplos) que entra em todo
   pedido do assistente de IA (008); só o dono edita; montar e testar o guia com a IA.
19. `019-analytics` ✅ **implementada** (`specs/019-analytics/`, 2026-10-02; falta a verificação final T061 e o quickstart com dados reais): o
   analytics de decisão em `/app/metricas`, só leitura sobre os dados da 016 e da cadeia do SociMan, em 8 abas
   (Visão geral com o ranking, Quando postar, O que funciona, Curvas, Contas, Funil, Mercado, Alertas), com
   medida do post (1 h, 24 h, 7 d), amostras mínimas, "Ver tabela" e CSV em todo card, e gráficos com o
   Apache ECharts carregado sob demanda (ADR 0002).
