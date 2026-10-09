# Research: Importação da agência (013)

Decisões técnicas da 013. Cada item traz **Decisão / Por quê / Alternativas**. Os volumes são do levantamento
de 2026-10-06 (só leitura): `shared/` com 71 arquivos (53 markdown, 18 JPEG, 5,1 MB) e `media/clipes/` com
70 MP4 (48 + 22, 896 MB); no banco de dev, 2 perfis, 3 contas, 21 canais, 16 imagens iguais às da pasta,
guias vazios e nenhum clipe do lote de 25/09.

## R1. Raízes, montagens e mapa explícito

- **Decisão:**
  - Duas raízes configuráveis: `AGENCIA_SHARED_DIR` (padrão `/agencia/shared`) e `AGENCIA_CLIPES_DIR`
    (padrão `/agencia/clipes`). No `docker-compose.yml`, o serviço `api` monta
    `${AGENCIA_SHARED_HOST:-../shared}:/agencia/shared:ro` e `${AGENCIA_CLIPES_HOST:-../media/clipes}:/agencia/clipes:ro`
    (caminhos relativos ao `SociMan/`, ou seja, as pastas do projeto da agência). O `agendador` e o `worker`
    não recebem as montagens.
  - O e2e monta `e2e/fixtures/agencia/shared` e `e2e/fixtures/agencia/clipes`. O pytest aponta as duas
    variáveis para `tmp_path` (sem montagem).
  - `agencia/mapa.py` tem a tabela `MAPA`: uma lista ordenada de `(padrão glob relativo, leitor | None,
    motivo_fora)`. O primeiro padrão que casa decide. Exemplos: `perfis/INDEX.md` → `ler_index`;
    `perfis/_modelo/**` → fora ("molde"); `perfis/*/perfil.md` → `ler_perfil`; `perfis/*/fontes.md` →
    `ler_fontes`; `perfis/*/pesquisa.md` → `ler_pesquisa`; `perfis/*/ideias-gravacao.md` → `ler_ideias`;
    `perfis/*/registro-clipes.md` → `ler_registro`; `perfis/*/{candidatos,semana,dia,clipes,revisoes}/**` →
    fora ("arquivo operacional"); `perfis/*/assets/**/*nao-usar-ainda*` → fora; `perfis/*/assets/**/*.{jpg,jpeg,png,webp}`
    → `ler_imagem_perfil`; `shop/persona.md` → `ler_persona`; `shop/persona/*` → imagem da persona;
    `shop/{nicho,fontes-dados,README}.md` → fora ("spec 012"); `shop/{avatares,avatares-candidatos,vozes-pt}.md`
    → fora ("HeyGen pausado"); `shop/{produtos,roteiros,pacotes}/**` → fora ("specs 011 e 012");
    `{agencia,aprendizados,custos}.md`, `modelos/**` → fora ("manual e moldes da agência"). Sem casar:
    "fora do mapeamento".
  - Os clipes: `<slug>/<AAAA-MM-DD>/<id>.mp4` na raiz de clipes; outro formato de caminho é "fora".
- **Por quê:** o mapa em código é o "mapeamento explícito" do spec (FR-005) e é testável linha a linha.
  As montagens `:ro` garantem no nível do sistema que o SociMan não escreve na agência (FR-004).
- **Alternativas:** um arquivo de configuração do mapa (YAGNI); ler a pasta inteira e adivinhar o tipo pelo
  conteúdo (frágil).

## R2. Varredura segura e impressão digital

- **Decisão:** `pastas.varrer(raiz)` usa `os.walk(followlinks=False)`. Um link simbólico é resolvido e
  aceito só se o destino continuar dentro da raiz (`Path.resolve().is_relative_to`); senão, "fora: link
  para fora da pasta". Limites (constantes): 2.000 entradas, markdown ≤ 2 MB, imagem ≤ 20 MB (o mesmo da
  007), vídeo pelos limites da 014 (≤ 2 GB, 1 s a 10 min, conferidos no `probe`). Passar do número de
  entradas recusa a leitura inteira (`agencia_pasta_grande`). A impressão digital de cada arquivo usado é o
  SHA-256 dos bytes, lido em blocos de 1 MB (vídeos) ou inteiro (markdown, imagens). Arquivo fora do mapa
  só tem o nome registrado, nunca aberto. A pasta inexistente ou vazia dá `agencia_pasta_indisponivel`
  (503), com a raiz que faltou.
