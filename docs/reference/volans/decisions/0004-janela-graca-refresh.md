# ADR 0004 — Janela de graça de 60s na rotação de refresh

**Status:** Aceita

## Contexto

O refresh token rotaciona a cada uso e detecta reuso (token já rotacionado
apresentado com a família viva → revoga a família inteira). Sem cuidado, isso
derruba **usuários legítimos**: uma navegação que aborta a resposta do refresh
(o `Set-Cookie` novo se perde) deixa o browser com o token antigo, e o próximo
load é tratado como "ataque". Bug real pego pelo e2e no deploy.

## Decisão

Aceitar o token da **geração imediatamente anterior** por uma janela de graça
(`REFRESH_GRACE`, default **60s**) após a rotação. Tokens de 2+ gerações atrás,
ou fora da janela, continuam **revogando a família inteira**. `REFRESH_GRACE=0`
volta ao modo estrito.

## Consequências

- Cobre os casos comuns (multi-tab, resposta perdida) sem derrubar o usuário.
- Trade-off: um replay dentro da janela de 60s é possível — aceitável e
  documentado; a detecção pega tudo fora dela.
- A rotação não é transacional no KV (get→set): há uma race residual rara que,
  no pior caso, força re-login (não vaza sessão). Solução robusta = CAS/Lua no KV.
- Coberto por teste unit, integração e e2e.
