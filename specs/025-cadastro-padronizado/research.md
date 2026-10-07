# Research: 025-cadastro-padronizado

Decisões de design do plano. Cada uma tem: decisão, por quê e alternativas descartadas. Os nomes do
motor de geração (`geracoes`, `geracao_candidatos`, `audios`, passos, estados, delete restrito, evento de
auditoria) são os do `specs/021-geracao-local/data-model.md`; esta feature não os redefine.

## R1. Estender a 007 sem reescrever

**Decisão:** colunas novas, todas anuláveis, em `assets` e `asset_files`, valores novos de enum em
`asset_file_role`, e código novo em módulos próprios dentro de `assets/`:
`assets/padrao.py` (domínio puro: slots, ordem dos passos, situação do kit, termos de menoridade,
instruções dos passos), `assets/service_padrao.py` (pedir passo, aplicar escolha, consentimento,
revogação), `assets/router_padrao.py` e `assets/schemas_padrao.py`. O `service.py` da 007 só ganha
ganchos pequenos: os campos novos no snapshot, o `slot`/`geracao_id` em `files`, a regra "um ativo por
slot" e a validação de `role` × tipo.

**Por quê:** o FR-001 exige que nada da 007 mude de comportamento. "Padrão" evita confundir com o "kit
de marca" da 004 (`marca/service_kit.py`), que já usa a palavra "kit" no código.

**Alternativas descartadas:** tabela `avatar_kits` separada (duplicaria arquivos e histórico, que na
007 são do agregado asset); reescrever o `service.py` (risco para kit de marca, cenas e importação, que
leem assets).

## R2. Integração com o motor da 021

**Decisão:** a 025 registra no `geracao/passos.py` da 021 um `Aplicador` (`validar_alvo`,
`montar_params`, `aplicar`, e o gancho `ao_mudar_estado`, ver abaixo) para cada passo seu: `avatar.*`
(7), `cenario.cena` (substitui o aplicador piloto da 021, que gravava `referencia`, pelo slot `cena`),
`cenario.variacao`, `voz.gravacao` e `voz.design`; `voz.teste` não tem aplicador de alvo (021:
`sem_escolha`, `aplica_alvo = False`), só a validação do pedido. Os aplicadores ficam em
`geracao/aplicadores_avatar.py`, `geracao/aplicadores_cenario.py` e `geracao/aplicadores_voz.py` e chamam
`assets.service_padrao` e `vozes.service` (a seta da 021: `geracao → assets`, `geracao → vozes`; nem
`assets/` nem `vozes/` importam `geracao/`, exceto os modelos para leitura de `geracao_id`).

O pedido é a rota genérica da 021 (`POST /api/perfis/{id}/geracoes`, `geracoes_criar`, com `passo`,
`instrucao`, `referencias`, `rotulo`, `texto` e `extras`); a 025 não cria rota de "pedir passo". A 021
continua dona do job, da fila, dos estados, das seeds, da limpeza e da tela de opções.

**Protocolo (confirmado pela 021, R15 de lá):** `validar_alvo(db, alvo)`, `montar_params(db, actor,
alvo, pedido) -> dict`, `aplicar(db, actor, geracao, candidato)` e o opcional
`ao_mudar_estado(db, geracao, de: GeracaoStatus | None, para: GeracaoStatus) -> None`, chamado na mesma
transação de **toda** transição (pedir com `de = None`, espera, `revisao`, `falhou`, `cancelada`,
`descartada`, `escolhido`, `entregue`, tentar de novo). Ele não faz rede nem motor; uma exceção desfaz a
transição (na API vira o erro da rota; no gerador, `falhou` com `internal`). Em "Gerar outras", a geração
nova (e o gancho dela, `None → na_fila`) vem **antes** de a antiga virar `descartada`; "sem outra
aberta" usa `geracao.fila.abertas_do_alvo(db, alvo_tipo, alvo_id, exceto=None)`. A 025 o usa para o `status` da voz (`gerando`,
`revisao`, volta ao anterior em `falhou`/`cancelada`/`descartada` sem outra aberta) e para manter a
checagem pendente visível no avatar. **`extras`** (confirmado): objeto ≤ 2 KB guardado em
`params.extras`, validado pelo `montar_params`; cada aplicador aceita só as próprias chaves (chave
desconhecida → 400 `entrada_invalida`, `field = "extras.<chave>"`); só a pose usa (`quandoUsar`, até 300).

