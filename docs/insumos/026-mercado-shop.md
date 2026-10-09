# Insumo: 026-mercado-shop (cockpit do TikTok Shop: coletor, lago de produtos e indicadores)

Entrada para o `/speckit-specify`. Resultado do brainstorm de 2026-10-08 com o dono. Abre uma sequência de
três specs: **026** (coletor + ingestão + lago de produtos + cockpit), **027** (vídeos virais por assunto e
nicho) e **028** (recomendações da IA e alertas). Este arquivo detalha a 026 e esboça as outras duas.
Pesquisa de fontes de referência: `../../shared/shop/fontes-dados.md` (2026-09-24, com adendo de
2026-10-08). Mecânica de referência: `../../tools/tiktok_agendar.py` (Chrome real + interceptação da API
interna). Exige **emenda da constitution** (princípio IX) antes de qualquer código.

## Problema
O SociMan já cobre contas, kit, cortes, conteúdos, publicação, métricas das próprias contas, analytics,
aprendizado e geração local. Falta a **inteligência de mercado**: o que vende no TikTok Shop (GMV estimado,
ritmo de vendas, produtos novos subindo, alto retorno com poucos afiliados), por categoria/nicho do perfil e
por mercado (país), mais o que viraliza por assunto e as recomendações da IA em cima disso. Hoje é manual: o
dono cola JSON de produtos e o `shop-analista` busca no YouTube e na web, "sem números de venda".

**Não existe API oficial de mercado.** Research API e Commercial Content API são só para pesquisa
acadêmica; o Creative Center tirou "Top Products" do público em 2026; Kalodata, FastMoss e EchoTik vivem de
scraping em escala (Kalodata admite na FAQ). A única via oficial e grátis é a Affiliate Creator API do
Partner Center (Brasil não confirmado, sem dado de concorrente): fica como **sonda** da 026.

## Decisões do dono (2026-10-08)
1. **Coleta própria** ("o Kalodata dentro do SociMan"): um robô assíncrono que navega como pessoa. Nenhuma
   ferramenta paga como base; FastMoss/EchoTik ficam como plano B.
2. **Conta e navegador:** a **própria conta de afiliado do dono**, num **único perfil de Chrome, logado
   sempre** (o dono recusou um perfil público separado). O robô roda no **Chrome real do desktop**, por um
   serviço no host (systemd de usuário), via CDP em loopback, 1 aba, modo visível. **Risco assumido pelo
   dono:** a TikTok pode restringir a conta que fatura (a pesquisa de 2026-09-24 recomendava não raspar
   logado). O aceite fica registrado na tela, em `coleta_config.risco_aceito_em` e em
   `docs/decisoes/coleta-mercado.md`.
3. **O dado entra por uma API de ingestão com token** (`scol_…`); o coletor nunca escreve no Postgres.
4. **Região = mercado (país):** dimensão `mercado` em toda tabela do lago desde o dia 1; só `BR` agora. Outro
   país exige outra conta e outro perfil de Chrome (o `mercado` acompanha o cliente de coleta). Região dentro
   do Brasil só para o público próprio (spec 022).
5. **Lista acompanhada:** rankings do Affiliate Center nas categorias do nicho de cada perfil; produtos que
   aparecem em vídeos virais (027); lista manual por link; produtos que o dono já promove (vitrine, que vale
   para **todos os perfis**); produtos novos da mesma linha/loja/categoria dos que as contas já vendem
   (criados por `system:mercado`, com limite diário e aviso).
6. **Ritmo humano:** ~300 páginas/dia, janela 08h-23h, pausas aleatórias de 5 a 40 s, rolagem e mouse. Os
   padrões vêm do servidor; o coletor aplica o menor entre o seu limite local e o do servidor.
7. **Cadência:** quentes (novos em alta) e manuais: **2 fotos/dia** (manhã e noite). Demais: 1/dia; fora do
   ranking há 7 dias: 1/semana; 30 dias sem interesse: para de coletar. Manual e vitrine nunca esfriam.
   **Nada é apagado, nunca:** esfriar só muda a frequência. A limpeza de 90 dias da 021 não se aplica.
