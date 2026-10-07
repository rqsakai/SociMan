# Contrato HTTP: 021-geracao-local

Rotas da API do SociMan (FastAPI). O OpenAPI gerado é a fonte única (princípio IV): depois de implementar,
`npm run gen:contract` atualiza `packages/contract`, e o `check:contract` acusa divergência. JSON em
camelCase (`CamelModel`). Nenhuma rota nem `operationId` contém "youtube" ou "tiktok".

Permissões: **U** = `RequireUser` (inclui leitura por cliente MCP autorizado, se a
009 liberar no futuro); **Hu** = `RequireHuman` (dono ou membro humano; outro ator → 403
`somente_humano` + evento `publicacao_recusada`). Nenhuma rota é `RequireHumanOwner` (nada publica).

## Gerações

### `POST /api/perfis/{perfil_id}/geracoes` · `geracoes_criar` · **Hu**
Pede uma geração. Corpo:
```json
{ "alvoTipo": "asset", "alvoId": "uuid", "passo": "cenario.cena",
  "instrucao": "cozy bright bedroom, morning sun", "referencias": ["image-uuid"],
  "nOpcoes": 2, "rotulo": null, "texto": null, "extras": null }
```
- `instrucao`: 1..2000; `referencias`: 0..4 ids de imagem do perfil. Onde a imagem pode estar é decidido
  pelo aplicador do passo (`Aplicador.montar_params`): nos passos de asset, em arquivo ativo de asset ativo;
  `nOpcoes`: 1..`n_max` do passo (padrão do passo); `rotulo`: 1..60 (looks, poses, variações; obrigatório
  nesses passos); `texto`: 1..500, obrigatório só em `voz.teste` (o texto narrado); `extras`: objeto opcional ≤ 2 KB, com as chaves que o aplicador do passo aceita (hoje só `avatar.pose`: `quandoUsar` ≤ 300); chave desconhecida → 400 `entrada_invalida` (`field = "extras.<chave>"`).
- **201** `Geracao` (status `na_fila`). Erros: 400 `entrada_invalida` (com `field`); 404 `alvo_nao_encontrado`;
  409 `passo_indisponivel` (passo sem aplicador nesta versão; na 021 só `cenario.cena` está disponível);
  409 `alvo_arquivado`; 409 `alvo_incompativel` (passo não aceita esse tipo de alvo/asset; **`alvoTipo =
  produto` sempre recebe este erro aqui**, porque a 012 usa rotas próprias);
  503 `geracao_indisponivel` (motor sem configuração: `COMFYUI_URL`, `SHOP_TTS_URL` ou chave do Claude).

### `GET /api/perfis/{perfil_id}/geracoes` · `geracoes_listar` · **U**
Filtros: `alvoTipo`, `alvoId`, `status` (repetível), `passo`; cursor `(created_at desc, id)`, `limite`
≤ 50. **200** `{ itens: GeracaoResumo[], proximo: string|null }`.

### `GET /api/geracoes/{geracao_id}` · `geracoes_detalhe` · **U**
**200** `Geracao` com `candidatos` e links.

### `POST /api/geracoes/{geracao_id}/escolher` · `geracoes_escolher` · **Hu**
```json
{ "candidatoId": "uuid", "version": 3, "alvoVersion": 7 }
```
**200** `Geracao` (status `escolhido`) + o alvo atualizado no campo `alvo`. Erros: 409 `geracao_decidida`
(não está em `revisao`); 409 `version_conflict` (geração ou alvo mudou); 409 `alvo_arquivado`; 400
`candidato_invalido` (não é desta geração ou já foi apagado).

### `POST /api/geracoes/{geracao_id}/cancelar` · `geracoes_cancelar` · **Hu**
`{ "version": 3 }` → **200** `Geracao` (`cancelada`). 409 `geracao_finalizada` em estado final; 409
`version_conflict`.

### `POST /api/geracoes/{geracao_id}/tentar-de-novo` · `geracoes_tentar_de_novo` · **Hu**
`{ "version": 3 }` → **200** `Geracao` (`na_fila`). Só em `falhou` (senão 409 `estado_invalido`).

### `POST /api/geracoes/{geracao_id}/gerar-outras` · `geracoes_gerar_outras` · **Hu**
`{ "version": 3 }` → **201** `Geracao` (a nova, `na_fila`, seeds novas); a antiga fica `descartada`. Só
em `revisao` (senão 409 `estado_invalido`); alvo arquivado → 409 `alvo_arquivado`.

### `GET /api/geracoes/{geracao_id}/versoes` · `geracoes_versoes` · **U**
**200** `VersionsList` (o mesmo schema do histórico das outras entidades).

## Áudios

