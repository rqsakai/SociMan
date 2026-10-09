# Modelo de dados: 021-geracao-local

Tudo fica no PostgreSQL (NVMe), na migration **`0020_geracao_local`** (número provisório: o gate T001
confere o próximo livre, porque a sessão paralela de UX/024 pode ocupar números). Os arquivos ficam no
MinIO do HD: as imagens no bucket `sociman` (tabela `images` da 003, sem mudança de forma) e os áudios no
bucket novo **`sociman-audios`**. As tabelas novas usam o `AuditMixin` da 001. O histórico é o
`entity_versions`, com o novo `entity_type` **`geracao`** (research R10).

Mudanças feitas pelo gerador (andamento, espera, erro, candidatos) são **estado de job**, sem versão,
como no envio da 006. Só as ações humanas versionam.

## Tipos (enums)

| Enum | Valores |
|---|---|
| `geracao_alvo` | `asset`, `voz`, `produto` |
| `geracao_motor` | `comfyui`, `tts`, `claude` |
| `geracao_status` | `na_fila`, `rodando`, `revisao`, `escolhido`, `descartada`, `cancelada`, `entregue`, `falhou` |

## `geracoes` (o job)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | |
| `alvo_tipo` | `geracao_alvo` not null | imutável |
| `alvo_id` | uuid not null | id do asset / voz / produto (sem FK: alvo polimórfico; o aplicador confere perfil e existência) |
| `passo` | text not null | CHECK `ck_geracoes_passo` com os 15 passos (FR-002; `voz.teste` coordenado com a 025); imutável |
| `motor` | `geracao_motor` not null | vem do registro do passo; imutável |
| `params` | jsonb not null | entrada resolvida: `instrucao`, `prompt` (montado, R6), `referencias` (`image_id`s do perfil; onde podem estar é validado pelo `Aplicador.montar_params` do passo), `seeds` (int[]), `n`, `rotulo`, `texto` (só `voz.teste`), `extras` (objeto ≤ 2 KB validado pelo aplicador; ex.: `quandoUsar` da pose), `bloco`; imutável depois do pedido, **exceto** a revogação LGPD (025, `revogacao.py`), que põe `instrucao`, `prompt`, `texto` e `extras` em null e preenche `limpa_em` |
| `n_opcoes` | smallint not null | 1..4; padrão do passo (2; `avatar.rosto_origem` 4; voz ≤ 3) |
| `status` | `geracao_status` not null default `na_fila` | ver Estados |
| `progress` | smallint not null default 0 | 0..100 |
| `etapa_mensagem` | text null | pt-BR curto ("Gerando opção 2 de 2", "Aguardando a GPU ficar livre") |
| `attempts` | smallint not null default 0 | tentativas contadas (R8) |
| `next_attempt_at` | timestamptz null | espera (GPU ocupada, 503, sem memória, serviço fora) |
| `heartbeat_at` | timestamptz null | **técnica** (R2): só em `rodando`; `requeue_stale` |
| `error_code` | text null | CHECK em `gpu_ocupada`, `servico_fora`, `sem_memoria`, `entrada_invalida`, `internal` |
| `error_message` | text null | mensagem curta em pt-BR (nunca o texto cru do serviço) |
| `escolhido_id` | uuid null FK → geracao_candidatos.id (`use_alter`) | só em `escolhido` |
| `started_at`, `finished_at` | timestamptz null | `finished_at` em todo estado final e em `falhou` |
| `limpa_em` | timestamptz null | **técnica** (R12): quando a limpeza de 90 dias removeu as opções não escolhidas |
| `version` | int not null | **técnica** (R10): `history.py`, controle otimista |
| AuditMixin | | `created_by` = quem pediu; `updated_by` = último humano |

Restrições e índices:
- `ck_geracoes_escolhido`: `(status = 'escolhido') = (escolhido_id IS NOT NULL)`;
- `ck_geracoes_erro`: `error_code IS NULL OR status IN ('falhou', 'na_fila')` (na fila, só com espera);
- `ck_geracoes_final`: `status NOT IN ('escolhido','descartada','cancelada','entregue','falhou') OR finished_at IS NOT NULL`;
- `ck_geracoes_entregue`: `status <> 'entregue' OR passo = 'voz.teste'`;
- `ck_geracoes_progress`: `progress BETWEEN 0 AND 100`; `ck_geracoes_n`: `n_opcoes BETWEEN 1 AND 4`;
- **`uq_geracoes_gpu_rodando`**: UNIQUE `((true)) WHERE status = 'rodando' AND motor IN ('comfyui','tts')`
  (FR-019, R2);
