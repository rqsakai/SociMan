# ADR 0011 — WAF na borda em modo logging (flip manual para blocking)

**Status:** Aceita

## Contexto

O app tem app-layer rate limit ([0008](0008-kv-hibrido-borda.md)) e CSP estrita
([security.md](../architecture/security.md)), mas nada inspecionava o **payload**
dos requests em `/api/*`. Sem WAF, tentativas de SQL injection, XSS, RFI, LFI e
similares chegam intactas na function e viram trabalho de Zod + queries
parametrizadas — que já protegem, mas custam CPU e não deixam rastro de
tentativa. Também não havia proteção baseline de DDoS L7 no edge.

A Azion oferece Edge Firewall (`azion_firewall_main_setting`) com módulos WAF,
DDoS protection e network protection, ligados ao workload via
`workload_deployment.strategy.attributes.firewall`.

## Decisão

- **Firewall provisionado via Terraform** (`infra/azion/firewall.tf`) com WAF +
  DDoS + network_protection habilitados, bindado ao workload.
- **WAF cobre as 8 ameaças** do engine `2021-Q3` (sql_injection,
  cross_site_scripting, remote_file_inclusion, directory_traversal,
  evading_tricks, file_upload, unwanted_access, identified_attack) em
  sensibilidade `medium` — o meio-termo entre false-positive (`highest`
  bloqueia senha com `--`) e cobertura fraca (`low`).
- **Aplicado só em `/api/*`** via `firewall_rule_engine` (behavior `set_waf`).
  Assets estáticos não passam por WAF — é CPU desperdiçada e não é superfície
  de ataque.
- **Modo default `logging`** (`var.waf_mode`): WAF inspeciona e loga em
  Real-Time Events, **não bloqueia**. Flip para `blocking` só após janela de
  observação (~1 semana em produção), via:
  `terraform apply -var waf_mode=blocking`

## Consequências

- **Zero risco de derrubar login legítimo no dia 1.** O custo é que ataques
  também passam no primeiro momento — aceitável porque as camadas de app (Zod,
  queries parametrizadas, argon2id) já defendem.
- **Ação humana obrigatória** pra virar `blocking`: revisar RTE, mapear
  false-positives, baixar sensibilidade de threats que ruidam demais (ex.:
  `sql_injection` costuma bater em senhas com aspa) — só então flipar. Sem
  essa etapa, `logging` é um placebo.
- **Edge rate limit fica pra depois.** A infra tá pronta (behavior
  `set_rate_limit` no firewall_rule_engine) mas exige threshold empírico
  (quantos req/s um usuário legítimo faz em `/api/auth/*`?) — só dá pra
  calibrar após observar tráfego real.
- **Custo:** WAF é medido por request na Azion. Como só `/api/*` passa (não
  assets), o volume é baixo — a SPA hidrata sem tocar API na maior parte da
  navegação.
