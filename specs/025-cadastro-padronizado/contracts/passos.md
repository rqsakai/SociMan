# Contrato: passos da 025 no motor da 021 (aplicadores)

Como cada passo da 025 entra no `POST /api/perfis/{perfil_id}/geracoes` (`geracoes_criar`, 021) e o que o
`Aplicador` (registro `geracao/passos.py` da 021) faz. Os nomes de passo, motor, resultado, `n` e estados
são os da 021; aqui só a parte da 025.

Toda validação abaixo roda em `validar_alvo`/`montar_params`, **antes** de criar a geração (nada de job
com pedido inválido). Comum a todos:
- alvo do mesmo perfil, não arquivado (021) e sem consentimento revogado (409 `consentimento_revogado`);
- regex de menoridade sobre `instrucao`, `rotulo` e `extras` (400 `menor_proibido`);
- uma geração aberta (`na_fila`, `rodando`, `revisao`, `falhou`) do mesmo passo e alvo → 409
  `geracao_em_andamento` (exceto `voz.teste`, um por vez por voz, e `avatar.look`/`avatar.pose`/
  `cenario.variacao`, uma por rótulo);
- o `prompt` do avatar **nunca** entra em `params` dos passos de edição (FR-016; teste unitário).

| Passo | Alvo | Resultado / n | Abre quando | Entrada do pedido → `params` | `aplicar` (escolha humana) |
|---|---|---|---|---|---|
| `avatar.rosto_origem` | avatar | imagem / 4 | sem `rosto_origem` ativo ou refazer; avatar sem `origem` ou `sintetico` | `instrucao` = descrição da pessoa (inglês, adulta) → prompt txt2img (bloco `retrato`) | slot `rosto_origem`; `origem = sintetico` |
| `avatar.rosto_frontal` | avatar | imagem / 2 | `rosto_origem` ativo | `instrucao` opcional (ajuste); `referencias = [rosto_origem]`; instrução fixa KIT_FRONTAL | slot `rosto_frontal` |
| `avatar.rostos_34` | avatar | **par_imagem** / 2 | `rosto_frontal` ativo | `referencias = [rosto_frontal]`; instruções fixas esquerda/direita da imagem | `image_id` → `rosto_34_esq`, `image_par_id` → `rosto_34_dir` (uma versão) |
| `avatar.corpo_base` | avatar | imagem / 2 | `rosto_34_esq` e `rosto_34_dir` ativos | `referencias = [rosto_frontal]`; instrução fixa KIT_CORPO (9:16, cinza, legging, tênis) | slot `corpo_base` |
| `avatar.identidade` | avatar | texto (sem escolha) | os 5 slots ativos | pedido **pelo servidor** (não pela tela) ao completar/trocar slot; `referencias` = os 5 slots | `identidade`, `prompt` (se sem proibida), `kit_status` (research R4) |
| `avatar.look` | avatar | imagem / 2 | `rosto_frontal` e `corpo_base` ativos | `rotulo` (nome do look, 1..60), `instrucao` (roupa toda), `referencias = [base, rosto_frontal]` (base = `corpo_base` ou a pose escolhida em `referencias[0]`) | `asset_files` `referencia` com `look = rotulo`, `geracao_id` |
| `avatar.pose` | avatar | imagem / 2 | idem | `rotulo` (único entre poses ativas, conferido antes), `instrucao` (roupa vestida), `extras.quandoUsar` (≤ 300; outra chave → 400 `entrada_invalida`, `field = "extras.<chave>"`), `referencias` como no look | `asset_files` `pose` com `label`, `quando_usar`, `geracao_id` (re-confere o rótulo: 409 `pose_label_in_use`) |
| `cenario.cena` | cenário | imagem / 2 (768×1344) | sempre (refazer troca) | `instrucao` = prompt do ambiente (ou o `prompt` do cenário), `referencias` = foto opcional; sufixo "sem pessoas, área livre para produto" | slot `cena` (substitui o aplicador piloto da 021); `kit_status = completo`; o 1º vira `primary_file_id` se não houver |
| `cenario.variacao` | cenário | imagem / 2 | `cena` ativa | `rotulo` (único entre variações ativas), `instrucao` (o que muda), `referencias = [cena]` | `asset_files` `variacao` com `label`, `geracao_id` |
| `voz.gravacao` | voz (`gravacao`) | áudio / até 3 | `gravacao_audio_id` preenchido e consentimento registrado | o aplicador lê `gravacao_audio_id` e `tom` da voz (o corpo não traz áudio) | `ref_audio_id`, `ref_texto` = `metricas.transcricao`, `status = aprovada`, `sincronizada_em = null`; `analise` gravada ao chegar em `revisao` |
| `voz.design` | voz (`sintetica`) | áudio / até 3 | sempre | `instrucao` opcional (texto falado; padrão: fala de vendas de ~12 s); `descricao` e `tom` vêm da voz | idem `voz.gravacao` (sem `analise`) |
| `voz.teste` | voz | áudio / 1, `entregue` | voz com referência e `sincronizada_em` não nulo (senão 409 `voz_nao_sincronizada`) | `texto` (1..500) | nenhum (021: `aplica_alvo = False`) |

## Gancho `ao_mudar_estado(db, geracao, de: GeracaoStatus | None, para: GeracaoStatus)` (confirmado pela 021)

Chamado na mesma transação de toda transição (pedir com `de = None`); sem rede nem motor; exceção desfaz a
transição. "Sem outra aberta" = `geracao.fila.abertas_do_alvo(db, "voz", voz.id, exceto=geracao.id)` vazio
(em "Gerar outras", a nova já existe quando a antiga vira `descartada`, então a voz fica em `gerando`).

| Passo | Transição | Efeito na 025 |
|---|---|---|
| `voz.gravacao`, `voz.design` | `None → na_fila` (pedir, gerar outras) e `falhou → na_fila` (tentar de novo) | `vozes.status = gerando` |
| idem | `rodando → revisao` | `vozes.status = revisao`; `vozes.analise` (do `Lote`) |
| idem | `→ falhou`, `→ cancelada`, `→ descartada` sem outra geração aberta do alvo | `vozes.status` volta: `aprovada` se há `ref_audio_id`, senão `rascunho` |
| `avatar.identidade` | `→ falhou` | o avatar mostra "Checagem pendente" com "Checar de novo" (pedido humano do mesmo passo) |
| `avatar.*` (imagem) | qualquer | nada (o `kit_status` só muda na escolha) |

O efeito roda na mesma transação da transição; um erro no gancho desfaz a transição (e o teste cobre).