- `ix_geracoes_fila`: `(motor, status, next_attempt_at, created_at, id) WHERE status = 'na_fila'`;
- `ix_geracoes_alvo`: `(alvo_tipo, alvo_id, created_at desc)` (lista por alvo; seeds usadas, R7);
- `ix_geracoes_perfil`: `(perfil_id, created_at desc, id)` (lista do perfil, cursor);
- `ix_geracoes_limpeza`: `(finished_at) WHERE limpa_em IS NULL AND status IN ('escolhido','descartada','cancelada','entregue','falhou')`.

**Snapshot versionado** (`__versioned_fields__`): `status`, `escolhido_id`, `error_code`,
`error_message`. Imutáveis (`__immutable_fields__`): `alvo_tipo`, `alvo_id`, `passo`, `motor`.

## `geracao_candidatos` (as opções)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `geracao_id` | uuid not null FK → geracoes.id | |
| `numero` | smallint not null | 1..n (o "Opção N"); UNIQUE `(geracao_id, numero)` |
| `image_id` | uuid null FK → images.id | candidato de imagem (no `avatar.rostos_34`, o lado **esquerdo**) |
| `image_par_id` | uuid null FK → images.id | só `avatar.rostos_34`: o lado **direito** do par (coordenado com a 025) |
| `audio_id` | uuid null FK → audios.id | candidato de voz |
| `seed` | bigint null | |
| `metricas` | jsonb not null default '{}' | voz: `{segundos, similaridade, transcricao, teste_audio_id}`; `voz.teste`: `{segundos, texto}`; identidade: `{nota, observacao}`; ficha: o resultado; cena: `{largura, altura, segundos}` |
| `created_at` | timestamptz not null default now() | |

Restrições:
- `ck_candidatos_par`: `image_par_id IS NULL OR image_id IS NOT NULL`;
- `ck_candidatos_midia`: `num_nonnulls(image_id, audio_id) <= 1`. O resto depende do passo, que está na
  geração: a regra fica no service (o aplicador) e num trigger `geracao_candidatos_midia` (BEFORE INSERT)
  que lê o `passo`:
  - `produto.ficha` e `avatar.identidade`: as três colunas de mídia nulas;
  - `avatar.rostos_34`: `image_id` e `image_par_id` preenchidas, `audio_id` nulo;
  - os demais: exatamente um de `image_id`/`audio_id`, e `image_par_id` nulo;
- só INSERT pelo gerador; DELETE **só** pela limpeza de 90 dias (exceção 1 da 4.3.0, R12). Não há UPDATE,
  **exceto** a revogação LGPD (exceção 2 da 4.3.0, 025, só `revogacao.py`): em todas as gerações do alvo,
  `image_id`, `image_par_id` e `audio_id` vão para null e `metricas` para `{}`, e a linha fica (o
  `escolhido_id` e o `ck_geracoes_escolhido` dependem dela). O trigger é só BEFORE INSERT, e o
  `ck_candidatos_midia` aceita tudo nulo. Na mesma transação, o `revogacao.py` esvazia `instrucao`,
  `entrada`, `proposta` e `explicacao` nas `ia_chamadas` dessas gerações (custo, tokens, modelo e desfecho
  ficam).

## `audios` (nova; irmã de `images` da 003)

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | uuid PK | |
| `perfil_id` | uuid not null FK → perfis.id | |
| `object_key` | text not null UNIQUE | `perfis/{perfil_id}/audios/{uuid}.{ext}` (R11) |
| `formato` | text not null | CHECK em `wav`, `m4a`, `ogg`, `mp3` |
| `sample_rate` | int not null | > 0 |
| `duracao_ms` | int not null | 1..600000 |
| `sha256` | text not null | hex de 64 caracteres |
| `bytes` | bigint not null | **técnica**: tamanho, para a contagem do evento de limpeza e o piso do HD |
| `created_at`, `created_by` | | |

Imutável. DELETE só pelas duas exceções da 4.3.0 (candidato não escolhido aos 90 dias; revogação LGPD na
025). Limite de upload: **25 MB**; formatos validados pelo `ffprobe` (R11).

## `images` (da 003): nada muda na forma
- Os candidatos de imagem (inclusive os dois lados do par do `avatar.rostos_34`) são linhas normais de `images`, com o `kind` do passo (`fundo` no
  `cenario.cena`, como o cenário da 007; `avatar` nos passos de avatar; `produto` chega com a 012).
