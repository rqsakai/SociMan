# Contrato HTTP: 025-cadastro-padronizado

Rotas da API do SociMan (FastAPI). O OpenAPI gerado é a fonte única (princípio IV): depois de implementar,
`npm run gen:contract` atualiza `packages/contract`, e o `check:contract` acusa divergência. JSON em
camelCase. Nenhuma rota nem `operationId` contém "youtube" ou "tiktok" (guarda do princípio I).

Permissões: **U** = `RequireUser` com acesso ao perfil; **Hu** = `RequireHuman` (dono ou membro humano;
outro ator → 403 `somente_humano` + evento `publicacao_recusada`, como na 015/021); **Ho** =
`RequireHumanOwner`; **O** = `RequireOwner` (reverter, como na 007).

**Pedir um passo não tem rota nova:** é o `POST /api/perfis/{perfil_id}/geracoes` (`geracoes_criar`) da
021, com o `passo` da 025 (ver `contracts/passos.md`). Escolher, cancelar, tentar de novo e gerar outras
também são as rotas da 021.

## Asset (da 007): o que muda

### `GET /api/assets/{asset_id}` · `assets_get` · **U** (existente)
`AssetDetail` ganha (só avatar/cenário; nulos nos outros tipos):
```text
origem: "upload"|"sintetico"|"pessoa_real"|null
consentimento: Consentimento|null            # no MCP, `prova` vem como null e `temProva: bool`
vozPadrao: { id, name, status, arquivada, revogada } | null
identidade: { modelo, data, geracaoId, notas: { <slot>: { nota, observacao } } } | null
kitStatus: "incompleto"|"completo"|"atencao"|null
kit: {
  slots: [{ slot, arquivo: AssetFile|null, aberto: bool, motivo: string|null,
            nota: int|null, observacao: string|null, refazer: bool }],   # na ordem de padrao.SLOTS
  passos: [{ passo, aberto: bool, motivo: string|null, geracaoAberta: GeracaoResumo|null }],
  checagemPendente: bool, descricaoNaoAplicada: { proibidas: string[] } | null
} | null
```
Cada `AssetFile` ganha `slot: string|null`, `geracaoId: uuid|null` e `origemArquivo: "enviado"|"gerado"`.
`AssetCard` (lista) ganha `kitStatus`.

