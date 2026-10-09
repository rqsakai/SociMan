---
target: SociMan SPA 7 telas
total_score: 24
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 2
target_identity: "file:/home/sakai/Projects/tiktok-shop/SociMan/apps/web/src/pages"
timestamp: 2026-10-07T02-14-59Z
slug: apps-web-src-pages
---
# Critique SociMan SPA (7 telas) — 2026-10-06
Method: dual-agent (A: design review · B: detector + DOM). Viewport medido 1920px (resize falhou); mobile só pelo código. Overlay bloqueado pela CSP.
Nota: 24/40 (H1 3, H2 3, H3 3, H4 1, H5 3, H6 2, H7 2, H8 1, H9 3, H10 3).
P0 HeaderCard (mt-6 + relative -top-6 -mb-2) + raízes space-y-6 (25 páginas): faixa encosta 0px no bloco de cima (Agentes, Propostas), 8px em Gerar cortes (Tabs gap-2), 16-68px mortos dentro do card.
P1 Dois dialetos de cartão (Card shadcn px-6 py-6 × HeaderCard px-4/5) e tons de faixa sem regra; tone=dark vira cinza-claro no tema escuro.
P1 Larguras soltas: Agentes Interruptor max-w-2xl (672px) sobre Clientes 1569px; idem Publicacao, ContasTab, RegistroTab, Home.
P2 Cinco padrões de filtro (Descobrir, Propostas, Conteúdos, Gerar cortes, Cortes).
P2 Perfil: banner vazio 192px, 10 abas; Cortes com upload raro acima da lista.
Menores: barra fixa Descobrir desalinhada 8px (lg:left-80); mt-6 + gap-6 = 48px antes da tabela (Conteúdos, Descobrir); 11 atalhos com zeros em Conteúdos; "Clientes" jargão; datas mm/dd/yyyy; sem scrollbar-gutter.
