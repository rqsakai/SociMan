# Decisão: coleta de mercado com a conta de afiliado do dono

**Data:** 2026-10-08 · **Quem decide:** o dono · **Status:** rascunho para confirmação do dono (a confirmação
na tela de `/app/configuracoes/coleta` grava `coleta_config.risco_aceito_em/por`; este arquivo é o registro legível).
**Base:** constitution 4.4.0, princípio IX; insumo `docs/insumos/026-mercado-shop.md`; pesquisa
`../../shared/shop/fontes-dados.md` (seções (a) e (e)).

## O que foi decidido
1. O SociMan coleta os dados de mercado do TikTok Shop por conta própria, com um robô que navega como pessoa no
   Chrome real do desktop do dono, **logado na conta de afiliado do dono**, num único perfil de Chrome.
2. Nenhuma ferramenta paga (FastMoss, Kalodata, EchoTik) entra como base; ficam como plano B.
3. O robô é só leitura: nunca segue, curte, comenta, adiciona à vitrine, compra ou pede amostra.
4. As **fotos que clientes anexam às avaliações públicas** são guardadas como vêm (originais). Elas podem mostrar
   pessoas e ambientes; são dado pessoal de terceiros sob a LGPD. O dono foi informado da alternativa (só texto,
   nota e data) e decidiu guardá-las, em 2026-10-08 (clarificação da spec 026). O autor da avaliação continua só
   como hash.

## O risco que o dono aceita
- Os Termos de Serviço da TikTok proíbem coleta automatizada. A TikTok declara combater scraping. A conta usada é
  a que recebe comissão de afiliado: a rede pode exigir verificação, limitar ou **suspender** essa conta, e com
  ela a comissão.
- A pesquisa de 2026-09-24 recomendava não raspar logado com a conta do afiliado. O dono foi informado dessa
  recomendação e das alternativas (perfil anônimo separado, conta coletora separada, ferramenta paga) e optou pela
  conta própria mesmo assim, em 2026-10-08.

## Mitigações exigidas pela constitution (princípio IX)
Ritmo humano ditado pelo servidor (janela 08h-23h, pausas de 5 a 40 s, ~300 páginas/dia, uma aba), interruptor em
dois níveis, parada automática em captcha, login perdido ou bloqueio (nunca contornar), serviço isolado fora do
compose, terceiros só por id público e contadores, logs sem dado pessoal.

## Revisão
O dono pode desligar a coleta a qualquer momento (`COLETA_HABILITADA=false`, botão da tela ou `systemctl --user
stop sociman-coletor`). Rever esta decisão se a conta receber qualquer aviso da TikTok.

_Confirmação do dono: ______ (data). Marcar aqui ou pelo aceite na tela._
