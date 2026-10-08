# Roteiro manual (quickstart §2), 2026-10-08

App de dev `https://192.168.86.47:8543`, Chrome do dono (sessão de dono, tema escuro, 1920 px). Rodado pelo Claude com o dono logado.

| # | Item | Resultado |
|---|---|---|
| 1 | Menu | ✅ grupos abrem/fecham; fechado continua fechado depois de recarregar (`sociman:menu:grupos`); `/app/seguranca` abre Configurações sozinho. Membro e celular não conferidos aqui (cobertos pelo e2e `layout.spec.ts`). |
| 2 | Ritmo | ✅ Agentes, Propostas, Gerar cortes, Conteúdos, Descobrir, Perfis e Perfil: espaço de 24 px entre blocos e conteúdo com 1440 px a 1920 px. Faixa azul da marca no tema escuro. |
| 3 | Perfil | ✅ 9 abas, sem Cortes; `?aba=cortes` → `/app/conteudos?perfil=<id>`. |
| 4 | Conteúdos | ✅ "Página 3 de 23" com `?pagina=3`; atalhos só com contagem (3 + "Ver todos os atalhos"); "Aplicar marca num corte" abre com o HD e "Escolher arquivo". Envio real não feito (criaria dado). |
| 5 | Aprendizado | ✅ Analytics › Aprendizado lembra o último perfil; `/app/perfis/<id>/aprendizado?aba=temas` → `/app/aprendizado?perfil=<id>&aba=temas`. |
| 6 | Descobrir | ✅ selo do tema e motivo na linha; "Por quê?" com "Nota (0 a 1)", afinidade e temas casados. **Achado corrigido:** com o score no teto, as parcelas somavam 105,4 e o total 100; agora há a linha "Limite da escala (0 a 100)" (`ScoreReason.tsx`). |
| 7 | Gerações | ✅ "8 aceitos", "9 aceitos · 1 arquivado" por linha. Arquivar um clipe não feito (mutação). |
| 8 | Propostas | ✅ vazio explicativo com "Configurar agentes (MCP)". |
| 9 | Filtros | ✅ "Criado" em Mais filtros vai para a URL (`criadoDe`), etiqueta "Remover filtro: Criado", sobrevive ao recarregar e sai pela etiqueta (342 → 571). |
| 10 | Datas e arquivos | ✅ `dd/mm/aaaa`; "Escolher arquivo · ou solte aqui". |
