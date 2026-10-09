# Data Model: 024-revisao-ux

**Sem migration.** Nenhuma tabela nem coluna nova. Tudo o que a 024 acrescenta é calculado na leitura ou fica
no navegador.

## Dados derivados (API, campos aditivos)

### CortesResumo (em `Envio.cortesResumo`, opcional)
| Campo | Tipo | Regra |
|---|---|---|
| `aceitos` | int ≥ 0 | cortes da geração não arquivados com status `na_fila`, `processando` ou `pronto` |
| `pendentes` | int ≥ 0 | não arquivados com status `revisao` |
| `falhou` | int ≥ 0 | não arquivados com status `falhou` |
| `arquivados` | int ≥ 0 | `archived_at` preenchido (qualquer status) |

- É `null` quando a geração não tem nenhum corte.
- Invariante: soma = total de cortes da geração (inclusive arquivados).

### TemaCasado (em `VideoFonte.afinidade.temas`, lista, padrão `[]`)
| Campo | Tipo | Regra |
|---|---|---|
| `temaId` | uuid | tema ativo da taxonomia do perfil que casou com o vídeo (`aprendizado_fonte_temas`) |
| `nome` | str | nome do tema |
| `pontos` | float | `a` do tema × 20, com 1 casa (contribuição isolada do tema) |
| `acao` | `"ampliar"` \| `"cortar"` \| null | preferência efetiva do perfil para o tema |
| `decisivo` | bool | o tema que decidiu a afinidade (mesmo critério do `_ordem`) |

- Ordem: decisivo primeiro, depois |pontos| decrescente e, por fim, o nome.

### AfinidadeEstado (em `VideosList.afinidadeEstado`, opcional)
| Campo | Tipo | Regra |
|---|---|---|
| `ativa` | bool | `afinidade.valores()` não é `None` |
| `motivo` | `"sem_perfil"` \| `"sem_temas"` \| `"desatualizada"` \| `"neutra"` \| null | `null` quando `ativa` |

### Página de Conteúdos
- `GET /api/conteudos?offset=N&limit=T`. A resposta é a mesma `ConteudosList` (`items`, `total`, `nextCursor`).
  A página é `offset/limit + 1`.

### Busca de propostas
- `GET /api/anotacoes?q=texto`: filtra por `texto` sem acento e sem caixa. O resto não muda.

## Estado do navegador (sem servidor; try/catch em toda leitura e escrita)
| Chave `localStorage` | Valor | Uso |
|---|---|---|
| `sociman:menu:grupos` | `{ "cortes": bool, "analytics": bool, "config": bool }` | grupos abertos no menu |
| `sociman:aprendizado:perfil` | uuid | último perfil do Aprendizado |

## Estado na URL (novo ou movido)
| Tela | Parâmetros |
|---|---|
| Conteúdos | `pagina`, `tamanho` (+ os filtros de hoje) |
| Aprendizado | `perfil`, `aba`, `conta`, `medida` |
| Propostas | `perfil`, `autor`, `tipo`, `situacao`, `q` |
| Segurança | `usuario`, `tipo`, `de`, `ate` |
| Registro da IA (aba) | `reg_perfil`, `reg_tipo`, `reg_desfecho`, `reg_de`, `reg_ate` |
| Registro do MCP (aba) | `reg_cliente`, `reg_resultado`, `reg_via`, `reg_de`, `reg_ate` |
| Cenas, Assets, Canais-fonte, Perfis, Gerações, Importação | os filtros que hoje são locais, com os nomes atuais |