**Por quê:** a 021 FR-009 diz que escolher copia para o alvo e grava a versão do alvo na mesma
transação; o que copiar e para onde é regra do cadastro.

**Alternativas descartadas:** a 025 consumir eventos "geração escolhida" depois do commit (dois commits
para uma decisão humana; quebra o FR-009 da 021).

## R3. Rostos 3/4 em par

**Decisão:** **um** passo `avatar.rostos_34` (resultado `par_imagem` no registro da 021), com cada
opção guardando as duas imagens no candidato: `geracao_candidatos.image_id` = esquerda e
`image_par_id` = direita (CHECK `ck_candidatos_par` e trigger `geracao_candidatos_midia` da 021). Escolher
grava os dois slots (`rosto_34_esq` e `rosto_34_dir`) numa versão só. A limpeza de 90 dias apaga as duas.

**Por quê:** a spec fixou "uma escolha = um par" (US1, cenário 4; FR-011). Lados escolhidos
separadamente dariam esquerda e direita de seeds diferentes, com variação de luz e expressão.

**Alternativas descartadas:** duas gerações (uma por lado) — o dono escolheria duas vezes e poderia
misturar pares; imagem composta lado a lado — os passos seguintes precisam de cada lado inteiro.

## R4. Checagem de identidade (`avatar.identidade`)

**Decisão:**
- disparada pelo servidor na mesma transação em que o **último slot que falta** é escolhido (ou
  quando qualquer slot é trocado com os 5 preenchidos), com o humano da escolha como autor do pedido;
  roda fora da fila da GPU (motor `claude`, 021);
- uma chamada ao Claude com as 5 imagens (o cliente da 008 já aceita blocos de imagem desde a 023),
  pedindo saída estruturada: `notas` por slot (`rosto_frontal`, `rosto_34_esq`, `rosto_34_dir`,
  `corpo_base`, cada uma `{nota 0..10, observacao}`) e `descricao_prompt`;
- grava direto (passo só de texto, 021 FR-010): `assets.identidade = {modelo, data, notas}`, o
  `prompt` **exatamente** como veio (sem trim, até 2.000) e a `kit_status`, numa versão do asset com
  `details.geracao_id` e `details.ia`;
- a chamada entra em `ia_chamadas` com o `tipo_campo = "avatar.identidade"` (novo, `usa_guia =
  "so_proibidas"`, idioma `en`), custo e desfecho;
- **proibidas do guia (017) no caminho que grava direto:** a descrição passa por `achar_proibidas` com
  as proibidas do perfil. **Sem 2ª tentativa automática** (o `aplicar` roda dentro da transação do
  gerador e não pode chamar o Claude de novo): com proibida, as **notas** são gravadas, mas o `prompt`
  **não** é trocado (fica o anterior), a chamada fica com as `proibidas` encontradas e o aplicador ajusta
  o desfecho para `sem_acao` (o motor da 021 grava `aplicada` por padrão), e o avatar mostra "Descrição
  não aplicada: contém a palavra proibida X", com "Checar de novo" (pedido humano) ou a edição à mão.
  Sem proibida, desfecho `aplicada`.

**Por quê:** a spec manda a checagem rodar sozinha (FR-013) e o 021 FR-010 manda o resultado direto. A
regra da 017 ("salvar igual à proposta com proibida → 400") só existe no caminho do "Aplicar"; sem esta
trava, a palavra proibida entraria no campo sem nenhum humano ver.

**Alternativas descartadas:** gravar a descrição com a proibida e só marcar (o campo é copiado
literal para prompts); bloquear também as notas (elas não têm texto do guia e não podem ficar presas a
isso).

## R5. Situação do kit

**Decisão:** função pura `situacao(tipo, slots_ativos, identidade)` em `assets/padrao.py`, gravada em
`kit_status` pelo service em toda mutação que mexe em slot ou identidade:
- avatar: falta slot ou identidade → `incompleto`; todos os slots e todas as notas ≥ 7 (`NOTA_MINIMA`,
  como no pipeline) → `completo`; alguma < 7 → `atencao`;
- cenário: sem `cena` → `incompleto`; com → `completo`;
- avatar e cenário da 007 ficam com `kit_status` nulo ("sem kit padrão") até o primeiro passo.