- **Por quê:** as pastas são de outro sistema (agentes gravam nelas); a leitura precisa ser defensiva e a
  impressão digital detecta mudança entre a leitura e a confirmação (FR-011, borda "pasta alterada").
- **Alternativas:** `mtime` em vez de hash (não detecta reescrita igual nem é confiável no bind mount).

## R3. Leitor de markdown determinístico

- **Decisão:** `agencia/markdown.py`, só biblioteca padrão:
  - `normalizar(txt)`: NFKD sem acento, `casefold`, sem `**`, `` ` ``, `_` de ênfase e espaços duplos
    (reusa `ia.guia.normalizar` para o acento e a caixa);
  - `secoes(texto)` → lista de `(nivel, titulo_normalizado, titulo_original, corpo, linha_inicial)` pelos
    títulos `#`/`##`/`###`; o frontmatter `---` inicial vira um dicionário simples `chave: valor`;
  - `campos(corpo)` → linhas `- Rótulo: valor` (rótulo normalizado; valor pode continuar nas linhas
    seguintes indentadas);
  - `tabelas(corpo)` → linhas `|…|` com o cabeçalho normalizado e a linha separadora `|---|`, células com
    `|` escapado aceitas, linha com número de células diferente vira problema da linha;
  - `links(txt)` → URLs (`https?://` ou `youtube.com/…` sem esquema).
  - Leitores por arquivo (`leitores.py`) procuram as **seções do molde** pelo número e pelo título
    normalizado (`## 1. Identidade`, `## 4. Posicionamento e tom`…) e os **rótulos** do molde
    (`nome do perfil`, `@ no youtube`, `@ no tiktok`, `idioma`, `nicho principal`, `tom`, `expressoes da
    casa`, `proibido`…). O `fontes.md` exige as colunas `criador`, `canal`, `status`; `evidencia`,
    `regras do programa`, `confirmado por` e `data` são opcionais. Faltou seção ou coluna obrigatória: o
    arquivo é `nao_reconhecido`, com a lista do que faltou (FR-007).
  - Texto do molde (`<Nome>`, valor vazio, "A DEFINIR") conta como vazio.
- **Por quê:** os arquivos seguem moldes conhecidos; um parser de markdown completo é dependência nova e não
  resolve a semântica dos rótulos. Sem IA (spec, Assumptions).
- **Alternativas:** `markdown-it-py` (dependência nova); pedir ao Claude para estruturar (custo, não
  determinístico, risco de instrução no texto).

## R4. Itens, chaves e situações

- **Decisão:** cada leitor produz `Item`s (`agencia/itens.py`):
  `tipo` (`perfil`, `conta`, `guia`, `anotacao`, `canal`, `vinculo_canal`, `imagem_logo`, `asset`,
  `arquivo_asset`, `clipe`, `sugestao_bordao`), `perfil_slug`, `origem` (`arquivo`, `trecho` legível e
  `linha`), `chave` (texto estável, ver tabela), `impressao` (SHA-256 do conteúdo normalizado do item) e
  `dados` (o valor proposto, já no formato do service de destino).

  | tipo | chave | igual quando |
  |---|---|---|
  | perfil | `perfil:<slug>` | nome, idioma, nicho e status mapeado iguais |
  | conta | `conta:<plataforma>:<handle>` | existe ativa com o mesmo @ no mesmo perfil |
  | guia | `guia:<slug>` | guia do perfil com `version ≥ 1` e campos iguais aos propostos |
  | anotacao | `anotacao:<slug>:<arquivo>#<trecho>` (decisões: `#8:<data>:<sha8 da linha>`) | há item de importação ativa com a mesma chave e a mesma impressão, e a anotação não está arquivada |
  | canal | `canal:<youtube_channel_id>` | canal existe e o direito está entre os aceitos (R6) |
  | vinculo_canal | `vinculo:<channel_id>:<slug>` | o vínculo existe |
  | imagem/asset | `img:<slug>:<sha256>` | há imagem com o mesmo SHA-256 no perfil (e, para asset, ligada a um asset do tipo esperado) |
  | clipe | `clipe:<slug>:<sha256>` | há conteúdo `video_proprio` do perfil com o mesmo `video_sha256` |

  Situações: `novo`, `igual`, `diverge` (com `motivo`: `valor`, `direito`, `arquivado`, `editado`),
  `fora` (com `motivo`), `aguardando_cota`, `nao_reconhecido` (no nível do arquivo). Itens `igual` e
  `fora` não têm escolha; `novo` tem `marcado` (padrão `true`); `diverge` tem `usar` (`sociman` padrão,
  ou `markdown`). Os canais novos têm também `direito` (proposto, editável).