8. **Data lake multi-conta:** o dado de mercado é **global e permanente**, sem `perfil_id` nas tabelas do
   lago. Perfis e contas só registram **interesse** (acompanhamentos, categorias do nicho). Todos leem o
   mesmo histórico.
9. **Multi-tenant em breve (spec própria):** a camada de mercado é neutra de tenant (coletada uma vez, lida
   por todos); a camada de interesse, perfis e contas é a que ganhará `tenant_id`. Hoje todo usuário lê toda
   entidade (padrão do repo); a spec de multi-tenant introduz a checagem de acesso por tenant nas leituras.
10. **Ficha completa:** coletar tudo o que a página expõe (fotos originais, título, descrição, atributos,
    variantes com SKU/preço/estoque visível, argumentos de venda, loja, categoria L1→L3, nota e avaliações,
    selos) e guardar o **payload bruto** para reprocessar quando o layout mudar.
11. **Vídeos top por produto** já entram na 026 como prioridade baixa (a tabela nasce populada); a 027 traz a
    busca por assunto.
12. **Vínculo com a 012 agora:** `produtos.mercado_produto_id` (nulo) e a ação humana "Adotar do mercado",
    que copia ficha e fotos para o catálogo do perfil.
    **Nota (029, 2026-10-09):** com a biblioteca da agência, "Adotar" cria o produto com o perfil base escolhido
    (ou nenhum); o catálogo deixa de ser "do perfil".

## Cartão mínimo do produto (exemplo real do dono)
| Campo | Origem |
|---|---|
| Preço | foto diária (página do produto) |
| Comissão % | foto diária (Affiliate Center) |
| Comissão por venda | calculado: % × preço (a TikTok desconta cupons; marcar "estimado") |
| Loja + selo "Loja oficial" | ficha |
| Vendas (período) | Σ dos deltas diários de "vendidos" no filtro `de/ate` |
| GMV (período) | Σ (delta diário × preço do dia), "estimado" |
| Crescimento | vendas do período ÷ período anterior − 1 |
| Vendas totais | última foto ("vendidos" acumulado) |
| GMV total | vendas totais × preço atual (grosseiro, "estimado") |
| Projeção de lucro (10/100/1000 vendas) | no cliente: comissão por venda × N |

Período e crescimento só existem a partir da 2ª foto e ficam confiáveis com ~7 dias; antes disso o cartão
mostra "coletando" (padrão "amostra pequena" da 019).

## Catálogo de dados e indicadores
**Bruto coletável.** Produto: título, descrição, atributos, fotos, variantes, preço de lista × desconto,
cupons/selos, categoria L1→L3, "vendidos" acumulado, nota, nº e texto das avaliações, relacionados. Loja:
nome, selo oficial, nota, seguidores, tempo de resposta, envio no prazo, nº de produtos, vendidos total,
catálogo. Affiliate Center: comissão %, nº de criadores promovendo, plano aberto/direcionado, amostra grátis,
posição nos rankings, vídeos top (id, @ público, views, legenda), lives. Já no SociMan: métricas próprias
(016), público (022), temas e afinidade (023), YouTube (006).

