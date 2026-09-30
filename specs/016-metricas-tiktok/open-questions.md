# Perguntas abertas para o dono: 016-metricas-tiktok

**Resolvido em 2026-09-30:** o dono escolheu a opção recomendada (A) nas 4 perguntas. As
respostas estão em [spec.md](spec.md) (Clarifications, Session 2026-09-30) e já refletidas no
plan, no research, no data-model, no contrato e no quickstart. Nenhuma decisão pendente.

| Pergunta | Resposta | Onde está |
|---|---|---|
| Q1. Características que ficam na anonimização | **A**: só as não textuais (origem, modo de envio, nota, status do canal, duração, hora e dia, intervalo desde o post anterior, seguidores na publicação, **tamanho** do gancho e **número** de hashtags) | research R13, data-model (`features`) |
| Q2. Vídeos com mais de 1 ano na primeira varredura | **A**: entram com uma foto (a da descoberta) e param | research R5, FR-003 |
| Q3. Ligar sozinho os posts do lembrete | **A**: só depois de "Marcar como postado" (sem link); âncora = hora do clique (post até 24 h antes ou 1 h depois), mesma regra de duração, legenda e candidato único; antes do clique, candidatos para o dono escolher em 1 clique | research R10, R11 e R12, data-model (vínculo), contrato (`Candidato`, `Vinculo`) |
| Q4. Onde guardar | **A**: só o PostgreSQL que já existe; pausa da coleta por `METRICAS_COLETA_HABILITADA=false` no `.env` | research R3, R8 e R20, FR-004 |

## Registro das opções (para consulta)

- **Q1:** A (só não textuais) × B (A + texto do gancho e hashtags). A porque um texto do gancho
  ou uma hashtag rara bastam para achar o post.
- **Q2:** A (uma foto e para) × B (ignorar). A porque a foto não custa chamada e o número final
  é um bom rótulo para o modelo.
- **Q3:** A (âncora no clique "postado") × B (nunca sozinho) × C (âncora no horário agendado
  ±6 h). A porque o clique é uma âncora quase tão boa quanto a entrega do rascunho, e a regra de
  candidato único continua impedindo ligações erradas.
- **Q4:** A (só Postgres) × B (híbrido com MongoDB) × C (tudo no MongoDB). A porque o volume é
  pequeno (30 a 300 MB/ano), o valor está na junção com os dados do corte e a anonimização
  precisa de uma transação só. B ou C exigiriam emenda da constitution.