- **Por quê:** uma chave estável por tipo é o que dá idempotência sem tabela de "de-para" global (FR-012).
  Para anotações, que não têm chave natural, a chave do trecho mais a impressão permite saber se a seção
  mudou (vira `diverge`, e "usar o markdown" edita a anotação).
- **Alternativas:** uma coluna `origem_importacao` em cada tabela de domínio (mexe em 7 tabelas); chave só
  por hash do conteúdo (toda edição na agência viraria item novo, e a seção antiga ficaria duplicada).

## R5. Conciliação por tipo (o que cada "usar o markdown" faz)

- **Decisão:**
  - **Perfil:** novo → `create_perfil` (slug normalizado; colisão com outro nome → `fora`); diverge →
    `update_perfil` só com os campos do markdown (nome, idioma, nicho, status). Status:
    `ativo`→`ativo`, `pausado`→`pausado`, `onboarding|pesquisa|aguardando-aprovacao`→`em_preparacao`.
    Nicho > 200: corta com aviso e cria a anotação "nicho completo" (FR-022). Perfil arquivado →
    `diverge(arquivado)` sem escolha de restaurar. A bio nunca é tocada.
  - **Conta:** do §1 (`@ no YouTube`, `@ no TikTok`, com a URL entre parênteses quando houver); "Nenhum"
    não cria. Novo → `create_conta`; existente em outro perfil → `fora` ("o @ já é de outro perfil"). Não
    há "diverge" de conta (só @, plataforma e URL; URL diferente é ignorada).
  - **Guia:** proposto `tom` (≤ 500), `vocabulario` (expressões separadas por `·`, ` / ` ou aspas; cada
    termo ≤ 60, até o máximo da lista) e `nao_faca` (proibido, uma regra por item separado por vírgula ou
    `;`, ≤ 200). Guia sem versão → `novo` → `put_perfil` com `version = 0`. Guia com versão → `igual` ou
    `diverge(editado)`; "usar o markdown" → `put_perfil` com a versão lida (409 na confirmação = mudou
    desde a leitura).
  - **Sugestão de bordão:** só aparece na prévia (situação `sugestao`), nunca grava (FR-020).
  - **Anotação:** novo → `anotacoes.criar` (alvo `perfil`, tipo `observacao`, texto até 4.000 com o
    título "`<arquivo>` §`<seção>`" na 1ª linha; corpo maior é dividido em partes "(1/2)"); diverge →
    `anotacoes.editar` com a versão lida.
  - **Canal:** ver R6. Vínculo novo → `update_canal(perfil_ids = atuais + perfil)`.
  - **Imagens e assets:** ver R9.
  - **Clipes:** ver R9.
- **Por quê:** reaproveitar os services garante as mesmas validações, o mesmo histórico e as mesmas regras
  (unicidade de @, limites, arquivamento) do uso manual; a importação vira só "quem chama".
- **Alternativas:** gravar direto nas tabelas (duplica regras e esquece histórico).

## R6. Canais-fonte e direito (Q1)

