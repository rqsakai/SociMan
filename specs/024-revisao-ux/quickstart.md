# Quickstart: validar a 024-revisao-ux

## 0. Pré-requisitos
- Stack de dev no ar: `curl http://localhost:8180/api/health` → `{"status":"ok",...}`.
- Nenhuma migration. Depois de mexer na API: `npm run gen:contract`.

## 1. Testes automatizados (obrigatórios, princípio VI)
```bash
npm run test:api                                   # inclui os testes de contrato da 024 (contracts/api-024.md)
docker compose exec api uv run ruff check .
npm run check:web                                  # contrato, typecheck, build, bundle, CSP, segredos
flock /tmp/sociman-e2e.lock npm run test:e2e       # com o código CONGELADO; inclui layout-ritmo.spec.ts
flock /tmp/sociman-e2e.lock npm run test:e2e:pwa   # o Sidebar mudou
```
Esperado: tudo verde. O `layout-ritmo.spec.ts` mede SC-002, SC-003, SC-004 e SC-008 em 1280 e 390 px.

## 2. Roteiro manual com o dono (app de dev, `https://192.168.86.47:8543`)
1. **Menu:** os grupos Cortes, Analytics e Configurações abrem e fecham. Feche Configurações e recarregue: continua
   fechado. Abra Segurança por endereço: o grupo abre sozinho. Como membro, Configurações mostra só o Assistente de
   IA. No celular, o menu lateral tem os mesmos grupos.
2. **Ritmo:** em Agentes (MCP), Propostas, Gerar cortes, Conteúdos, Descobrir e Perfil, nada encosta, o espaço
   entre os blocos é o mesmo e, a 1920 px, o conteúdo para em 1440 px e fica centralizado. Confira nos temas claro
   e escuro: a faixa tem a cor da marca e não fica cinza-claro.
3. **Perfil:** sem a aba Cortes; `?aba=cortes` cai em Conteúdos filtrado. Um perfil sem banner tem cabeçalho
   compacto.
4. **Conteúdos:** "Aplicar marca num corte" envia um arquivo e o corte aparece na lista. A paginação mostra
   "Página X de Y". Abra um item na página 3 e volte: continua na página 3. Os atalhos mostram só os que têm
   contagem.
5. **Aprendizado:** Analytics › Aprendizado; troque o perfil. Um link antigo
   `/app/perfis/<id>/aprendizado?aba=temas` abre o novo endereço com a aba Temas.
6. **Descobrir:** a linha mostra o tema e o motivo. Em "Por quê?", as parcelas somam a pontuação (±1), aparecem
   todos os temas casados e a coluna diz "Nota (0 a 1)".
7. **Gerações:** a linha mostra "N aceitos · N pendentes · N arquivados". Arquive um clipe no detalhe e volte: a
   contagem muda.
8. **Propostas:** sem propostas, aparece a explicação e o link "Configurar agentes (MCP)". Com um filtro que não
   acha nada, aparece "Limpar filtros". A busca acha propostas fora da página carregada.
9. **Filtros:** em cada tela com filtro, mude um filtro principal e um de "Mais filtros", remova pela etiqueta e
   recarregue: o filtro continua (está no endereço).
10. **Datas e arquivos:** os campos de data aceitam `dd/mm/aaaa`; o seletor de arquivo diz "Escolher arquivo".

## 3. Revisão visual final
- Capturas do Playwright MCP em 1280 e 390 px das telas do item 2.
- O agente `impeccable:impeccable-finish-reviewer`, mais um novo `/impeccable critique` nas mesmas telas: nota
  ≥ 30/40 e nenhum P0 (SC-009). Linha de base: 24/40 (2026-10-06).