**Por quê:** a coluna é do insumo; gravar evita recalcular na grade, e a função pura é testável.

**Alternativas descartadas:** só calcular na leitura (a grade e o MCP precisariam carregar arquivos e
identidade de cada asset).

## R6. Ordem dos passos e trocas de slot

**Decisão:**
- abertura: `rosto_origem` → `rosto_frontal` → `rostos_34` → `corpo_base` → `identidade`; look e
  pose exigem `rosto_frontal` e `corpo_base` ativos (FR-018); `cenario.variacao` exige `cena`;
- um passo com geração aberta (`na_fila`, `rodando`, `revisao`, `falhou`) recusa um novo pedido do mesmo
  passo e alvo: 409 `geracao_em_andamento`;
- trocar um slot (escolha nova ou upload no slot) arquiva o arquivo ativo anterior (o UNIQUE parcial
  garante), apaga `identidade`, põe `kit_status = incompleto` e, com os 5 slots, pede nova checagem;
- trocar `rosto_origem` ou `rosto_frontal` com derivados ativos devolve o aviso
  `derivados_desatualizados` na resposta (lista de slots, looks e poses gerados antes), sem mexer neles.

**Por quê:** é a ordem do pipeline (`avatares.py kit`), e a spec proíbe regerar sozinho.

## R7. Instruções dos passos e o `prompt` fora das edições

**Decisão:** as instruções de cada passo (frontal, 3/4 esquerda e direita, corpo-base, look, pose, cena e
variação) ficam como constantes em `assets/padrao.py`, portadas do texto testado em
`pipeline/avatares.py` e `pipeline/cenarios.py`, preenchidas com a descrição da roupa, o rótulo e a
pessoa (só no `rosto_origem`, que é txt2img). O `prompt` do avatar **nunca** entra nos `params` dos
passos de edição (frontal, 3/4, corpo-base, look, pose); um teste unitário confere isso (FR-016).

**Por quê:** o PADROES.md registra que a descrição na instrução de edição faz o Qwen Edit dar zoom e
cortar o corpo.

## R8. Termos de menoridade

**Decisão:** a regex `PROIBIDO` do pipeline, portada para `assets/padrao.py` (pt-BR e inglês: child,
kid, teen, minor, baby, criança, adolescente, menino/menina, bebê, "N years old" de 1 a 17), aplicada a
toda entrada de texto de um pedido (descrição da pessoa, instrução, descrição da roupa, rótulo, prompt
da cena, descrição da voz sintética) antes de criar a geração: 400 `menor_proibido`, "Menores de idade
não são permitidos". Sem job, sem chamada.

**Por quê:** FR-005; a lista do pipeline já foi testada. Pessoa famosa não tem detecção (Assumptions).

## R9. Consentimento

**Decisão:**
- `assets.consentimento` e `vozes.consentimento` com a forma do insumo:
  `{nome, data, registrado_por, observacao, prova: {image_id} | {audio_id} | null}`; ao revogar,
  ganham `revogado_em` e `revogado_por` (R10);
- rota própria de registrar (`PUT …/consentimento`), com `RequireHuman` (dono ou membro humano; cliente
  MCP → 403 `somente_humano`, como na 015) e versão no histórico; `registrado_por` é sempre o ator, nunca
  o corpo da requisição;
- a prova é imagem (`images.kind = imagem`, rota da biblioteca, 20 MB) ou áudio (`audios`, rota da 021,
  25 MB), do mesmo perfil;
- origem `pessoa_real` só aceita a foto do `rosto_origem` com consentimento registrado e não revogado
  (400 `consentimento_ausente`); voz `gravacao` só pede `voz.gravacao` com consentimento
  (400 `consentimento_ausente`). Origem `upload` não pede;
- a leitura do consentimento omite a prova para o MCP (só `temProva: true`).

**Por quê:** FR-009, FR-024, FR-033; a prova é dado sensível e não precisa sair para agentes.

## R10. Revogação (LGPD; exceção nomeada do princípio VII, constitution 4.3.0)

**Decisão:** `POST …/consentimento/revogar` com `RequireHumanOwner`, confirmação no corpo
(`confirmo: true`) e `version`. Numa transação:
1. grava `revogado_em`/`revogado_por` no consentimento (o resto do registro fica: nome, data, quem
   registrou);
