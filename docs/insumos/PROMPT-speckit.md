Vamos especificar três features novas com o Spec Kit, a partir de insumos já prontos e decididos pelo dono.
Siga o CLAUDE.md do SociMan (um passo por vez, nada de código de feature sem spec aprovada) e a constitution
em `.specify/memory/constitution.md`.

## Insumos (leia os três antes de começar)
- `docs/insumos/021-geracao-local.md`: jobs de geração local (ComfyUI, shop-tts, Claude) com candidatos para
  o dono escolher. É PRÉ-REQUISITO das outras duas.
- `docs/insumos/007b-cadastro-padronizado.md`: estende a 007 (assets do perfil) com kit padrão do avatar,
  vozes do perfil e cenário padronizado.
- `docs/insumos/012-produtos-shop.md`: cadastro de produtos com recorte, flat lay e ficha técnica.
Referência técnica já testada (só leitura, não copie código sem spec): `../comfyui-docker/pipeline/PADROES.md`,
`../comfyui-docker/pipeline/{produtos,avatares,voz,run_storyboard}.py` e `../comfyui-docker/tts_service/app.py`.
Leia também `specs/007-assets-do-perfil/data-model.md` e `specs/006-cortes-openshorts/data-model.md`
(padrão de job/trilha do worker e de progresso), porque os insumos estendem esses modelos.

## Ordem e numeração
1. `021-geracao-local` (número 21, short-name `geracao-local`).
2. `022-cadastro-padronizado` (número 22, short-name `cadastro-padronizado`): é a 007b; a 007 já está
   implementada e NÃO deve ser reescrita, esta feature só estende `assets`/`asset_files` e cria `vozes`.
3. `012-produtos-shop` (número 12, já reservado no backlog de `docs/visao.md`; short-name `produtos-shop`).
Antes de criar cada branch, rode `git status` e me mostre: o branch atual é `004-kit-de-marca-poc`; se houver
mudança não commitada, PARE e me pergunte o que fazer. Não faça commit sem eu pedir.

## Para cada feature, nesta sequência (pare entre as etapas para eu aprovar)
1. `/speckit-specify` com o conteúdo do insumo (passe `--number` e `--short-name` acima). A spec deve
   seguir o formato das specs existentes (User Stories com prioridade e Independent Test, FR numerados,
   Success Criteria, Key Entities). Leve TODAS as entidades, colunas, estados e regras do insumo para a
   spec ou para as notas que o plan vai usar; não invente campos que não estão lá.
2. `/speckit-clarify`. As decisões abaixo JÁ estão tomadas; não as pergunte de novo, registre-as em
   Clarifications com a data 2026-10-06:
   - RAM do ComfyUI: o worker sobe o limite do container para 28 GB só durante o job `comfyui` e devolve
     para 12 GB logo em seguida, inclusive em falha/cancelamento, e confere que voltou.
   - GPU: sem fila única com o OpenShorts; o job só começa com a GPU desocupada, senão espera na fila
     ("Aguardando a GPU ficar livre").
   - Voz é do perfil; o avatar pode ter uma voz padrão (`assets.voz_id`).
   - Produto é do perfil.
   - Candidatos não escolhidos são apagados 90 dias depois; o escolhido nunca.
   - Toda escolha de candidato é humana (não existe "auto"), exceto passos só de texto (ficha do produto,
     checagem de identidade), que vão direto e são editáveis.
   Perguntas ainda abertas (pode perguntar, no máximo 3 por spec): gravação original completa da pessoa
   real ou só a referência cortada (022); `url_loja`/preço/comissão já na 012 ou depois.
3. `/speckit-plan`. Pontos obrigatórios no plano:
   - Testes sem serviço real: fakes do ComfyUI e do shop-tts em `apps/api/tests/fakes/` e no
     `openshorts-fake` do e2e (como já existe para OpenShorts, Claude e TikTok).
   - Mudança de contrato do shop-tts (upload/download de arquivos e rota de importar voz aprovada) fica
     documentada em `contracts/` como dependência externa em `../comfyui-docker/tts_service/`; NÃO edite
     esse serviço nesta sessão, só descreva.
   - Acesso ao Docker para o ajuste de RAM: proponha o mecanismo mais restrito possível e sinalize o
     risco de segurança (montar o socket do Docker dá poder total no host). Eu decido.
   - Armazenamento: MinIO no HD (constitution 2.1.0), tabela `audios` irmã da `images`.
   - Contrato gerado (`npm run gen:contract`), migrations Alembic na sequência das existentes.
   - Chamadas ao Claude no registro de chamadas da 008.
