# Quickstart: validar o Analytics (019)

Roteiro de validação de ponta a ponta. Os detalhes de forma estão em
[contracts/http-api.md](contracts/http-api.md) e as regras de cálculo em [data-model.md](data-model.md).

## 0. Pré-requisitos

- Stack de dev no ar: `docker compose up -d` e `curl http://localhost:8180/api/health` → `ok`.
- Pelo menos uma conta da TikTok conectada com métricas (016) e alguns vídeos vinculados.
- Logado como dono (e, para o passo 6, também como membro).

## 1. Testes automatizados

```bash
npm run test:api -- tests/ -k "analytics or metricas or constitution" -q   # stack efêmera
docker compose exec -T api uv run ruff check .
npm run gen:contract && npm run check:web      # contrato, tipos, build, CSP, bundle
flock /tmp/sociman-e2e.lock npm run test:e2e -- e2e/analytics.spec.ts e2e/metricas.spec.ts
```

**Esperado:** tudo verde. O pytest inclui:
- cálculo de referência de cada aba sobre dados semeados (SC-002);
- o teste de desempenho com 10× o volume (cada aba < 2 s, SC-003);
- os guardas: rotas só GET, nada de import de `publicacao` ou de serviços de escrita.

## 2. Carregamento sob demanda (SC-004)

1. Com o build de produção (`npm run casa:up`) ou o preview, abra o DevTools → Network e entre em
   `/app/conteudos`. **Esperado:** nenhum chunk de gráficos baixado.
2. Entre em `/app/metricas`. **Esperado:** o chunk do analytics (com o ECharts) é baixado só agora.
3. Console sem erros de CSP (`Refused to evaluate…`/`Refused to execute inline script`).

## 3. Visão geral e período (US1, FR-002, FR-012)

1. Abra `/app/metricas`. **Esperado:**
   - o período vem nos últimos 7 dias;
   - os 6 indicadores mostram o valor anterior e ▲/▼;
   - a série diária por conta e o top 10 com miniatura e título curto aparecem.
2. Troque para 30 dias e volte no navegador. **Esperado:** a URL guarda `?de&ate`, e voltar restaura o
   período.
3. Escolha um período anterior à primeira coleta. **Esperado:** "sem base de comparação" e estados
   vazios com "ampliar período".
4. Confira 1 indicador contra o banco (soma dos ganhos de views no período) com `psql` somente leitura.

## 4. Quando postar (US2)

1. **Esperado:**
   - o mapa por publicação mostra o n em cada célula, e células com n < 5 aparecem como amostra pequena;
   - o mapa da audiência tem a nota de fuso e o total "sem hora atribuída";
   - o calendário mostra posts e views por dia.
2. Troque a medida para 1 h. **Esperado:** os valores mudam e o contador "aguardando" cai.

## 5. O que funciona, curvas, contas, funil, mercado e alertas (US3–US8)

- **O que funciona:** as dispersões só mostram a correlação com n ≥ 8, e clicar num ponto abre
  `/app/metricas/videos/:id`; o lift de hashtags só aparece com n ≥ 5; aparece "N vídeos fora do SociMan
  excluídos".
- **Curvas:** destacar um vídeo deixa os outros em cinza; um vídeo com menos de 7 dias mostra "ainda
  não calculável".
- **Contas:** com 1 conta, o radar mostra "precisa de pelo menos 2 contas"; clicar numa conta aplica o
  filtro e mostra a trilha.
- **Funil:** cada etapa tem n e %, e o tooltip mostra as perdas; mudar o patamar recalcula a última etapa.
- **Mercado:** em oportunidades aparecem o status de direito e "Gerar cortes". Clicar leva à seleção, e
  o aviso de direito aparece para um canal `sem_acordo`.
- **Alertas:** os vídeos com 0–1 view depois de 6 h (como os de 30/09) aparecem como "estagnado", com o
  que conferir no app.

## 6. Permissões (FR-010)

Entre como membro. **Esperado:**
- o funil não mostra custo de IA;
- a resposta de `/api/analytics/funil` traz `custoIaUsd: null`;
- não há "Exportar dataset";
- o CSV de cada card continua disponível.

## 7. Acessibilidade, tema e celular (FR-005, FR-006, FR-008, SC-005, SC-006)

1. Em cada card:
   - "Ver tabela" mostra os dados;
   - "CSV" baixa o mesmo conteúdo da tabela;
   - o texto "Como ler" está presente.
2. Alterne entre os temas claro e escuro pelo menu da conta. **Esperado:** as cores dos gráficos mudam
   sem recarregar a página, e cada conta mantém a mesma cor nos dois temas.
3. DevTools com 390 px de largura. **Esperado:** sem rolagem horizontal da página; os mapas de calor
   rolam dentro do card; as views ficam visíveis nas tabelas.

## 8. Só leitura (FR-009)

Com o Network aberto, navegue por todas as abas. **Esperado:** só requisições `GET /api/analytics/*`
(além das de sessão), e nenhum `POST`, `PATCH` ou `PUT`.
