---
target: SociMan SPA após a 024
total_score: 30
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 1
target_identity: "file:/home/sakai/Projects/tiktok-shop/SociMan/apps/web/src/pages"
timestamp: 2026-10-08T13-01-38Z
slug: apps-web-src-pages
---
# Critique final da spec 024 — 2026-10-08
Method: dual-agent (A: design review · B: detector + DOM). Viewport 1920 (resize falhou); celular só pelo código e pelo e2e layout-ritmo (1280/390). Sessão caiu no meio: Conteúdos, Descobrir, Perfil, Aprendizado e Métricas revistos pelo código.
Nota: 30/40 (H1 3, H2 3, H3 3, H4 3, H5 3, H6 3, H7 3, H8 3, H9 3, H10 3). Sem P0.
Linha de base 24/40: P0 (HeaderCard mt-6) corrigido; P1 cartões/tons corrigido; P1 larguras corrigido (1440 px, Agentes 1440/1440); P2 filtros quase (Perfil de Envios fora da barra); P2 Perfil parcial (9 abas).
Corrigidos nesta rodada: P1 contraste do botão tone-primary no escuro (variante `band`); P2 item ativo do menu fora da dobra (scrollIntoView).
Abertos: P2 Perfil de Envios fora da FilterBar (decisão do T054); P3 nomes Gerar cortes/Geração de cortes/SociShorts; P3 título "Conteúdos" repetido no cartão; P3 vazio de Propostas não considera o estado do MCP; "Revisar clipes" como botão cheio em toda linha.
Detector: 0 achados nos alvos da 024; 4 side-tab fora do escopo (PromptPainel, Alertas, Calendario ×2), pré-existentes.