### `POST /api/perfis/{perfil_id}/audios` · `audios_enviar` · **Hu**
`multipart/form-data` com `arquivo`. O edge tem `location` própria (26m, sem buffering). **201** `Audio`.
Erros: 413 `arquivo_grande` (> 25 MB); 400 `audio_invalido` ("Formato não aceito: envie wav, m4a, ogg ou
mp3"; "O arquivo não tem áudio"; "Áudio longo demais (máximo 10 min)"); 503 `storage_unavailable` / 507
`storage_full` (HD, como as imagens).

### `GET /api/audios/{audio_id}` · `audios_detalhe` · **U**
**200** `Audio`.

## Integrações (aditivo)
`GET /api/integracoes` (existente) ganha, sem expor valores:
```json
{ "geracao": { "comfyui": "ok|fora|nao_configurado", "shopTts": "ok|fora|nao_configurado",
               "memoriaComfyui": "ok|travada|nao_configurado", "gpu": "livre|openshorts|pouca_vram|desconhecida",
               "gerador": "ativo|parado" } }
```

## Schemas

```text
Geracao {
  id, perfilId, alvoTipo, alvoId, passo, motor,
  instrucao: string, referencias: ImageRef[], rotulo: string|null, texto: string|null, extras: object|null,
  nOpcoes, status, progress, etapaMensagem: string|null,
  attempts, nextAttemptAt: datetime|null,
  erro: { code, message } | null,
  escolhidoId: uuid|null, startedAt, finishedAt, limpaEm: datetime|null,
  semEscolha: bool,                 # passo vai direto ao alvo (texto, produto.recorte) ou é entregue (voz.teste)
  candidatos: Candidato[],          # vazio depois da limpeza, exceto o escolhido
  deGeracaoId: uuid|null,           # "Gerar outras": a geração anterior
  version, createdAt, createdBy: UserRef, updatedAt
}
GeracaoResumo = Geracao sem `candidatos` (com `nCandidatos` e a miniatura do escolhido)
Candidato {
  id, numero, seed: int|null,
  imagem: { imageId, width, height, url /img (miniatura), link: Link (original, com validade) } | null,
  imagemPar: <mesma forma> | null,   # só avatar.rostos_34: o lado direito (imagem = lado esquerdo)
  audio: Audio | null,
  metricas: object,                 # por tipo (data-model)
  testeAudio: Audio | null          # voz: o áudio de teste
}
Audio { id, perfilId, formato, sampleRate, duracaoMs, sha256, bytes, link: Link (com validade e Range),
        createdAt, createdBy }
Link { url, expiresAt }
```

## Mídia (aditivo)
- `MidiaKind` ganha `"audio"`: link sempre com `exp` (1 h na interface), `Range` 206/416, `Content-Type`
  por formato (`audio/wav`, `audio/mp4`, `audio/ogg`, `audio/mpeg`), bucket `sociman-audios`.
- Candidatos de imagem usam `imagem` **com** `exp` (podem ser apagados pela limpeza).

## Erros (resumo)
| Código | HTTP | Mensagem |
|---|---|---|
| `entrada_invalida` | 400 | por campo |
| `candidato_invalido` | 400 | "Esta opção não é desta geração" |
| `audio_invalido` | 400 | por motivo |
| `somente_humano` | 403 | "Só um dono, pela interface, pode fazer isto" (texto da 015) |
| `alvo_nao_encontrado` | 404 | "Alvo não encontrado" |
| `passo_indisponivel` | 409 | "Este passo chega com o cadastro de <tipo>" |
| `alvo_arquivado` | 409 | "Restaure o item antes de gerar ou escolher" |
| `alvo_incompativel` | 409 | "Este passo não se aplica a este item" |
| `geracao_decidida` | 409 | "Esta geração já foi decidida" |
| `geracao_finalizada` / `estado_invalido` | 409 | por estado |
| `version_conflict` | 409 | "Recarregue e tente de novo" |
| `arquivo_grande` | 413 | "Arquivo grande demais (máximo 25 MB)" |
| `geracao_indisponivel` | 503 | por motor |

## Tela (SPA)
- **Piloto:** em `/app/assets/:id` de um **cenário**, a seção "Gerar cena" (instrução, foto de referência
  opcional, número de opções) e a lista "Gerações deste cenário".
- **Componentes reutilizáveis** (`components/geracao/`), para a 025 e a 012: `PedirGeracao`,
  `AndamentoGeracao` (porcentagem + mensagem, polling de 2 s enquanto não final), `OpcoesGeracao`
  (grade numerada, comparação lado a lado, "Usar opção N" com confirmação, "Gerar outras", "Cancelar",
  "Tentar de novo"), `ListaGeracoes`, `PlayerAudio` (`<audio controls>` nativo).
- Confirmações em AlertDialog (`role="alertdialog"`); selects nativos (`NativeSelect`), como os e2e esperam.
