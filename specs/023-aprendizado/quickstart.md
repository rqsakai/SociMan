# Quickstart: validar o Aprendizado (023)

Roteiro de validação de ponta a ponta. A forma das rotas está em [contracts/http-api.md](contracts/http-api.md),
as regras em [data-model.md](data-model.md) e as fórmulas em [research.md](research.md) (R1–R4).

## 0. Pré-requisitos

- A stack de dev no ar: `docker compose up -d` e `curl http://localhost:8180/api/health` → `ok`.
- A migration aplicada: `docker compose exec api uv run alembic upgrade head`. A cabeça deve ser
  `0019_aprendizado_fonte_temas` (a 0018 e o cache de casamento do plano B do R9).
- O agendador reiniciado depois do código novo (`docker compose restart agendador`). O log mostra a trilha
  `aprendizado` ativa (ou ociosa sem `ANTHROPIC_API_KEY`).
- O HD montado com `.sociman-volume` (`./scripts/data-setup.sh check`), para a análise com quadros.
- Login como dono (e, no passo 6, também como membro).

## 1. Testes automatizados

```bash
npm run test:api -- tests/ -k "aprendizado or ia_prompt or constitution or mcp_mapa or migration_0018 or videos_fonte or analytics" -q
docker compose exec -T api uv run ruff check .
npm run gen:contract && npm run check:web
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/aprendizado.spec.ts e2e/cortes-openshorts.spec.ts e2e/assistente-ia.spec.ts e2e/guia-comunicacao.spec.ts e2e/analytics.spec.ts
```

**Esperado:** tudo verde, incluindo:
- os efeitos de referência (encolhimento, intervalo com semente, concentração, "não separável", blocos e
  travada), com SC-003 e SC-004;
- a recusa de membro e MCP em todas as rotas H (SC-006);
- a ordem do Descobrir idêntica à da 006 com afinidade neutra, e o aviso de direito intacto (SC-008);
- as 10 gerações com bloco de desempenho: fixas presentes, nenhuma "evitar" e versões no registro (SC-007);
- o desempenho: análise < 2 s com 10× o volume, e Descobrir ≤ +300 ms com 50 mil vídeos-fonte.

## 2. Temas e classificação (US1)

1. Em `/app/perfis/<Taverna>/aprendizado?aba=temas`, clicar em "Propor com IA". **Esperado:** de 3 a 15
   temas, com descrição e palavras-chave, e nada salvo.
2. Ajustar para 5 temas e "Salvar". **Esperado:** `taxonomiaVersao` = 1 e o histórico de cada tema.
3. Clicar em "Classificar pendentes" e aguardar a próxima volta da trilha (≤ 5 min, ou
   `docker compose logs -f agendador`). **Esperado:** os posts com ≥ 24 h ganham tema, estilo do gancho e
   justificativa, e o contador "usadas hoje / 50" sobe.
4. Corrigir o tema de 1 post. **Esperado:** `origem = dono`. Pedir "Classificar pendentes" de novo: o post
   corrigido não muda.
5. Juntar 2 temas e depois reverter. **Esperado:** as classificações vão e voltam, com histórico.

## 3. Análise e diagnóstico (US2, US5)

1. Abrir `?aba=analise` com a medida de 24 h. **Esperado:**
   - as duas contas aparecem como "distribuição travada", porque a maioria tem 0–2 views;
   - a parte "rendimento" aparece como indício;
   - as hashtags #multiversomarvel, #vingadoresdoomsday e #geek aparecem num bloco ou como "não separável
     do tema Marvel/MCU";
   - todo número mostra n de posts e de dias.
2. Abrir `?aba=diagnostico`. **Esperado:** sinais com número (conta nova, posts no mesmo dia, repostagem)
   e o checklist. Marcar "conferi: não estava restrito" num post e ver o histórico.

## 4. Análise da IA (US2, Clarification 1)

1. Em `?aba=ia`, pedir a análise dos 8 melhores. **Esperado:** a estimativa com e sem quadros, e o botão
   "Confirmar custo".
2. Confirmar com quadros. **Esperado:**
   - `pendente → processando → pronta` em até 2 min;
   - as hipóteses citam posts reais, com link, n e "a conferir";
   - a chamada aparece no registro do assistente com a finalidade `aprendizado.analise` e o custo;
   - `work/tmp/aprendizado/` fica vazio depois.
3. Transformar uma hipótese em "padrão de gancho". **Esperado:** ela aparece em Recomendações como
   aberta.

## 5. Recomendações e ciclo (US3, US4)

1. Em `?aba=recomendacoes`, aceitar "ampliar <tema>" e "fixar <hashtag>" (se houver, porque com as contas
   travadas pode não haver nenhuma; nesse caso, usar a recomendação de hipótese do passo 4). Rejeitar
   outra com motivo. **Esperado:**
   - as preferências ficam na v1;
   - a hashtag entra no guia da conta, com a origem "recomendação 023" no histórico do guia;
   - a rejeitada some.
2. No Descobrir, com o perfil escolhido. **Esperado:**
   - vídeos do tema ampliado sobem, com o motivo "Tema …";
   - com um tema marcado "cortar" nas preferências, aparece "N ocultos por tema cortado", e o interruptor
     "mostrar temas cortados" os traz com o selo;
   - um vídeo `sem_acordo` continua com o aviso ao enviar para corte.
3. Gerar "Sugerir textos" de uma postagem da conta. **Esperado:** no registro, "Desempenho: perfil v1,
   conta v0, N exemplos"; as fixas estão presentes, e a "evitar" é removida com aviso.
4. Desligar "usar desempenho no assistente" e gerar de novo. **Esperado:** "sem bloco de desempenho".

## 6. Permissões e custo (US6)

- Como membro: abrir as 5 abas. **Esperado:** tudo visível, sem nenhum botão de escrita, sem custo e sem
  "Pedir análise".
- Como dono: o resumo do mês do assistente mostra `aprendizado.taxonomia`, `.classificacao` e `.analise`
  separados.

## 7. Real com o dono (manual)

O passo 2 a 5 com as contas reais (@atavernanerd e @meusqueridinhos10). Registrar:
- quantas classificações o dono corrigiu de 20 (SC-002);
- se a leitura "distribuição travada" faz sentido para ele;
- o custo real de uma análise com quadros.

**Commit só quando o dono pedir.**