- A regra "imutável, nunca apagada" ganha a exceção 1 da 4.3.0: só a limpeza (R12) apaga, e só imagens de
  candidatos não escolhidos e sem uso.

## `ia_chamadas` (da 008): uma coluna
| Coluna | Tipo | Regras |
|---|---|---|
| `geracao_id` | uuid null FK → geracoes.id | preenchida nas chamadas do motor `claude` (R14) |

Índice `ix_ia_chamadas_geracao (geracao_id) WHERE geracao_id IS NOT NULL`.

## `entity_versions` e `security_events`: valores novos
- `entity_type = "geracao"` (pedir, cancelar, tentar de novo, gerar outras, escolher);
- o alvo (`entity_type = "asset"` na 021) ganha versões com `details.geracao_id` (e `details.automatico =
  true` nos passos sem escolha);
- evento `eliminacao_candidatos` (`actor_kind = "system:agendador"` ou `"system:cli"`, `outcome = "ok"`,
  `details = {excecao: "candidatos_90d", geracaoId, perfilId, candidatos, imagens, audios, bytes,
  mantidos}`), um por geração limpa.

## Estados

```text
na_fila ──claim (GPU livre / claude)──▶ rodando ──opções prontas──▶ revisao ──"Usar opção N" (humano)──▶ escolhido
   ▲  ▲                                   │  │                        └──"Gerar outras" (humano)──▶ descartada (+ nova na_fila)
   │  └───GPU ocupada (sem contar) ───────┘  │
   │  └───503 / sem memória / serviço fora (espera, conta tentativa)
   │                                         ├─erro ou tentativas esgotadas──▶ falhou ──"Tentar de novo" (humano)──┐
   └─────────────────────────────────────────┴───────────────────────────────────────────────────────────────────┘
rodando ──passo sem escolha (texto, produto.recorte)──▶ escolhido (aplicado direto)
rodando ──voz.teste (áudio pronto, alvo intocado)──▶ entregue
na_fila | rodando | revisao | falhou ──cancelar (humano)──▶ cancelada
worker parado (sem heartbeat 120 s) ──▶ na_fila (3ª vez: falhou, internal)
finais: escolhido, descartada, cancelada, entregue
```

Na tabela abaixo, "H" = ação humana com `history.record`; "J" = estado de job.

| De | Para | Quem | Tipo |
|---|---|---|---|
| — | `na_fila` | humano (pedir, gerar outras) | H (`created`) |
| `na_fila` | `rodando` | gerador | J |
| `rodando` | `na_fila` | gerador (espera) / `requeue_stale` | J |
| `rodando` | `revisao` / `falhou` | gerador | J |
| `rodando` | `escolhido` | gerador (passo sem escolha) | J (+ versão do alvo com autor = quem pediu) |
| `rodando` | `entregue` | gerador (`voz.teste`) | J (o alvo não muda) |
| `revisao` | `escolhido` | humano | H (+ versão do alvo) |
| `revisao` | `descartada` | humano (gerar outras) | H |
| `falhou` | `na_fila` | humano (tentar de novo) | H |
| não final | `cancelada` | humano | H |

## Regras derivadas (sem coluna)
- **Seeds usadas** de um alvo e passo: `SELECT seed FROM geracao_candidatos JOIN geracoes …` (R7).
- **Em uso** (`geracao/uso.py`, R12): imagem em `asset_files`, escolhida por outra geração, em `params`
  vivo, nos tokens de kit ou nos ingredientes de cena; provedores futuros (025, 012).
- **Estado da GPU** para a tela e para `GET /api/integracoes`: calculado na hora (R3), nunca gravado.

## Migração `0020_geracao_local`
1. `CREATE TYPE geracao_alvo`, `geracao_motor`, `geracao_status`;
2. `CREATE TABLE audios`, `geracoes` (sem a FK `escolhido_id`), `geracao_candidatos`; depois
   `ALTER TABLE geracoes ADD CONSTRAINT fk_geracoes_escolhido …` (ciclo, `use_alter`);
3. índices, CHECKs e o trigger `geracao_candidatos_midia`;
4. `ALTER TABLE ia_chamadas ADD COLUMN geracao_id uuid REFERENCES geracoes(id)` + índice;
5. **Downgrade:** recusa se existir linha em `geracoes` ou `audios`; senão remove a coluna, as tabelas, o
   trigger e os tipos. Nada de objeto do MinIO é tocado.

`test_migration_0020` cobre upgrade, downgrade vazio e recusa do downgrade com dados.
