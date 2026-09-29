# Referência de layout do painel (inspirado no Material Dashboard React)

Estas são observações feitas em 2026-09-29, navegando com Playwright pela demo pública
(`demos.creative-tim.com/material-dashboard-react`): dashboard, tables, billing, notifications,
profile, sign in e sign up.

Servem só como **referência visual**. Nada de código, imagem, ícone ou marca da Creative Tim entra
no SociMan (ADR 0001). As capturas ficam em `.playwright-mcp/ref/`, que é gitignored.

## Estrutura geral
- **Menu lateral flutuante** à esquerda, com cerca de 250 px:
  - fundo escuro em degradê (quase preto), cantos arredondados de cerca de 12 px e sombra;
  - fica descolado da borda, com margem de cerca de 16 px;
  - no topo, marca e nome do produto, com um separador fino embaixo;
  - itens com ícone e rótulo, em texto claro;
  - o **item ativo** é um retângulo arredondado preenchido com a cor primária, com leve degradê e
    sombra colorida;
  - no rodapé do menu, um botão de ação de largura total. No SociMan, pode ser "Novo perfil".
- **Barra superior** transparente sobre o fundo:
  - à esquerda, a trilha de navegação e o título da página;
  - à direita, um campo "Buscar" com borda e os ícones de conta, configurações e notificações;
  - pode ficar fixa ao rolar.
- **Fundo da página** cinza muito claro (cerca de `#f0f2f5`).
- **Rodapé** discreto, com texto pequeno e links à direita.
- **Tipografia** sans (Roboto na demo; no SociMan, a fonte é local). Títulos de cartão em negrito
  escuro e textos secundários em cinza.

## Componentes recorrentes
- **Cartão de métrica:** cartão branco com um "selo" de ícone colorido quadrado (cerca de 64 px,
  degradê e sombra) que **sai para fora do topo** do cartão. À direita, o rótulo pequeno em cinza e
  o número grande em negrito; embaixo, um separador e uma linha de variação ("+3% que o mês
  passado", com o número em verde).
- **Cartão com cabeçalho colorido:** o conteúdo principal (gráfico ou título da tabela) fica numa
  faixa colorida em degradê, arredondada e com sombra, que se sobrepõe ao topo do cartão branco.
  Abaixo vêm o título, a descrição e a linha de rodapé com ícone de relógio ("atualizado há 4 min").
- **Tabela:**
  - o cabeçalho de colunas fica em CAIXA ALTA pequena, cinza e espaçada;
  - as linhas são altas, com separador fino;
  - a primeira coluna tem avatar ou logo e nome em negrito, com um subtítulo cinza;
  - os status aparecem como **badges** pequenos e arredondados (verde "ONLINE", escuro
    "OFFLINE");
  - há barras de progresso finas coloridas e ações como link de texto ("Editar") ou menu de três
    pontos.
- **Linha do tempo:** ícones circulares coloridos ligados por uma linha vertical, com título em
  negrito e data pequena. Serve para o histórico e os eventos de segurança.
- **Billing:**
  - cartão escuro destaque (estilo cartão de crédito);
  - cartões pequenos com selo de ícone centralizado;
  - lista de "faturas" com valor e link "PDF";
  - blocos de informação em fundo cinza-claro com ações "EXCLUIR" (vermelho) e "EDITAR";
  - lista de transações com ícone circular de borda colorida (entrada verde, saída vermelha).
- **Notifications:**
  - alertas de largura total com cor sólida em degradê (primário, secundário, sucesso, erro,
    aviso, info, claro, escuro) e um "×" para fechar;
  - toasts disparados por botões coloridos.
- **Profile:**
  - banner largo com imagem e sobreposição colorida;
  - cartão branco sobreposto ao banner, com avatar, nome e cargo;
  - abas em "pílula" à direita (App, Mensagens, Configurações);
  - três colunas: configurações (switches), informações (campos rótulo/valor) e conversas
    (avatar, nome, trecho e "RESPONDER");
  - grade de projetos em cartões com imagem.
- **Sign in / sign up:**
  - imagem de fundo escura em tela cheia;
  - barra superior flutuante clara com links;
  - cartão branco central com um **cabeçalho colorido que sobe para fora do cartão** ("Entrar"),
    com os ícones de login social;
  - campos com borda arredondada, switch "Lembrar de mim" e botão primário em largura total com
    texto em caixa alta;
  - um link para a outra ação no rodapé do cartão.
- **Botões:** texto em CAIXA ALTA pequena e negrito, cantos de cerca de 8 px, preenchido
  (primário ou escuro) ou com contorno ("VER TODOS").
- **Paleta da demo:** primário azul (cerca de `#1A73E8` para `#49a3f1`), sucesso verde, erro
  vermelho, aviso laranja, info azul, destaque rosa e escuro (cerca de `#344767`). O SociMan
  define a própria paleta em tokens do Tailwind/shadcn (ver a spec de base de UI).

## Mapeamento para o SociMan
| Na demo | No SociMan |
|---|---|
| Dashboard | Início: métricas (perfis ativos, contas por plataforma, cortes na fila, eventos recentes) |
| Tables | Perfis, Usuários, Segurança (TanStack Table: ordenação, filtro, paginação) |
| Billing | (sem equivalente agora; o padrão "lista + detalhe" serve a Cortes e fila de processamento) |
| Notifications | Alertas e toasts do sistema (sucesso, erro, conflito de versão, nova versão do app) |
| Profile | Página do Perfil (banner + logo + abas Dados, Contas, Marca e Histórico) e Minha conta |
| Sign In / Sign Up | Login, esqueci a senha, redefinir senha, trocar senha, verificar e-mail (sem cadastro público) |
