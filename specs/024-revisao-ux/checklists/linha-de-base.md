# Linha de base da 024 (2026-10-07)

- Commit de partida: `efc18bf` (spec 021), árvore limpa fora de `.impeccable/` e `specs/024-revisao-ux/`.
- `npm run check:web`: verde (contrato, typecheck, build, bundle, CSP, segredos).
- e2e: última suíte completa verde em 2026-10-06 (84 testes, antes da 021); a suíte completa da 024 roda no fim (T073) e as falhas novas são comparadas com esta referência.

## Verificação final (2026-10-08, código congelado)
- T072: `gen:contract` ok; `check:web` verde (contrato, typecheck, build, PWA, bundle, CSP, segredos); ruff limpo.
- T073:
  - `npm run test:api`: **3172 passed** (inclui o p95 de `test_escala_conteudos`, que tinha falhado por carga).
  - `npm run test:e2e`: 95 passed, 2 failed na rodada completa:
    - `metricas.spec.ts:772` (timeout no login do membro): passou na segunda rodada;
    - `guia-comunicacao.spec.ts:184`: falhou em pontos diferentes quando rodou junto com `metricas.spec.ts`; passou isolado e com o arquivo inteiro (3/3). Instável sob paralelismo, sem relação com a 024 (a página só ganhou o `<Page>`). Fica como pendência de estabilidade dos testes.
  - `npm run test:e2e:pwa`: 9/10 → corrigido `e2e-pwa/offline.spec.ts` (usa `nav()`, porque "Usuários" e "Segurança" ficam no grupo Configurações) → **10/10**.
- Achado fora da 024: refresh concorrente de várias abas derrubou a sessão do dono no dev (`POST /api/auth/refresh` 200 seguido de 401). Investigar à parte (rotação do refresh + carência de 10 s da correção de logout).
- T074/T075: critique final dual-agent → **30/40, sem P0** (base 24/40), registrado em `.impeccable/critique/2026-10-08T13-01-38Z__apps-web-src-pages.md`. Corrigidos na rodada: P1 contraste do botão de faixa no tema escuro (variante `band` do `Button`) e P2 item ativo do menu fora da dobra. Depois disso: `check:web` verde, e2e layout + layout-ritmo + cortes-openshorts 11/11, PWA 10/10. Capturas a 1920 px (o `resize_window` não muda a janela); 1280/390 cobertos pelo `layout-ritmo.spec.ts`.
