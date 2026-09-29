# ADR 0001 — Verificação de e-mail obrigatória para login

**Status:** Aceita

## Contexto

O brief (§12) deixa a verificação de e-mail como ponto de ajuste `[decisão]`:
default = obrigatória para login, com opção de relaxar para "login permitido mas
com flag `unverified`".

## Decisão

Adotar o default: **verificação obrigatória para login**. O cadastro abre sessão
imediatamente (para não travar o onboarding), mas um **novo login** exige e-mail
verificado, respondendo `403 email_not_verified` caso contrário.

A checagem vem **depois** da verificação de senha — dizer "verifique o e-mail" só
com a senha correta não abre enumeração de usuário.

## Consequências

- Contas não verificadas ficam com a sessão do cadastro, mas não conseguem
  re-logar até verificar.
- Para relaxar: remover o bloqueio em `handleLogin` e tratar a flag
  `emailVerified` na UI.
- Depende de um provider de e-mail funcional (ver [0006](0006-email-byok.md)).
