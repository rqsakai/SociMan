# Architecture Decision Records (ADRs)

Registro das decisões de arquitetura tomadas no projeto e o **porquê** de cada
uma. Formato: Contexto / Decisão / Consequências / Status.

| # | Decisão | Status |
|---|---|---|
| [0001](0001-verificacao-email-obrigatoria.md) | Verificação de e-mail obrigatória para login | Aceita |
| [0002](0002-argon2id-hash-wasm.md) | Argon2id (hash-wasm) como hash default, PBKDF2 fallback | Aceita |
| [0003](0003-padrao-hibrido-cookieless.md) | Sessão híbrida cookieless (access memória + refresh cookie) | Aceita |
| [0004](0004-janela-graca-refresh.md) | Janela de graça de 60s na rotação de refresh | Aceita |
| [0005](0005-segredos-azion-variables.md) | Segredos em Azion Variables (não em function args) | Aceita |
| [0006](0006-email-byok.md) | E-mail BYOK (cliente traz a key e paga direto) | Aceita |
| [0007](0007-driver-rest-edge-sql.md) | Driver REST do Edge SQL na borda + inlining seguro | Aceita (com ressalva) |
| [0008](0008-kv-hibrido-borda.md) | KV híbrido na borda (Edge SQL hoje, AzionKV pronto) | Aceita (bloqueada na Azion) |
| [0009](0009-conectores-plugaveis.md) | Arquitetura de conectores plugáveis | Aceita |
| [0010](0010-monorepo-handlers-puros.md) | Monorepo + handlers puros (Request,deps)=>Response | Aceita |
| [0011](0011-waf-edge-firewall-counting.md) | WAF na borda em modo logging (flip manual para blocking) | Aceita |

Como as ressalvas de 0007/0008 dependem da Azion, o status de produção completo
está em [../../PRODUCTION.md](../../PRODUCTION.md).