**Derivado na 026.** Produto: vendas/dia e GMV/dia, média móvel 7 d, aceleração; idade e curva de vida
(lançamento, subida, platô, queda); "novo em alta"; comissão por venda; **retorno por afiliado** =
vendas/dia × comissão ÷ (criadores + K); saturação = criadores ÷ vendas/dia; elasticidade de preço; sinal de
estoque; taxa de avaliação (reviews/dia ÷ vendas/dia; anomalia indica review comprado). Loja: GMV estimado,
concentração no produto nº 1, ritmo de lançamentos, confiabilidade, comissão média ("loja boa para
parceria"). Categoria: medianas de comissão e preço, nº em alta, sazonalidade, **espaço em branco**
(subcategoria crescendo com poucos criadores).

**Cruzamento (027/028).** Fit com o público (022) e os temas (023); você contra a mediana dos criadores do
produto; padrões dos vídeos top (gancho, formato); mineração das avaliações pela IA (dores, objeções,
argumentos reais).

**Decisões que alimenta.** O que gravar esta semana; vale a pena este produto; que argumento usar; quando
postar; que loja procurar para amostra ou parceria; o que largar; onde ninguém está olhando; estou bem ou mal
neste produto.

**Alertas (028).** Comissão mudou; preço caiu mais de 15%; estoque esgotou; produto novo em loja acompanhada;
produto promovido em queda; concorrente com poucos afiliados subiu 3 dias seguidos.

**Não existe (não prometer).** Vendas por estado, conversão real, GMV exato (tudo é estimado pelo
"vendidos") e identidade dos compradores.

## Arquitetura da 026

### Componentes
1. **`apps/coletor/`** (host, fora do Docker; pacote `sociman_coletor`, Python 3.12 + uv, `pyproject`
   próprio; dependências só `playwright` para `connect_over_cdp`, `httpx` e `pydantic`). Lança o Chrome do
   sistema com `--user-data-dir=~/.config/sociman-coletor/chrome-profile` e `--remote-debugging-port=0`
   (porta lida de `DevToolsActivePort`, só loopback), visível, pt-BR, sem flags de automação; 1 aba; `flock`
   no perfil. Lê as páginas como pessoa e intercepta as respostas da API interna (lista fechada `INTERCEPTAR`
   em `redes/tiktok_shop.py`); o DOM é só reserva. **Nunca** reproduz a chamada assinada, **nunca** escreve na
   rede (seguir, curtir, comentar, vitrine, comprar); cliques só em `navegacao.py`, dentro de
   `CLIQUES_PERMITIDOS` (guarda AST). Baixa as imagens dentro do contexto do navegador e envia por multipart.
   Módulos: `main.py` (CLI `rodar | uma-vez --limite N | dry-run | autoteste | perfil-iniciar | parar`),
   `config.py`, `api.py`, `navegador.py`, `ritmo.py` (puro, RNG semeado), `janela.py`, `sinais.py` (captcha,
   login perdido, bloqueio, layout), `privacidade.py` (poda chaves pessoais do bruto), `redes/base.py`
   (Protocol `ColetorRede`), `redes/tiktok_shop.py`, `navegacao.py`, `log.py` (sem dado pessoal). Unidade
   `systemd/sociman-coletor.service` de usuário; precisa da sessão gráfica (sem fallback headless: tela
   bloqueada = não coleta).
   **Kill switch em 3 níveis:** `COLETA_HABILITADA` **e** o botão da tela (que exige aceite de risco
   registrado) esvaziam a fila; o arquivo `~/.config/sociman-coletor/PARAR` para na hora; `systemctl --user
   stop`. Captcha ou login perdido → evento → sino → pausa com o Chrome aberto para o dono resolver;
   `CAPTCHA_ESPERA_MAX = 2 h`; `PARSES_VAZIOS_MAX = 5` → `layout_mudou` e recuo de 24 h; 429/403 em série →
   `bloqueio_suspeito` e recuo de 24 h. Depois de captcha ou login, o dono clica **"Continuar"** na tela
   do coletor (`POST /api/coleta/config/continuar`, só dono humano) e o robô espera `CAPTCHA_ESFRIAR_MIN = 60`
   antes de voltar.
   **Orçamento:** as imagens têm teto próprio (`ORCAMENTO_IMAGENS_DIA = 1500`, `IMAGENS_POR_PRODUTO_MAX = 9`,
   originais sem redimensionar) e não contam como página. Estimativa: 300 páginas ≈ 25 rankings + 200
   produtos quentes + 40 primeiras visitas + 35 lojas/vídeos/avaliações; ≈ 100 MB/dia de imagens + 90 MB/dia
   de bruto gzip, ≈ 70 GB/ano no HD (2,1 TB).
   **Reprocessamento:** os parsers moram no coletor; quando o layout muda, `sociman-coletor reprocessar
   --desde <data>` baixa o bruto (`GET /api/coleta/coletas/{id}/bruto`, link assinado) e reenvia os campos
   com `reprocessadoDe`; a ingestão só preenche o que faltava (o trigger impede UPDATE).
2. **Pacote `mercado/`** na API (lago, leitura e interesse; sem HTTP): `models.py`, `mercados.py` (dimensão
   em código: `BR` = fuso + moeda), `constantes.py`, `fontes/base.py` (Protocol `FonteMercado.normalizar`),
   `fontes/tiktok_shop.py`, `fontes/registro.py` (único importador), `cadencia.py` (puro), `fila.py`
   (calculada na leitura, com lease), `ingestao.py` (`INSERT … ON CONFLICT DO NOTHING`), `interesses.py`
   (history), `consulta.py` e `calculo.py` (puro), `filtros.py`, `trilha.py`, `schemas.py`, `router.py`.
   **Pacote `coleta/`** (ingestão, clientes e portão): `models.py`, `credenciais.py` (cópia de
   `mcp/credenciais.py` com o prefixo `scol_`), `portao.py` (dependência global), `service.py`, `router.py`.
   Toques fora dos pacotes: `produtos/models.py` (+`mercado_produto_id`, versionado), `notificacoes/models.py`
   (+`coleta_captcha | coleta_login | coleta_layout | coleta_parada | mercado_novo_em_alta`),
   `integracoes.py` (bloco `coleta`), `agendador.py` (trilha `mercado`), `config.py`, `mcp/mapa.py`,
   `main.py`, `auth/deps.py` (`RequireColetor`), `storage.py` (bucket `mercado`),
   `scripts/check-secrets.mjs` (padrão `scol_`) e o edge (`location` multipart da ingestão).
3. **SPA:** o grupo Analytics do menu ganha "Mercado de produtos" → `/app/mercado`
   (`?aba=cockpit|produtos|rankings|lojas|acompanhamentos`, `FilterBar` + `useFiltroUrl("mercado")`, cards com
   "Ver tabela" e CSV, ECharts no chunk `graficos`); `/app/mercado/produtos/:id` (ficha, galeria, série,
   rankings, vídeos, avaliações, "Acompanhar neste perfil", "Adotar no catálogo"); aba `?aba=mercado` do
   perfil (categorias do nicho e acompanhamentos); `/app/configuracoes/coleta` (só dono: aceite de risco,
   interruptor, janelas, limites, "Pausar N h", tokens mostrados 1 vez, rodadas, eventos, guia de instalação).
   A aba "Mercado" de `/app/metricas` (YouTube de origem) continua como está.
4. **Trilha `mercado`** do agendador (`AGENDADOR_MERCADO_S`, 300 a 900 s, autor `system:mercado`): recalcula
   calor e próxima coleta; monta a fila do dia (idempotente por `(tipo, chave, data_local)`, com prioridade e
   orçamento); cria interesses `relacionado` (produtos novos das lojas e categorias dos acompanhados,
   `MAX_RELACIONADOS_DIA = 10`); devolve leases vencidos; marca a rodada sem batimento há 10 min; avisa
   `coleta_parada` após 48 h sem resultado. Nenhum DELETE.

### Contrato da ingestão (`/api/coleta/*`, operationId `coleta_*`, cabeçalho `X-Sociman-Coleta-Protocolo: 1`)
- `GET /api/coleta/fila?limite=50` → `{habilitada, pausadaAte, janelas, limites: {paginasDia, itensPorColeta,
  intervaloMinS, intervaloMaxS}, orcamentoRestanteHoje, tarefas: [{tarefaId, tipo, rede, mercado, fonte, chave,
  prioridade, prazoEm}]}`; marca o lease. Tipos: `produto` (página pública e/ou Affiliate Center), `ranking`
  (categoria × tipo × janela), `categorias` (semanal), `vitrine` (diária), `loja` (ficha e novos),
  `avaliacoes`, `produto_videos` (prioridade baixa). Reservados para a 027: `busca_assunto`, `video`.
- `POST /api/coleta/coletas` abre a rodada (409 se já há uma aberta; 503 `coleta_desligada`);
  `POST …/{id}/itens` recebe lotes de até 50 itens `{tarefaId, status, coletadoEm, campos, bruto, imagens?}` e
  responde `gravado | repetido | invalido` por item (a `data_local` é calculada **pelo servidor** no fuso do
  mercado; o bruto é podado e recusado se tiver chave pessoal); `POST …/{id}/imagens` (multipart, sha256 no
  cliente e no servidor, dedup); `POST …/{id}/fim`; `POST /api/coleta/eventos` (`captcha | login_perdido |
  layout_mudou | bloqueio_suspeito | parar_local | retomou` → sino, dedupe por rodada e tipo).
- Gestão (dono humano): `/api/coleta/clientes` (criar, rotacionar, suspender, revogar; `no-store`),
  `/api/coleta/config` (versionado; `PUT habilitada=true` sem `risco_aceito_em` → 409 `risco_nao_aceito`),
  `/api/coleta/execucoes`, `/api/coleta/estado`.
- Portão `coleta/portao.py` (molde `mcp/portao.py`): credencial (401) → interruptor (fila vazia ou 503) →
  revogado/vencido (401) ou suspenso (403) → `Origin` presente (403) → rota fora de `/api/coleta/*` (403
  `escopo_coleta`) → limite no Redis (429). Ator `Actor(kind="coletor")`, sem usuário; o coletor não
  versiona nada.
- `mcp/mapa.py`: ingestão em `FORA`; gestão em `PROIBIDAS`; `mercado_*` de leitura em `TOOLS` (escopo
  `leitura`, pronto para a 028); escritas de interesse em `FORA`; reverts em `PROIBIDAS`.

### Modelo de dados (migration `0025_mercado_shop`; o gate confere o próximo número livre)
Dimensões em toda tabela do lago: `rede platform` e `mercado text CHECK (~ '^[A-Z]{2}$')`.
- **Lago** (sem `perfil_id`, `conta_id`, `tenant_id` nem `created_by`; autoria = `coleta_id`):
  `mercado_categorias` (árvore; UQ `(rede, mercado, rede_categoria_id)`); `mercado_lojas` (identidade e último
  visto); `mercado_loja_fotos` (**só inserção**: nota, seguidores, envio no prazo, nº de produtos, vendidos
  total); `mercado_produtos` (identidade, último visto, `primeira_vez_em`, `lancado_em`, estado de coleta
  `calor | proxima_coleta_em | ultimo_erro`, `fonte_descoberta`; UPDATE só em "último visto" e estado técnico);
  `mercado_produto_fichas` (**só inserção**, nova linha só quando `hash_conteudo` muda: título, descrição,
  atributos jsonb, variantes jsonb, argumentos, selos, categoria, `bruto_ref`); `mercado_produto_imagens`
  (sha256, bucket `sociman-mercado` no HD, ordem, `ficha_id`; imutáveis, dedup global por hash);
  `mercado_produto_fotos` (**só inserção**; UQ `(produto_id, data_local, fonte, turno)` com `turno manha |
  noite` para a cadência de 2/dia; `vendidos`, `vendidos_min/max/exato`, `preco_centavos`, `preco_original`,
  `moeda`, `nota`, `avaliacoes`, `comissao_pct`, `criadores_promovendo`, `vendas_7d/30d` quando o Affiliate
  Center expõe, `estoque_visivel`, `disponivel`, `campos jsonb`, `bruto_ref`); `mercado_ranking_fotos` e
  `mercado_ranking_foto_itens` (**só inserção**); `mercado_avaliacoes` (**só inserção**: texto, nota, data,
  fotos do cliente, `autor_hash` = sha256 do id do autor com o `MERCADO_HASH_PEPPER` do `.env`, sem nome); `mercado_produto_videos` (**só inserção**: `rede_video_id`,
  `autor_handle` = @ público, views, likes, legenda, `publicado_em`; nunca nome, foto ou bio do criador); `mercado_fila` (operacional, nunca apagada);
  `mercado_coletas` (rodadas). O **bruto completo** vai para o bucket `sociman-mercado`
  (`bruto/<coleta>/<tarefa>.json`); o Postgres guarda `bruto_ref`, `esquema_versao` e os `campos`
  normalizados. Trigger `mercado_so_insercao` (reusa `metricas_recusa_mudanca()`); o `TRUNCATE` dos testes
  continua valendo.
- **Interesse** (versionado; é onde o tenant entra depois): `mercado_interesses` (`perfil_id` **nulo =
  todos**, caso da vitrine; `mercado_produto_id`; `origem manual | vitrine | ranking | video | loja |
  categoria`; `situacao ativo | pausado | encerrado`; `motivo jsonb`; `nota`; `produto_id` FK 012 nulo;
  `tema_id` nulo para 027/028; UQ parcial; `entity_type mercado_interesse`); `mercado_perfil_config` (1 por
  perfil: `mercado`, `categoria_ids`, `max_relacionados_dia`, `avisar_novo_em_alta`).
- **Infra do dono** (versionado): `coleta_clientes` (= `mcp_clientes` com `scol_`, mais `mercado`);
  `coleta_config` (singleton: `habilitada`, `risco_aceito_em/por`, janelas, `paginas_dia`, `itens_por_coleta`,
  pausas, `pausada_ate`; CHECK `NOT habilitada OR risco_aceito_em IS NOT NULL`).
- **012:** `produtos.mercado_produto_id` nulo, em `__versioned_fields__`; "Adotar do mercado" =
  `produtos.create` copiando ficha e imagens (só humano, `details.origem = "mercado_026"`).

### Cálculo na leitura (`mercado/calculo.py` puro; constantes nomeadas em `constantes.py`)
Filtro comum: `de/ate` (padrão 30 dias, até 400, no fuso do mercado), `perfilId` (só filtra, por interesse e
categorias), `mercado` (BR), `rede` (tiktok), `categoriaId`, `lojaId`, `origem`, `soAcompanhados`, `q`,
`ordenar`. Todo número sai como `{valor, estimado, motivos[], amostraPequena, nFotos}`.
- `v(d)` = vendidos da última foto com data ≤ d (o Affiliate Center com `vendas_7d/30d` tem precedência
  quando a janela coincide; a página pública é reserva). Vendas = `max(0, v(ate) − v(de − 1))`; negativo →
  nulo com `inconsistente`. Vendas/dia exige `MIN_FOTOS_VENDAS = 2` e `MIN_DIAS_ENTRE_FOTOS = 1`. Faixa
  ("1,2 mil") usa o ponto médio e carrega `incerteza`.
- GMV = Σ Δvendidos × preço vigente (centavos; min/max). Crescimento = vendas/dia dos últimos 7 d ÷ 7 d
  anteriores − 1; base menor que `MIN_VENDAS_DIA_BASE = 3` → nulo.
- Novo em alta: `primeira_vez_em` há no máximo `NOVO_DIAS = 30` **e** `vendas_dia ≥ NOVO_VENDAS_DIA_MIN = 10`
  **e** (`crescimento ≥ 0,5` **ou** apareceu em ranking `em_alta | novos` **ou** subiu ≥ `ALTA_POSICOES = 10`).
- Retorno por afiliado: `retorno_dia = vendas_dia × preco × comissao`; `score = retorno_dia / (criadores +
  K_AFILIADOS = 5)`; selo "poucos afiliados" se `criadores ≤ POUCOS_AFILIADOS = 50`; exige `comissao ≥
  COMISSAO_MIN = 5%`, foto do Affiliate Center com até `AC_FOTO_MAX_DIAS = 3` dias e `retorno_dia ≥
  MIN_RETORNO_DIA`.
- Saturação, elasticidade, sinal de estoque, taxa de avaliação e os indicadores de loja e categoria seguem a
  mesma disciplina. Nenhuma tabela agregada; os GETs não gravam (guarda). Desempenho: 10× volume, < 2 s por
  rota.

### Emenda da constitution (4.3.0 → 4.4.0; a emenda prevista pela 011 passa a ser a 4.5.0)
**Princípio IX: coleta de mercado com conta própria, só leitura e ritmo humano.** Observação pública
coletada em nome do dono, com a conta de afiliado do dono (risco aceito e registrado em
`docs/decisoes/coleta-mercado.md` e em `coleta_config.risco_aceito_em`); só leitura, com lista fechada de
ações e teste; serviço separado, fora do compose, que fala com o SociMan só pela API de ingestão (`scol_`) e
nunca com o banco; a API sem navegador, Playwright ou hosts da rede; ritmo humano ditado pelo servidor
(janela, pausas, teto); interruptor em dois níveis; captcha e login perdido param e avisam, nunca contornam;
terceiros só por hash e contadores; **lago permanente e neutro** (sem perfil ou tenant, nunca apagado,
esfriar é só cadência); todo derivado marcado como estimado; nenhuma recomendação vira ação sem humano (o
princípio I não muda). Restrições técnicas: `apps/coletor/` é o 3º aplicativo da stack, fora do Docker.

**Guardas novos** (`test_constitution_guards.py`, seção "spec 026"): API sem `playwright | selenium |
pyppeteer` no `pyproject`; `mercado/` e `coleta/` sem `httpx | playwright | publicacao` e sem hosts da TikTok;
lago sem `perfil_id | conta_id | tenant_id | created_by | user_id` (inspeção do metadata); nenhum `delete |
DELETE | TRUNCATE | apagar_por_excecao` em `mercado/` e `coleta/`; fotos só de inserção (integração); portão
`scol_` global que recusa uso fora de `/api/coleta/*`; token só hash e `check:secrets`;
`test_agendador_sem_trilha_nova` ganha `mercado`; leituras só GET e sem `history`; rotas sem "tiktok" no
nome. No coletor: `test_acoes_permitidas` (AST), `test_privacidade_poda`, `test_ritmo`, `test_log_sem_pessoal`.

### Riscos e mitigações
Detecção ou ação da rede sobre a conta (conta própria, só leitura, Chrome real visível, ritmo e tetos do
servidor, pausa em sinais, kill switch em 3 níveis, risco registrado); captcha e login (pausa com aviso no
sino; nunca contorna); mudança de layout (interceptar por URL, bruto completo no HD para renormalizar sem
recoletar, evento `layout_mudou`); dado estimado (marcação, faixas e amostra mínima); LGPD (só hash e
agregados, poda no coletor **e** recusa no servidor, screenshots desligados, logs limpos); porta CDP
(loopback, porta efêmera, perfil 700, flock); token (`scol_` só hash, mostrado 1 vez, rotação,
`check:secrets`); deriva de versão (protocolo e 426); volume (imagens e bruto no HD com o marcador
`.sociman-volume` e o piso de espaço; Postgres só com o normalizado); orçamento (prioridade manual/vitrine →
rankings → quentes → mornas → relacionados; a 1ª visita custa a página mais as imagens).

### Dependências do dono
- **X1** perfil de Chrome dedicado, logado na conta de afiliado (`sociman-coletor perfil-iniciar`).
- **X2** categorias do nicho por perfil, depois da 1ª tarefa `categorias`.
- **X3** token `scol_` em `~/.config/sociman-coletor/token` (600), `api_url` e `ca_cert` no `config.toml`.
- **X4** aceite de risco na tela, `docs/decisoes/coleta-mercado.md` e aprovação da emenda 4.4.0.
- **X5** unidade systemd de usuário instalada, com a sessão gráfica ativa nas janelas.
- **X6** validação `uma-vez --limite 3` acompanhada antes de liberar o `rodar`.
- **X7** lista inicial de links de produtos e a vitrine.

### Perguntas para o `/speckit-clarify`
1. Campos reais do Affiliate Center BR (confirmar com a sonda `uma-vez` em 1 produto; decide a fonte
   prioritária de "vendidos").
2. Quantas categorias por perfil (sugestão: até 5) e quantos rankings por dia (top 30 × `7d | 30d`) cabem nas
   300 páginas.
3. Relacionados automáticos: criar direto (`system:mercado`, 10/dia) ou só sugerir?
4. O membro vê comissão e retorno em R$? Proposta: leitura total para dono e membro; escrita só dono humano.
5. O vínculo 012 ↔ mercado é criado de qual tela (as duas?).
6. Sonda da Affiliate Creator API oficial (Partner Center) como tarefa de pesquisa paralela.
7. Taxonomia: usar a L1→L3 do TikTok Shop como vem (dicionário observado) e o dono escolhe entre as vistas?
8. "Poucos afiliados": percentis por categoria (P25 de criadores, P75 de retorno; mínimo de 10 produtos) com
   fallback absoluto, ou limiar fixo do dono?
9. Dia da foto quando a coleta cruza a meia-noite: pelo `coletado_em` no fuso do mercado (proposta).
10. Renomear a aba "Mercado" de `/app/metricas` (YouTube de origem) para "Fontes", para não confundir com
    `/app/mercado`?

## Esboço da 027: vídeos virais por assunto e nicho
- Tarefas novas na mesma fila e no mesmo protocolo: `busca_assunto` (busca e hashtags do TikTok com a conta
  logada, interceptando as respostas) e `video` (ficha e contadores de um vídeo com produto marcado); fonte
  `tiktok_shop/2` no adaptador. Reusa o `canais/` do YouTube (006) para a parte do YouTube.
- Lago: `mercado_videos` e `mercado_video_fotos` (só inserção; criador só por hash; legenda e transcrição
  quando disponíveis), ligação opcional com `mercado_produtos`; vídeo viral com produto marcado cria
  interesse `video` para o produto.
- Leitura: velocidade (views/hora, como o `yt_trending.py`), virais por assunto e por nicho do perfil
  (afinidade da 023), "o que o produto X tem de vídeo" e "você contra a mediana dos criadores do produto".
  Aba "Virais" em `/app/mercado`.
- Tudo marcado estimado; nenhuma recomendação vira ação. Mesmas guardas da 026.

## Esboço da 028: recomendações da IA e alertas
- Tipos de IA `mercado.recomendar | mercado.argumentos | mercado.alertas` pelo registro e custo da 008,
  autor `system:mercado`, com o guia da 017 e o `<desempenho>` da 023; a IA lê o cockpit pelas tools MCP
  `mercado_*` de leitura e **propõe** por `anotacoes` (propostas da 009); o humano decide.
- Mineração das avaliações (dores, objeções, argumentos reais) e dos vídeos top (gancho, formato) por
  produto; "o que gravar esta semana" por perfil (retorno por afiliado × fit com o público × novo em alta).
- Alertas calculados na leitura, na aba Alertas da 019, e a notificação `mercado_novo_em_alta` (1 por dia por
  perfil): comissão mudou, preço caiu > 15%, estoque esgotou, produto novo em loja acompanhada, produto
  promovido em queda, concorrente com poucos afiliados subiu 3 dias seguidos.
- Cache de casamento produto × tema (`aprendizado_mercado_temas`, irmã de `aprendizado_fonte_temas`), para
  a afinidade sem regex na leitura.