- **Decisão:**
  - **Identificação:** da célula "Canal", o primeiro link do YouTube (`/channel/UC…`, `/@handle`, `/c/…`,
    `/user/…`, `youtube.com/<nome>`) vai para `canais.service_canais.resolver` (mesmo parser
    `resolver_entrada` e mesma cota). Sem link do YouTube, ou com "não confirmado"/"a confirmar" na célula
    → `fora(sem_canal_youtube)`, com o texto original. Twitch, TikTok e sites são ignorados para a
    identificação e vão para a nota. "Material original próprio" (sem link, pasta `media/originais`) →
    `fora(conteudo_proprio)`, com a explicação do envio avulso.
  - **Cota:** a prévia guarda o resultado do `resolver` por entrada (não repete a chamada); um 429/`cota`
    da 006 deixa as linhas restantes em `aguardando_cota`, e o resto segue. Na confirmação, o
    `create_canal` gasta a unidade da 006 de novo (o `resolver` não grava).
  - **Status proposto (canal novo):** `programa-de-cortes` → `programa_de_cortes`; linha marcada como
    própria ("canal próprio", "conteúdo próprio", "próprio do dono" na linha) → `proprio`; `autorizado` →
    `sem_acordo` (o dono pode trocar para `parceiro`); `pendente`, `negado`, `desconhecido` → `sem_acordo`.
    O dono pode escolher qualquer um dos 4 em cada linha nova.
  - **Aceitos (canal existente, FR-015a):** `programa-de-cortes` → {`programa_de_cortes`}; próprio →
    {`proprio`}; `autorizado` → {`sem_acordo`, `parceiro`}; `pendente|negado|desconhecido` →
    {`sem_acordo`}. Fora disso → `diverge(direito)`; "usar o markdown" pede o status escolhido (padrão: o
    proposto) e chama `mudar_direito` com a versão lida.
  - **Evidência:** `direito_evidencia_url` = primeiro link da coluna "Evidência"; `direito_evidencia_nota`
    = "fontes.md de `<slug>`, linha N: status `<md>`. <evidência>. Regras: <…>. Confirmado por <…> em
    <data>." (cortada no limite do schema com "…"). Num canal existente, a nota só muda junto com o
    direito, por escolha do dono.
  - **Duas linhas para o mesmo canal:** um item `canal` só, com os vínculos; status mapeados diferentes →
    `diverge(direito)` com as duas origens.
  - Com o banco atual: 18 `igual` (2 programa, 1 próprio, 15 `autorizado` como `parceiro`), 3
    `diverge(direito)` (Fofocalizando, Vênus, Blogueirinha: `pendente` como `parceiro`) e 8 `fora`.
- **Por quê:** Q1 e o princípio II: proposta conservadora, decisão do dono e nada muda em silêncio. Aceitar
  `parceiro` para `autorizado` evita 15 falsas divergências do que o dono já decidiu à mão.
- **Alternativas:** criar o canal sem o YouTube (o modelo exige `youtube_channel_id` e playlist de
  uploads, e a sync quebraria).

## R7. Pré-visualização no Redis

- **Decisão:** `POST /api/agencia/previa` (H) monta os itens e grava `agencia:previa:<uuid>` no Redis com
  `EX = 30 min`: o autor, os itens (com `dados`), as impressões digitais dos arquivos, a **base** (para
  cada entidade existente tocada: `entity_type`, id e `version` lida) e o resultado do `resolver`. Tamanho
  esperado < 1 MB (texto; vídeos só com caminho, tamanho e hash). A resposta traz os itens sem os `dados`
  grandes (o texto da anotação vem resumido em 300 caracteres) e as contagens. A confirmação lê com
  `GETDEL` (uso único); expirou ou já usada → 409 `previa_expirada`. Uma prévia é do dono que a criou
  (outro usuário → 404).
- **Por quê:** mesmo padrão da 020 e do `state` da 015; nada vai ao PG antes de confirmar (FR-009).
- **Alternativas:** guardar a prévia no PG (lixo a limpar).

## R8. Confirmação: tarefa de fundo, arquivos antes, transação depois