2. arquiva o avatar ou a voz (`archived`), cancela as gerações abertas do alvo e bloqueia novas
   gerações, restauração e reversão (409 `consentimento_revogado`);
3. **avatar:** apaga, pelo delete restrito da 021 (`storage.apagar_por_excecao(key, bucket=…,
   excecao="lgpd_revogacao")`, chamado só pelo módulo `sociman_api/revogacao.py`, que o guarda
   `test_delete_so_nas_excecoes` da 021 libera), as imagens de **todos**
   os `asset_files` do avatar (slots, looks e poses, que derivam do rosto da pessoa), os candidatos de
   todas as gerações do avatar e a imagem de prova; apaga as linhas de `asset_files` correspondentes
   (`image_id` é NOT NULL), zera `primary_file_id`, `identidade` e `prompt` (a descrição física é dado
   pessoal da pessoa);
4. **voz:** apaga a gravação original, a referência, os candidatos, os áudios de teste e a prova; zera
   `ref_audio_id`, `gravacao_audio_id`, `ref_texto` e `analise`; marca a remoção pendente no shop-tts
   (R12);
4a. **gerações do alvo** (todas, de qualquer estado; as abertas já canceladas no passo 2): nos
   `geracao_candidatos`, `image_id`, `image_par_id` e `audio_id` viram `null` e `metricas` vira `{}`
   (a linha fica, porque o `escolhido_id` e o `ck_geracoes_escolhido` dependem dela; o trigger de mídia
   da 021 é só de INSERT); em `geracoes.params`, `instrucao`, `prompt`, `texto` e `extras` viram `null`;
   `limpa_em = now()`. Coordenado com a 021: é a única UPDATE em `geracao_candidatos` e em
   `geracoes.params`, feita só pelo `revogacao.py`;
4b. **`ia_chamadas`** do alvo (`entity_id` = alvo ou `geracao_id` de uma geração do alvo): `instrucao`,
   `entrada`, `proposta` e `explicacao` viram vazio/`null`; custo, tokens, modelo e desfecho ficam (o
   resumo de custo do mês não muda);
4c. **snapshots** do alvo em `entity_versions` (D1, abaixo);
   ordem dentro da transação: 4a → apagar `asset_files` → apagar as linhas de `images`/`audios` → 4b → 4c;
   os objetos do MinIO saem depois do commit;
5. grava a versão `revoked` do alvo e **um** evento `eliminacao_lgpd` em `security_events` (irmão do
   `eliminacao_candidatos` da 021: `actor_kind` humano, `outcome = "ok"`, `details = {excecao:
   "lgpd_revogacao", alvoTipo, alvoId, perfilId, imagens, audios, candidatos, geracoes, chamadasIa,
   versoesLimpas, bytes}`); nunca o nome da pessoa nem texto dela. As
   linhas saem na transação; os objetos do MinIO, depois do commit (como a limpeza da 021, R12 de lá).
   A revogação **não** consulta o `midia_em_uso`: a eliminação vale mesmo com a imagem em cena (010).

Os snapshots antigos em `entity_versions` guardam ids que deixam de existir: a tela do histórico mostra
"arquivo apagado por revogação" e o `revert` recusa.

