# Changelog do sociman-coletor

Formato: versão do pacote (semver, enviada em `X-Sociman-Coletor-Versao`), protocolo com a API
(`X-Sociman-Coleta-Protocolo`) e esquema do adaptador (`esquemaVersao` de cada item).

## 0.1.0 — 2026-10-09

- Primeira versão (spec 026, User Story 2). Protocolo `1`.
- Adaptador `tiktok_shop/1`: parsers de `produto`, `ranking`, `categorias`, `vitrine`, `loja`,
  `avaliacoes` e `produto_videos` no formato de `contracts/coletor.md`; `busca_assunto` e `video`
  (reservados para a 027) respondem `tipo_desconhecido`.
- `INTERCEPTAR` **vazia de valores reais** até a sonda guiada com o dono (quickstart §2). Os nomes
  de chave dos parsers são um formato de referência e serão ajustados pela sonda; as regras e o
  formato de saída não mudam.
- CLI: `rodar`, `uma-vez`, `dry-run`, `autoteste`, `perfil-iniciar`, `parar`, `reprocessar`, `--versao`.
- Ritmo humano, janela no fuso do servidor, sinais (captcha, login, bloqueio, layout), poda de
  dados pessoais, imagens baixadas dentro do navegador, logs sem dado pessoal.