- **Decisão:**
  1. `POST /api/agencia/importacoes` (H) com `{previaId, escolhas}`: valida as escolhas contra a prévia,
     cria a `Importacao` em `processando` (com `history.record created`), faz commit e responde **202**.
     Uma segunda confirmação da mesma prévia recebe 409 `previa_expirada` (o `GETDEL` já consumiu).
     Só uma importação `processando` por vez (índice parcial único) → 409 `importacao_em_andamento`.
  2. A tarefa de fundo (`BackgroundTasks`, mesma imagem e processo da API, sessão própria):
     a. reconfere a impressão digital dos arquivos usados; mudou → os itens daquele arquivo ficam
        `nao_gravado(mudou_desde_a_leitura)`;
     b. soma os bytes de imagens e vídeos novos marcados e chama `datadir.ensure_writable(total)`; falhou →
        importação `falhou` com o motivo, nada gravado;
     c. **grava os arquivos** no MinIO (imagens no bucket `imagens` pelo caminho da 007; vídeos e miniaturas
        pelo caminho da 014), com ids pré-gerados; atualiza `progresso` (feitos/total) na linha da
        importação a cada arquivo (commit curto);
     d. abre **uma transação**: para cada item marcado, confere a `version` da base (mudou →
        `nao_gravado(editado_desde_a_leitura)`, sem abortar), chama o service (R5, R6, R9) com o `Actor`
        do dono e `details.importacao = {id, arquivo, trecho}`, e grava o `ImportacaoItem` com o resultado;
        erro inesperado → rollback, importação `falhou` (com o erro em pt-BR), arquivos órfãos
        (aceito, Complexity Tracking);
     e. fecha com `concluida`, as contagens e `history.record updated`.
  - A tarefa de fundo reconstrói o `Actor` do dono (`kind = "user"`, o `user_id` da prévia) e confere de
    novo que ele continua dono e ativo; senão, `falhou(dono_inativo)`.
  3. A SPA acompanha com `GET /api/agencia/importacoes/{id}` a cada 2 s enquanto `processando`.
  4. Se a API reiniciar no meio, a importação fica `processando` com o `progresso_em` parado: ao ler, uma
     importação `processando` sem progresso há mais de 10 min é marcada `falhou(interrompida)` (nada foi
     gravado no domínio, porque a transação é o último passo).
  - O `details.importacao` precisa chegar ao `history.record` dos services: eles ganham o parâmetro
    opcional `details` onde ainda não têm (acréscimo, sem mudar o comportamento atual), ou a importação usa
    o contexto `history.origem(...)` (variável de contexto lida pelo `record`). **Escolha:** o contexto
    (`contextvars`), para não alterar 10 assinaturas; o `record` junta `{"importacao": …}` aos `details`
    quando ele está ativo.
- **Por quê:** "tudo ou nada" no domínio (FR-011) com arquivos grandes; sem serviço novo (VIII); a
  requisição não depende do timeout do edge.
- **Alternativas:** síncrono (minutos presos na requisição, timeout de proxy); trilha do agendador (serviço
  e lock a mais); uma transação por item (quebra o tudo ou nada).

## R9. Imagens, persona e clipes

- **Decisão:**
  - **Imagens do perfil:** validadas por `imaging.validate_image` (conteúdo, 20 MB, `IMGPROXY_MAX_SRC_RESOLUTION`).
    `logo.jpg` → `perfis.service_imagens` (logo) só se o perfil não tiver logo; senão, se o SHA-256 for
    igual ao logo atual → `igual`, diferente → `diverge(valor)`. `avatar-poses/*` → um asset `avatar`
    (nome "Avatar do perfil", ou o asset avatar que já tiver alguma dessas imagens) com cada imagem como
    `pose` (rótulo do nome do arquivo, `avatar-2-rpg-dnd` → "rpg dnd"); `avatar-5poses.jpg` → `referencia`
    do mesmo asset; `stickers/*` → asset `sticker` se a imagem tem transparência, senão `imagem` (o
    mesmo critério da 007); `foto-perfil` e demais → `imagem`. Conciliação pelo SHA-256 no perfil (R4).
  - **Imagem citada que não existe** (ex.: `assets/watermark.png` no §5 do `perfil.md`): item `fora`
    ("arquivo citado não encontrado"), só como aviso.
  - **Persona:** o dono escolhe o perfil (padrão: o perfil que já tem uma imagem com o SHA-256 de uma das
    imagens da persona). Avatar "Achadinhos" (nome do título `# Persona: …`): `prompt` = a citação da seção
    "Descrição para prompts", `voice_tone` = a seção "Voz", `image_rules` = "Regras de imagem"; cada imagem
    da tabela "Imagens de referência" → `referencia` com `look` = coluna "Look". Cada item de "Cenários" →
    asset `cenario` com `prompt`. Existente (por nome no perfil ou por SHA-256): campos iguais → `igual`;
    diferentes → `diverge(valor)` campo a campo; "usar o markdown" → `assets.update` com a versão lida.
  - **Clipes (Q2):** o registro dá `id → (data, fonte, título, produto/CTA, obs)`; o vídeo é
    `<slug>/<data>/<id>.mp4`. Linha sem vídeo, vídeo sem linha ou vídeo inválido (`probe` da 014) → `fora`.
    Novo → `conteudos.video_proprio.create_de_arquivo(db, actor, perfil_id, path, titulo, sha256)`: a
    mesma rotina da rota, recebendo um arquivo já no disco (o vídeo é lido da montagem, a miniatura vai
    para o `spool_dir` do HD) — extraída da função atual sem mudar a rota. Título = "Título" do registro,
    cortado em 100. Depois, `anotacoes.criar` no alvo `conteudo` com "registro-clipes.md · <id> · <data>
    · Fonte: <url e trecho> · <produto/CTA> · <obs>". Status e métricas do registro não entram.