**Snapshots antigos (D1 do dono = sim, 2026-10-07):** em todas as versões do alvo em `entity_versions`,
`prompt`, `identidade` e `consentimento.prova` viram `null` (e, na voz, `ref_texto`); a linha da versão,
o autor e a data ficam. Coberto pelo texto ajustado da exceção 2 da 4.3.0 ("os arquivos e os textos que
descrevem a pessoa, inclusive em versões antigas do histórico"). É a única escrita em `entity_versions`
fora do `history.record`, feita só pelo `revogacao.py` e auditada no evento (`versoesLimpas: N`).

**Redação do histórico (R10b):** função nova e restrita `history.redigir_versoes(db, entity_type,
entity_id, campos, *, motivo: Literal["lgpd_revogacao"], actor) -> int` em `history.py`:
- faz UPDATE em `entity_versions` do alvo, em `before` **e** `after` de **todas** as versões, trocando o
  valor de cada campo da lista por `null` (caminho JSON para `consentimento.prova`); `changed_fields`,
  `action`, autor e data ficam; soma `details.redigida = {em, por, motivo}`; devolve quantas versões mudou;
- **campos redigidos:** asset (`entity_type = "asset"`): `prompt`, `identidade`, `image_rules` e
  `consentimento.prova`; voz (`"voz"`): `ref_texto`, `analise` e `consentimento.prova`. Ficam: `name`,
  `consentimento.nome/data/registrado_por/revogado_*` (o registro que a exceção manda manter), ids de
  arquivo (já apagados, sem conteúdo) e as versões de `geracao` (só estado, sem texto);
- **guarda AST** (`test_constitution_guards.py`): só `sociman_api/revogacao.py` importa
  `redigir_versoes`, e nenhum outro módulo faz UPDATE/DELETE em `entity_versions`;
- **revert numa versão redigida:** `history.target_state` recusa com 409 `versao_redigida` ("Esta versão
  foi redigida pela revogação do consentimento e não pode ser restaurada"), para qualquer entidade; no
  alvo revogado, o 409 `consentimento_revogado` vem antes. A tela de histórico mostra "Redigido (LGPD)"
  nos campos, sem diff.

**Por quê:** FR-033a e emenda 4.3.0. Apagar só os arquivos e deixar a descrição física no histórico não
atenderia ao pedido de eliminação.

**Riscos registrados (para o dono):**
- **Cenas (010) e tomadas (D2 do dono = só listar):** cenas que apontam para o avatar continuam com o
  prompt **congelado** (status `pronta`/`usada`), que pode conter a descrição física. A revogação lista
  essas cenas na confirmação (`cenasAfetadas`) e não mexe nelas.
  Vídeos já publicados ou baixados fora do SociMan também ficam fora do alcance.
- **Backups** do banco e do MinIO feitos antes da revogação continuam com os dados até expirarem.

**Alternativas descartadas:** só arquivar (não atende à LGPD); apagar o avatar inteiro (perde o registro
de que houve consentimento e revogação, que a spec manda manter).

## R11. Vozes: pacote, estados e identificador no shop-tts

**Decisão:**
- pacote novo `vozes/` (`models.py`, `service.py`, `router.py`, `schemas.py`, `tts_id.py`), com histórico
  `entity_type = "voz"` e o `_Versioned` da 003;
- estados (insumo): `rascunho` → (pedido `voz.gravacao`/`voz.design`) `gerando` → (geração em `revisao`)
  `revisao` → (escolha) `aprovada` → ("Trocar referência", pedido novo) `revisao`. Falha ou cancelamento
  devolvem ao estado de antes do pedido (`rascunho` sem referência; `aprovada` com referência). Durante a
  troca, o status é `revisao`, mas a referência aprovada continua valendo para o "Testar", a voz padrão e o
  shop-tts (FR-026); a tela mostra "Trocando a referência";
- **identificador no shop-tts:** `tts_id(voz.id) = "v_" + voz.id.hex[:32]` (34 caracteres,
  `[a-z0-9_]`), derivado e estável, sem coluna nova; renomear a voz não muda nada no shop-tts. O `name`
  (1..60, único entre as ativas do perfil, índice parcial em `lower(name)`) é só exibição.

**Por quê:** o shop-tts aceita só `[a-z0-9_]{2,40}` e chama a voz pelo nome (`ref_<nome>.wav`); um nome
derivado do `name` quebraria ao renomear e colidiria entre perfis.

**Alternativas descartadas:** coluna `tts_nome` editável (dá para errar e é dado a mais); slug do `name`
(colisão entre perfis e renomeação).

## R12. Sincronização com o shop-tts

**Decisão:** a escolha da referência zera `sincronizada_em`. Uma linha nova do serviço
`gerador` da 021, `vozes_sync` (`GERADOR_VOZES_SYNC_S`, padrão 60 s), fora da linha da GPU (importar e
remover não usam a GPU), usa o cliente `geracao/shoptts.py` e procura `vozes` com `status IN ('aprovada','revisao')`,
`ref_audio_id` não nulo e `sincronizada_em IS NULL`, e chama `POST /v2/voices/import` (contrato da 021: `nome = tts_id`, `ref`, `ref_texto`, `meta` com
`sociman_voz_id` e `sha256`) e confere o `sha256` em `GET /voices`. Sucesso grava `sincronizada_em`; falha fica para a próxima
volta com espera crescente (log, sem estado novo). Revogação: voz com `consentimento.revogado_em` e
`sincronizada_em` não nulo é **removida** do shop-tts pela mesma trilha (rota nova `DELETE /v2/voices/{nome}`, pedido aditivo da
025 ao contrato `v2`, em `contracts/shop-tts-025.md`) e fica com
`sincronizada_em = NULL`.

**Por quê:** chamar o shop-tts dentro da transação da escolha prenderia a decisão humana a um serviço
externo (FR-023: aprovada mesmo com o shop-tts fora).

Fica no `gerador` porque só ele está na rede `gpu-local` (D2 da 021); o agendador e a API não alcançam o
shop-tts.

**Alternativas descartadas:** `BackgroundTask` do FastAPI (perde a tentativa se a API reiniciar e a API
não alcança o shop-tts); trilha do agendador (não está na rede `gpu-local`).

## R13. "Testar" a voz

**Decisão:** o passo `voz.teste` da 021 (motor `tts`, alvo `voz`, resultado áudio, `n_opcoes = 1`,
`params.texto` 1..500, `sem_escolha = True`, `aplica_alvo = False`), na fila da GPU como qualquer job
`tts`; termina em `rodando → entregue` (estado final novo da 021, CHECK `ck_geracoes_entregue`), com o
candidato `audio_id` e `metricas = {segundos, texto}`. A tela mostra o player quando o teste
termina; o áudio entra na limpeza de 90 dias. Só abre com a voz sincronizada (o shop-tts narra pelo
`tts_id`).

**Por quê:** a narração usa a GPU e precisa da regra "um job de GPU por vez" (021 FR-019); uma chamada
direta passaria por cima da fila e do OpenShorts.

## R14. "Onde é usada" da voz

**Decisão:** sem provedor em `assets/usos.py` (que indexa por `image_id`). O detalhe da voz traz
`usadaPor` (avatares ativos do perfil com `voz_id` = a voz, com nome e link), calculado na leitura, e o
detalhe do avatar traz `vozPadrao` (id, nome, status, arquivada). Não bloqueia arquivar (FR-027).

**Por quê:** o uso é por entidade, não por imagem; forçar no provedor de imagens mudaria a forma da 007.

## R15. Voz padrão do avatar

**Decisão:** `PATCH` do asset aceita `vozId` (só em `avatar`): a voz precisa ser do mesmo perfil, não
arquivada, não revogada e com referência aprovada (`status = aprovada`, ou `revisao` com referência);
senão 400 `voz_invalida`. Voz arquivada depois continua apontada, e o avatar mostra "Voz padrão
arquivada". `voz_id` entra no snapshot do asset.

## R16. Uploads

**Decisão:**
- upload num slot reusa a rota de arquivos da 007 (`POST /api/assets/{id}/arquivos`, que já tem
  `location` de 21m no edge) com `role=kit` e `slot`; a ordem de abertura vale também para o upload; o
  `rosto_origem` enviado define a `origem` (`upload` ou `pessoa_real`) no mesmo pedido;
- a gravação da voz usa a rota de áudio da 021 (25 MB, `location` de 26m da 021) e o `audio_id` vai no
  pedido do passo `voz.gravacao`; a gravação original fica em `vozes.gravacao_audio_id` e **nunca** entra
  na limpeza de 90 dias (só a revogação a apaga);
- `images.kind`: slots, looks e poses do avatar → `avatar`; `cena` e `variacao` → `fundo` (768×1344 passa
  no mínimo de 540×540); prova → `imagem`.

## R17. Histórico e reversão

**Decisão:** o snapshot do asset ganha `origem`, `consentimento` (sem a prova binária, só o id),
`voz_id`, `identidade`, `kit_status` e, em cada arquivo, `slot` e `geracao_id`. O `revert_asset` da 007
passa a: (a) arquivar primeiro e restaurar depois os arquivos de slot e de variação (para o UNIQUE
parcial não colidir no flush, como o `_flush_labels` das poses); (b) conferir rótulos de variação como
confere os de pose; (c) recusar alvo com consentimento revogado; (d) recalcular `kit_status` a partir do
estado revertido (a identidade da versão alvo volta junto, US6 cenário 3). A voz tem o próprio
`revert_voz` (só dono), que volta texto, voz de referência e status, e recusa se a referência da versão
alvo foi apagada.

## R18. Permissões

| Ação | Quem |
|---|---|
| Ler kit, vozes, notas, situação, consentimento (sem prova no MCP) | dono, membro, MCP (leitura) |
| Pedir passo, escolher opção, editar, arquivar, voz padrão, testar | humano dono ou membro (`RequireHuman`; MCP → 403 `somente_humano`) |
| Registrar consentimento, origem `pessoa_real` | humano dono ou membro (`RequireHuman`) |
| Revogar consentimento | só dono humano (`RequireHumanOwner`) |
| Reverter asset ou voz | só dono (`RequireOwner`, como na 007) |

As operações novas entram em `mcp/mapa.py`: as de leitura como tools; as de escrita na lista proibida
(as do princípio VII para revogar e reverter; as demais com o motivo "cadastro é ato humano (009
FR-023)").

## R19. SPA

**Decisão:** sem rota nova de topo. O detalhe do asset (`/app/assets/:id`) ganha, para avatar, as seções
"Kit padrão" (5 slots em ordem, notas, situação, "Refazer este passo", aviso de derivados), "Origem e
consentimento" (com "Revogar" só para o dono, AlertDialog com a lista do que será apagado) e "Voz
padrão" (NativeSelect das vozes aprovadas); para cenário, "Cena" e "Variações". O perfil ganha a aba
**Vozes** (`?aba=vozes`, DataTable) e o detalhe `/app/vozes/:id` (análise, candidatos com player,
"Testar", "Usada por", histórico). O cartão de geração (andamento, opções, "Usar opção N", "Gerar
outras", "Cancelar") é o componente da 021, reaproveitado.

## R20. Testes

**Decisão:**
- pytest com os fakes da 021 (`tests/fakes/` do ComfyUI e do shop-tts) e o `anthropic_fake` da 008
  ampliado com a saída de identidade (notas configuráveis, uma resposta com proibida);
- unitários: `padrao.situacao`, ordem dos passos, regex de menoridade, instruções sem o `prompt`,
  `tts_id`, forma do consentimento;
- integração: kit completo de ponta a ponta com os fakes; par 3/4; identidade (completo, atenção,
  proibida não aplicada, Claude fora); troca de slot (arquiva, apaga identidade, nova checagem);
  consentimento (sem → 400; MCP → 403); revogação (só dono; arquivos e linhas apagados, eventos de
  auditoria, revert e restore recusados, histórico sem `prompt`); vozes (análise, candidatos, escolha,
  sincronização pendente e feita, troca de referência mantendo a anterior, voz padrão, nome único);
  reversão com slot (UNIQUE parcial); migration `0021` (upgrade, downgrade recusa com dado novo);
- princípio I: guarda de caminhos e `operationId` nas rotas novas (sem nome de rede); princípio VII:
  toda mutação cria versão com autor, e as duas exceções de apagamento têm teste próprio;
- e2e `e2e/cadastro-padronizado.spec.ts` com o `openshorts-fake` (ComfyUI e shop-tts falsos da 021,
  Claude falso com o formato de identidade).

## R21. Migration

**Decisão:** `0021_cadastro_padronizado`, `down_revision = "0020_geracao_local"` (provisório; o gate da
implementação confere a cadeia). Upgrade: tipos `asset_origem` e `asset_kit_status`; `ALTER TYPE
asset_file_role ADD VALUE 'kit'`, `'variacao'` (fora da transação dos usos); colunas novas; tabela
`vozes` e tipos `voz_origem`, `voz_status`; FK `assets.voz_id`; índices e CHECKs (data-model). Nenhum
backfill: os assets da 007 ficam com as colunas novas nulas. Downgrade recusa se houver voz, arquivo
`kit`/`variacao` ou asset com `origem`/`kit_status`; senão remove o que criou e recria o
`asset_file_role` sem os dois valores (como a `0004`/`0005`).

## R22. "Em uso" para a limpeza da 021

**Decisão:** a 025 registra no `geracao/uso.py` da 021 o provedor `vozes_e_consentimento`: um áudio está
em uso se for `vozes.gravacao_audio_id`, `vozes.ref_audio_id` ou a prova de `vozes.consentimento`; uma
imagem, se for a prova de `assets.consentimento`. As imagens de slot, look, pose e variação já contam
pela regra "imagem em `asset_files`" da 021. Assim a limpeza de 90 dias nunca apaga a gravação original
(FR-024), a referência aprovada nem uma prova.