4. `/speckit-tasks` e `/speckit-analyze`. Me mostre as inconsistências antes de seguir.
5. NÃO rode `/speckit-implement` sem eu pedir explicitamente.

## Ao terminar as três specs
- Atualize o backlog em `docs/visao.md` (021, 022 e 012 com status "spec pronta").
- Me dê um resumo: entidades criadas/alteradas por spec, migrations previstas, perguntas que ficaram abertas
  e riscos.

---

# Rodada 2: 011-roteiros-video-local (2026-10-08)

Cole numa sessão nova do Claude Code em `/home/sakai/Projects/tiktok-shop/SociMan`:

```text
Vamos especificar a 011 (roteiros com vídeo local) com o Spec Kit, a partir do insumo já decidido pelo dono.
Siga o CLAUDE.md do SociMan (um passo por vez, nada de código sem spec aprovada) e a constitution.

## Leia antes de começar
- docs/insumos/011-roteiros-video-local.md (o insumo; é um HANDOFF do pipeline que já gerou um vídeo aprovado).
- specs/010-cenas/data-model.md (a cena que esta spec ESTENDE: tomada_origem, cena_tomadas, Duplicar, status usada).
- specs/021-geracao-local/spec.md e data-model.md (a lista fechada de passos do FR-002 que esta spec AUMENTA,
  a trava de GPU, a regra "escolha sempre humana" que o modo automático altera só dentro do roteiro).
- specs/012-produtos-shop/data-model.md (ponte cenas.produto_id / produto_variante_id) e
  specs/025-cadastro-padronizado/data-model.md (kit do avatar, vozes, assets.voz_id).
- specs/014-central-de-conteudos/data-model.md (o vídeo final vira conteúdo de origem video_proprio, como rascunho).
Referência técnica (só leitura, não copie código sem spec): ../comfyui-docker/pipeline/PADROES.md,
../comfyui-docker/pipeline/{run_storyboard,finalizar_hd}.py, ../comfyui-docker/runs/bia_vo/{gerar,refazer}.py,
../comfyui-docker/output/candidatos/candidato_01_bia_vestido_verde.txt.

## Numeração e branch
Número 11, short-name `roteiros-video-local`. Antes de criar a branch rode `git status` e me mostre; se houver
mudança não commitada, PARE e pergunte. Não faça commit sem eu pedir.

## Sequência (pare entre as etapas para eu aprovar)
1. /speckit-specify com o insumo (--number 11 --short-name roteiros-video-local). Leve TODAS as entidades,
   estados, portões, invalidações e regras aprendidas; o que estende a 010 e a 021 vira FR próprio desta spec
   ("a 010 ganha…", "a lista do FR-002 da 021 ganha…"), sem reescrever aquelas specs.
2. /speckit-clarify. Já decidido (registre em Clarifications com data 2026-10-08, não pergunte de novo):
   - portões aprovados por dono ou membro; histórico registra quem;
   - roteiro com um ou vários produtos (roteiro_produtos);
   - modo automático escolhe a opção 1, autor "sistema (automático)", só dentro do roteiro;
   - no automático o vídeo final vai para a 014 como RASCUNHO; publicar/agendar segue a aprovação humana;
   - formato único: voice over (fala na câmera e lip-sync fora do escopo).
   Abertas (no máximo 3 perguntas): limite de cenas por roteiro; retenção das tomadas não usadas.
3. /speckit-plan. Obrigatório no plano:
   - fakes do ComfyUI (bloco keyframe/clipe/upscale devolvendo imagem e vídeo pequenos) e do shop-tts
     (/tts_paragraph com tempos) nos testes e no e2e; nenhum teste chama GPU real;
   - mídia de vídeo nos candidatos da 021 (video_key no bucket de vídeos + miniatura);
   - montagem (ffmpeg) no worker, sem GPU, fora da trava de GPU; acabamento dentro da trava;
   - o dicionário de pronúncia vira tabela por perfil e passa a ir no pedido ao shop-tts (mudança de contrato
     em contracts/, dependência externa no ../comfyui-docker; NÃO edite o comfyui-docker nesta sessão);
   - contrato gerado (npm run gen:contract) e migrations Alembic na sequência das existentes.
4. /speckit-tasks e /speckit-analyze; me mostre as inconsistências.
5. NÃO rode /speckit-implement sem eu pedir.

Ao terminar: atualize o backlog em docs/visao.md (011 com status "spec pronta") e me dê o resumo
(entidades novas e estendidas, passos novos da 021, portões e estados, migrations, perguntas abertas, riscos).
```
