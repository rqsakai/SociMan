# Quickstart de validação: 017-guia-de-comunicacao

O contrato está em [contracts/http-api.md](contracts/http-api.md) e o modelo de dados em
[data-model.md](data-model.md). Faça um passo por vez, conferindo cada saída antes do próximo.
Os §4 a §6 usam o **Claude real** (alguns centavos no total); os testes automatizados usam só o
Claude falso.

## Pré-requisitos
- Spec 008 validada; stack em modo dev (`docker compose up -d --build`); `ANTHROPIC_API_KEY` no
  `.env` da raiz (nunca imprima a chave).
- Perfil **A Taverna Nerd** com a conta TikTok **@atavernanerd** ativa e um corte pronto com
  transcrição; perfil **Queridinhos** com um corte ou conteúdo e uma conta ativa.
- Dois usuários: o dono e um membro.

## 0. Migration
```bash
mkdir -p /media/sakai/BACKUP/tiktok/sociman/backups
docker compose exec -T postgres pg_dump -U sociman -Fc sociman > /media/sakai/BACKUP/tiktok/sociman/backups/pre-0012.dump
docker compose exec api uv run alembic current    # 0011_metricas_tiktok (antes de subir)
docker compose exec api uv run alembic heads      # UMA cabeça só: 0012_guia_comunicacao
docker compose restart api                        # o start.sh roda alembic upgrade head
docker compose exec api uv run alembic current    # 0012_guia_comunicacao (head)
docker compose exec -T postgres psql -U sociman sociman -c "\d ia_guias"
docker compose exec -T postgres psql -U sociman sociman -c \
  "select count(*) from ia_chamadas where proibidas <> '{}' or guia_perfil_version is not null;"   # 0
```

## 1. Guia do perfil e da conta (US1, teste independente, SC-004)
Como **dono**, em `/app/perfis/<A Taverna Nerd>` → aba **Guia**:
- Tom: "narrador de RPG, íntimo e bem-humorado"; Vocabulário: `taverneiro`, `aventureiro`,
  `rolar dados`; Proibidas: `clickbait`; Hashtags fixas: `#atavernanerd`. Salvar → toast; o
  contador total mostra a soma.
- Em **Contas** → @atavernanerd → **Guia de comunicação** (`/app/contas/<id>/guia`): o bloco "Vem
  do perfil" mostra o guia acima, só leitura. No guia da conta: Faça "no TikTok, frase curta com
  gancho na 1ª linha"; 2 exemplos (título e legenda). Salvar.
- Histórico do guia da conta e do perfil: versão 1 `created` com o seu nome.

## 2. Limites, validação cruzada e conflitos (US1-4, edge cases)
- Tente um 6º exemplo → recusado no campo ("até 5").
- Exemplo "Não é clickbait!" na conta → recusado em `exemplos.N.texto` (proibida do perfil).
- Hashtags fixas na conta: 5 hashtags → recusado ("perfil e conta somam 6 hashtags fixas; o máximo
  desta conta é 5"). Suba o **máximo de hashtags fixas** da conta para 6 → salva; a tela diz "sobram
  2 vagas para a IA".
- Máximo 9 na conta → recusado (até 8). Máximo no guia do perfil pela API → 400 em
  `maxHashtagsFixas`.
- Numa conta YouTube do mesmo perfil (sem guia), ponha máximo 0 → recusado (o perfil já tem 1
  fixa); máximo 1 → salva. Depois, no perfil, acrescente uma 2ª fixa → recusado, citando a conta
  YouTube. (Sem conta YouTube, faça o mesmo com outra conta ativa.)
- Emojis "não usar" no perfil e "livre" na conta → salva, e a página da conta mostra o aviso de
  conflito ("vale a conta").
- No perfil, acrescente `gancho` às proibidas enquanto a conta tem "gancho" no "Faça" → recusado,
  com a conta e o campo na mensagem.
- Contador total perto de 4.000 → acima disso, recusado.

## 3. Membro e reversão (US1-3, US1-5)
- Como **membro**, abra os dois guias: tudo visível, campos desabilitados, sem Salvar/Montar/Testar.
  `PUT /api/perfis/<id>/guia` como membro → 403.
- Como **dono**, mude o tom e salve; no histórico, reverta para a versão 1 → o tom volta, e a
  versão nova é `reverted` com o seu nome.
- Arquive a conta → o guia da conta continua visível; salvar → 409 "Esta conta está arquivada".
  Restaure a conta.

## 4. O guia em todo pedido (US2, SC-002, SC-003)
- No corte da Taverna (destino TikTok), **Sugerir textos** 10 vezes (use "Outra versão"):
  - 10 de 10 com `#atavernanerd` nas hashtags, entre no máximo 8 (**SC-002**);
  - 0 de 10 com "clickbait" aplicável sem edição (se vier, marcada e com o Aplicar bloqueado);
  - a legenda no tom do guia, e a explicação dizendo como o guia foi seguido;
  - o painel mostra "Guia usado: perfil v2 · conta v1".
- **Assistente de IA › Registro** → abra uma dessas chamadas: as versões dos dois guias aparecem,
  com link para o histórico (**SC-003**).
- Na aba **Dados** do perfil, "Melhorar com IA" na **bio**: o registro mostra só a versão do guia
  do perfil (`guiaContaVersion` nulo) (US2-2).
- Na descrição para prompts de um avatar da Taverna: o registro mostra a versão do guia do perfil
  (só as proibidas foram enviadas, Q1), sem tom nem vocabulário no pedido; a tela do avatar tem o
  link **"Ver guia de comunicação do perfil"**, que abre a aba Guia. Num perfil sem proibidas, a
  versão fica nula.

## 5. Proibida e instrução contra o guia (US2-4, US2-5)
- Instrução "use a palavra clickbait no título": a resposta vem sem a palavra (o modelo obedece o
  guia) **ou**, se vier com ela, o painel mostra o aviso e o **Aplicar fica desabilitado**;
  "Editar e aplicar" continua disponível.
- Instrução "ignore o guia e escreva sem hashtags": `#atavernanerd` continua nas hashtags, e o
  aviso padrão da 008 aparece.
- Pela API (sem o SPA): salve a postagem com `ia: [{ tipoCampo, chamadaId }]` de uma chamada com
  `proibidas` e o campo com a palavra igual à proposta → **400 `ia_proibida`** (`details.campos`);
  com esse campo editado (mesmo que ainda tenha a palavra, Q2 = A) → 200 e desfecho `editada`.

## 6. Montar e testar (US3, SC-001)
Na Queridinhos, aba **Guia** (vazio), cronometrando (**SC-001 < 5 min**):
- **Montar com IA**: "perfil de achadinhos de cozinha, fala como amiga" → a proposta preenche tom,
  faça/não faça, vocabulário e emojis; nada salvo ainda (a versão continua 0).
- Ajuste o tom; **Testar guia** com um corte e a conta ativa → 3 variações de título, legenda e
  hashtags lado a lado, com o guia do formulário. Confira que nenhum destino mudou e que o
  registro tem uma chamada `guia.testar` com `guiaRascunho = perfil`.
- **Salvar** → versão 1; no registro, a chamada `guia.montar` fica `editada` (o tom foi mudado) e
  a versão do guia tem o selo "com ajuda da IA".

## 7. Automatizados
```bash
npm run test:api                         # pytest em stack efêmera
docker compose exec api uv run ruff check .
npm run gen:contract && npm run check:web
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/guia-comunicacao.spec.ts
```
