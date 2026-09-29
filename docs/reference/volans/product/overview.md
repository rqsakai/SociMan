# Visão geral do produto

## O que é o Volans

Plataforma de desenvolvimento e deploy sobre a **borda da Azion**, para agências
pequenas e médias, devs indie e estudantes. Três camadas:

- **Ferramental para agentes (MCP)** — deixa um agente de IA provisionar,
  publicar e operar infraestrutura real, com teto de gasto e separação
  plan/apply.
- **Boilerplates opinativos** — starters prontos para as restrições de edge. É o
  que este repositório é.
- **Relação Azion gerenciada** — provisionamento, orçamento, handover,
  exportação.

## A tese

A maioria dos geradores de código entrega o básico **sutilmente errado**: auth
insegura, custo que explode, limites do edge ignorados. O Volans é o substrato
que faz uma IA entregar **produção, não protótipo**. Os boilerplates são o
**contrato** contra o qual todo o ferramental — e todo agente — escreve. O código
dos boilerplates é aberto; o pipeline de build/deploy é fechado.

## Este boilerplate: Auth (o primeiro)

Auth é a coisa mais fácil de fazer *parecer* que funciona e a mais fácil de
errar em segurança. É o **primeiro** boilerplate e é a **fundação** que todo app
Volans herda — não um exemplo. Se a IA acerta auth de produção aqui, prova a tese
do produto inteiro.

Entrega: cadastro, login, logout, recuperação de senha, verificação de e-mail,
sessão via JWT (padrão híbrido cookieless) e aceite de cookies (LGPD), com a
arquitetura e a segurança padrão do Volans **corretas por construção**.

## Modelo de custo do edge (afeta cada decisão)

O app roda na borda, onde **quatro limites travam antes de tudo**:

1. **Compute** — backend em edge functions é compute medido.
2. **Processamento de imagens.**
3. **Escrita em SQL.**
4. **Transferência.**

Frontend estático custa ~R$ 0. Código enxuto e cache **não são preferência de
estilo — são o modelo de negócio**. Cada escolha de arquitetura pesa esses
limites (ex.: o hash de senha é o maior custo por request de auth, e é o preço da
segurança; rate-limit e sessão idealmente vão para KV in-process, não para
escrita SQL).

## Regra de portabilidade

Nada que o app precise para **funcionar ou estar seguro** pode depender de um
serviço fechado do Volans. Teste mental em cada escolha: *"se exportar este
código hoje, ele continua correto e seguro sozinho?"* Se não, refaz. Por isso os
`node:*` e os serviços externos ficam atrás de adapters plugáveis (ver
[../architecture/connectors.md](../architecture/connectors.md)).

## Referências

- Escopo e defaults: [scope.md](scope.md)
- Decisões de arquitetura: [../decisions/](../decisions/)
- Status e ressalvas de produção: [../../PRODUCTION.md](../../PRODUCTION.md)