- **Por quê:** reaproveitar a validação e os caminhos de armazenamento da 007 e da 014; a anotação guarda a
  origem sem coluna nova no conteúdo.
- **Alternativas:** coluna "origem" em `conteudos` (migration e schema a mais para 70 linhas).

## R10. Desfazer

- **Decisão:** `POST /api/agencia/importacoes/{id}/desfazer` (H, `{version}`), só para `concluida`. Para
  cada item `criado`/`atualizado`, na ordem inversa, numa transação:
  - **criado** e a entidade ainda está na versão gravada (não mexida) e sem uso → arquiva pelo service
    (`archive_*`; anotação → `arquivar`; vínculo de canal → `update_canal` sem o perfil; arquivo de asset →
    `archive_file`; logo → `clear_image`). Uso que impede: canal com envio, conteúdo com destino, asset no
    kit (409 do service) → `nao_desfeito(em_uso)`;
  - **guia criado** pela importação (o perfil não tinha guia) e intocado → `put_perfil` com os campos
    vazios (na 017, "limpar" é salvar vazio; não há DELETE);
  - **atualizado** e a entidade está na versão gravada → `revert_*` para a versão anterior (guia,
    perfil, canal, asset, anotação); mexida depois → `nao_desfeito(editado_depois)`.
  - A importação passa a `desfeita` (autor, data), cada item ganha `desfeito_em` ou o motivo, e o ato vai
    para o histórico da importação. Nada é apagado; arquivos no MinIO ficam sem referência.
- **Por quê:** FR-029 e princípio VII com os mesmos atos de arquivar e reverter que o dono já usa.
- **Alternativas:** apagar o criado (proibido); desfazer só tudo ou nada (um item editado depois travaria
  o resto).

## R11. Permissões, MCP e guardas

- **Decisão:** prévia, confirmar e desfazer são `RequireHumanOwner` (403 `somente_humano` + evento
  `publicacao_recusada` para não humano; 403 `somente_dono` para membro), como na 015/020. Lista, detalhe
  e estado são `RequireUser`. No `mcp/mapa.py`: `agencia_previa`, `agencia_confirmar` e
  `agencia_desfazer` em `_PROIBIDAS_DONO`; `agencia_importacoes_list` e `agencia_importacoes_get` entram
  como **leitura** (os agentes sabem o que foi migrado); `agencia_estado` fica em `_FORA_INFRA`. Guardas
  novas em `test_constitution_guards.py`: `agencia/` não importa `publicacao`, `httpx` nem
  `sociman_api.canais.youtube` direto (só pelo service); nenhum `open(..., "w"|"a"|"x")`,
  `write_text`, `write_bytes`, `unlink`, `rename`, `mkdir` ou `shutil` em `agencia/`.
- **Por quê:** FR-001, FR-002, FR-004 e o padrão do projeto.

## R12. SPA

- **Decisão:** `/app/configuracoes/importacao` (dono e membro; botões só para dono):
  - **Estado:** as raízes (disponível ou não), a última importação por perfil e "arquivos mudaram desde
    então" (`GET /api/agencia/estado`, que só lê as impressões digitais, sem montar itens) (FR-028);
  - **Ler a pasta** → prévia: contagens por situação (cartões), filtros (perfil, tipo, situação) e a
    `DataTable` com origem, situação, motivo e a escolha (checkbox para `novo`; `NativeSelect`
    "Manter o SociMan / Usar o markdown" para `diverge`; `NativeSelect` de direito para canal novo e para
    `diverge(direito)` com "usar o markdown"); `ItemDiverge` mostra os dois lados; o tempo restante da
    prévia; "Confirmar importação" (AlertDialog com o resumo: N criar, M trocar, X MB a gravar no HD);
  - **Andamento:** barra com `progresso` e a etapa enquanto `processando`; ao fim, o resumo e o link para o
    detalhe;
  - **Lista** de importações e **detalhe** (`/app/configuracoes/importacao/:id`) com os itens, o resultado e
    "Desfazer" (AlertDialog com a lista do que será arquivado ou revertido).
  - Sidebar: "Importar da agência" no grupo Configurações.
- **Por quê:** segue o padrão das telas de configuração (005/018) e os componentes `Field`/`NativeSelect`
  que os e2e usam.