### `PATCH /api/assets/{asset_id}` · `assets_update` · **U** (existente)
Aceita também `vozId: uuid|null` (só avatar). Erros novos: 400 `voz_invalida` ("Escolha uma voz aprovada
deste perfil"); 409 `consentimento_revogado`.

### `POST /api/assets/{asset_id}/arquivos` · `assets_file_upload` · **U** (existente, mesma `location` de 21m)
Campos novos do multipart: `role=kit` + `slot`, ou `role=variacao` + `label`. No `slot=rosto_origem`,
`origem` (`upload` | `pessoa_real`) é obrigatória.
- trocar um slot arquiva o anterior, apaga `identidade`, põe `kitStatus = incompleto` e, com os 5 slots,
  pede a checagem (a resposta traz `checagemGeracaoId`);
- resposta ganha `avisos: [{ codigo: "derivados_desatualizados", itens: [{ fileId, slot|look|label }] }]`.
Erros novos: 400 `invalid_asset` (`slot` fora do tipo, slot ainda fechado: "Escolha o rosto de origem
antes"); 400 `consentimento_ausente` ("Registre o consentimento da pessoa antes de usar a foto");
409 `variacao_label_in_use`; 409 `consentimento_revogado`.

### `POST /api/assets/{asset_id}/revert` · `assets_revert` · **O** (existente)
Recusa 409 `consentimento_revogado` em avatar revogado; recalcula `kitStatus`; respeita
`uq_asset_files_slot` e `uq_asset_files_variacao_label` (research R17).

### `POST /api/assets/{asset_id}/restore` · `assets_restore` · **U** (existente)
Recusa 409 `consentimento_revogado`.

## Consentimento (novo)

### `PUT /api/assets/{asset_id}/consentimento` · `assets_consentimento_registrar` · **Hu**
```json
{ "nome": "Ana Souza", "data": "2026-10-07", "observacao": "termo assinado", "prova": { "imageId": "uuid" },
  "version": 4 }
```
`prova` opcional: `{imageId}` (imagem do perfil, enviada pela biblioteca) ou `{audioId}` (áudio do perfil,
`audios_enviar` da 021). Define `origem = pessoa_real` se o avatar ainda não tem origem. **200**
`AssetDetail`. Erros: 400 `entrada_invalida`; 409 `consentimento_revogado`; 409 `version_conflict`; 400
`invalid_asset` (não é avatar, ou avatar com `origem = upload`/`sintetico`).

### `POST /api/assets/{asset_id}/consentimento/revogar` · `assets_consentimento_revogar` · **Ho**
```json
{ "confirmo": true, "version": 5 }
```
Executa a revogação (research R10). **200** `{ asset: AssetDetail, apagados: { imagens, candidatos,
geracoes, bytes }, cenasAfetadas: [{ id, titulo }] }`. Erros: 400 `confirmacao_obrigatoria`; 409
`sem_consentimento`; 409 `consentimento_revogado` (já revogado); 409 `version_conflict`; 503
`storage_unavailable`.

### `GET /api/assets/{asset_id}/consentimento/previa-revogacao` · `assets_consentimento_previa` · **Ho**
**200** `{ imagens, candidatos, geracoes, bytes, cenasAfetadas: [...] }` (o que a confirmação mostra).

## Vozes (novo)

### `GET /api/perfis/{perfil_id}/vozes` · `vozes_listar` · **U**
Filtros `status`, `arquivadas` (bool), `q`; cursor `(updated_at desc, id)`, `limite` ≤ 50. **200**
`{ itens: VozResumo[], proximo }`.

### `POST /api/perfis/{perfil_id}/vozes` · `vozes_criar` · **Hu**
```json
{ "name": "Ana vendas", "origem": "gravacao", "tom": "vendas animada", "descricao": null }
```
`descricao` (inglês, ≤ 1000) obrigatória em `sintetica`; passa pela regex de menoridade (400
`menor_proibido`). **201** `Voz` (`rascunho`). Erros: 400 `entrada_invalida`; 409 `voz_nome_em_uso`.

### `GET /api/vozes/{voz_id}` · `vozes_detalhe` · **U**
**200** `Voz`.

### `PATCH /api/vozes/{voz_id}` · `vozes_update` · **Hu**
`{ name?, tom?, descricao?, gravacaoAudioId?, version }`. `gravacaoAudioId` só em `gravacao` e só sem
referência aprovada (trocar a gravação de uma aprovada é "Trocar referência" com outro áudio: aceito,
e a gravação anterior fica no histórico). **200** `Voz`. Erros: 400 `entrada_invalida`; 409
`voz_nome_em_uso`; 409 `version_conflict`; 409 `consentimento_revogado`.

### `PUT /api/vozes/{voz_id}/consentimento` · `vozes_consentimento_registrar` · **Hu**
Mesmo corpo do asset. Só em `gravacao`. **200** `Voz`.

### `POST /api/vozes/{voz_id}/consentimento/revogar` · `vozes_consentimento_revogar` · **Ho**
`{ "confirmo": true, "version": 3 }` → **200** `{ voz: Voz, apagados: { audios, candidatos, geracoes,
bytes }, avataresAfetados: [{ id, name }] }`.

### `POST /api/vozes/{voz_id}/archive` · `vozes_archive` · **Hu** / `…/restore` · `vozes_restore` · **Hu**
`{ version }` → **200** `Voz`. Restaurar revogada → 409 `consentimento_revogado`; nome repetido entre as
ativas → 409 `voz_nome_em_uso`.

### `GET /api/vozes/{voz_id}/versoes` · `vozes_versoes` · **U** / `POST /api/vozes/{voz_id}/revert` · `vozes_revert` · **O**
Como as outras entidades. Revert recusa 409 `consentimento_revogado` e 409 `revert_midia_apagada`
(a referência da versão alvo foi apagada).

## Schemas

```text
Consentimento { nome, data, observacao, registradoPor: UserRef, registradoEm,
                prova: { imageId, link } | { audio: Audio } | null, temProva: bool,
                revogadoEm: datetime|null, revogadoPor: UserRef|null }
Voz {
  id, perfilId, name, origem, tom, descricao: string|null, ttsId: string,
  status, trocandoReferencia: bool,          # status gerando/revisao com referência aprovada
  gravacao: Audio|null, referencia: Audio|null, refTexto: string|null,
  analise: { codec, bitrate, sampleRate, pisoRuidoDbfs, snrDb, clippingPct, duracaoS, avisos: string[] }|null,
  consentimento: Consentimento|null,
  sincronizadaEm: datetime|null, sincronizacao: "ok"|"pendente"|"removendo"|"nao_se_aplica",
  usadaPor: [{ id, name }],
  geracaoAberta: GeracaoResumo|null, ultimoTeste: GeracaoResumo|null,
  archived, version, createdAt, createdBy, updatedAt
}
VozResumo = Voz sem gravacao/analise/consentimento/usadaPor (com `nUsadaPor`)
```
`Audio`, `GeracaoResumo` e `Link`: schemas da 021.

## Erros novos (resumo)
| Código | HTTP | Mensagem |
|---|---|---|
| `menor_proibido` | 400 | "Menores de idade não são permitidos" |
| `consentimento_ausente` | 400 | "Registre o consentimento da pessoa antes de usar a foto" / "… a gravação" |
| `voz_invalida` | 400 | "Escolha uma voz aprovada deste perfil" |
| `confirmacao_obrigatoria` | 400 | "Confirme que entendeu o que será apagado" |
| `passo_fechado` | 409 | "Escolha o <slot anterior> antes" (no `geracoes_criar`, pelo aplicador) |
| `geracao_em_andamento` | 409 | "Já existe uma geração deste passo em andamento" |
| `variacao_label_in_use` | 409 | "Já existe uma variação com esse rótulo neste cenário" |
| `voz_nome_em_uso` | 409 | "Já existe uma voz ativa com esse nome neste perfil" |
| `consentimento_revogado` | 409 | "O consentimento foi revogado; este item não pode ser usado nem restaurado" |
| `sem_consentimento` | 409 | "Não há consentimento registrado" |
| `revert_midia_apagada` | 409 | "Essa versão usa arquivos apagados" |
| `versao_redigida` | 409 | "Esta versão foi redigida pela revogação do consentimento e não pode ser restaurada" |
| `voz_nao_sincronizada` | 409 | "A voz ainda não foi enviada ao serviço de voz" (no `voz.teste`) |

## MCP (`mcp/mapa.py`)
- leitura (tools): `vozes_listar`, `vozes_detalhe`, `vozes_versoes` (o `assets_get` já é tool e passa a
  trazer os campos novos, com a prova omitida);
- proibidas, princípio VII: `vozes_revert`, `assets_consentimento_revogar`, `vozes_consentimento_revogar`,
  `assets_consentimento_previa`;
- proibidas, "cadastro é ato humano (009 FR-023)": `vozes_criar`, `vozes_update`, `vozes_archive`,
  `vozes_restore`, `assets_consentimento_registrar`, `vozes_consentimento_registrar`.
