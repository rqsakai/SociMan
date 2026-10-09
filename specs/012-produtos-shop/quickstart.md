# Quickstart: validar a 012-produtos-shop

Roteiro de validação. A §1 é automática (nenhum serviço real). As §2 e §3 são **manuais, com o dono**,
na GPU real, um passo por vez (comando → uma linha de explicação → rodar → ler a saída).

## §0. Pré-requisitos

1. **021 pronta e verde**, com a constitution 4.3.0 aplicada, a rede `gpu-local`, o `dockerctl` e o
   `gerador` de pé (quickstart da 021, §0). **Verificar:** `curl -s http://localhost:8180/api/integracoes`
   (logado) mostra `geracao.comfyui: "ok"`, `memoriaComfyui: "ok"`, `gerador: "ativo"`.
2. **Migration:** `docker compose exec api uv run alembic heads` mostra `0022_produtos_shop` como único head.
3. **Chave do Claude** no `.env` da raiz (`ANTHROPIC_API_KEY`; `GET /api/integracoes` mostra "configurada").
4. **Edge:** depois de mudar o `default.conf.template`, `docker compose restart edge`.

## §1. Automático (sem serviço real)

```bash
npm run test:api -- -k "produto or migration_0022 or cenas_prompt or constitution"
docker compose exec api uv run ruff check .
npm run gen:contract && npm run check:web
npm run test:e2e -- e2e/produtos.spec.ts
```
Cobre:
- estados e pendências;
- a ficha: 1 chamada, registro na 008 com `geracao_id`, recusa e saída inválida;
- os recortes direto e os flats com 2 opções e escolha humana (403 para MCP);
- "Refazer flat" e "Gerar outras";
- falha de GPU sem 2ª chamada ao Claude e RAM de volta a 12 GB (`dockerctl_fake`);
- aviso `flat_desatualizado`;
- limites (6 variantes, 512×512, 20 MB, formatos);
- arquivar/restaurar mantendo o status e reverter só pelo dono;
- a limpeza de 90 dias sem tocar imagem de variante;
- a ponte com as cenas (seletor, prompt, ingrediente, aviso, cenas antigas intactas);
- o MCP só leitura;
- a migration.

## §2. Manual com o dono: um produto de roupa (GPU real)

1. Na aba **Produtos** do perfil, "Novo produto": nome `shorts_canelado`, as 3 fotos de teste do pipeline
   (`../comfyui-docker/input/` ou as do dono) e a observação "shorts de cintura alta canelados, 3 cores,
   logo LS". **Verificar:**
   - em segundos, a ficha aparece com `ribbed knit`, uma cor por variante e `precisa_flat` ligado;
   - o Registro do assistente mostra a chamada `produto.ficha` com custo.
2. Acompanhar os passos: 3 recortes, depois 3 × 2 opções de flat. **Verificar:**
   - com o OpenShorts processando, aparece "Aguardando a GPU ficar livre";
   - durante o job, `docker inspect comfyui --format '{{.HostConfig.Memory}}'` mostra 28 GB e, ao fim, 12 GB.
3. Escolher um flat por variante; num deles, "Gerar outras" e escolher de novo. **Verificar:** a folha mostra
   originais | recortes | flats; o histórico do produto lista as escolhas com a geração.
4. Corrigir uma cor (ex.: `heather grey`), salvar e **Aprovar**. **Verificar:** origem "IA editada"; o
   produto aparece no seletor de uma cena; a cena monta o prompt com a frase da ficha e "Color: …", e o
   ingrediente é o recorte.
5. Editar a ficha do produto aprovado. **Verificar:** volta para `revisao`, some do seletor e o flat mostra
   "feito com a ficha anterior" quando a cor/material mudou.

## §3. Manual com o dono: falhas

1. Parar o ComfyUI (`docker compose -f ../comfyui-docker/docker-compose.yml stop comfyui`) e criar um
   produto. **Verificar:** a ficha chega; o recorte fica com espera/erro `servico_fora`; ao subir o ComfyUI e
   "Tentar de novo", o recorte sai **sem** nova linha `produto.ficha` no Registro.
2. Cancelar um flat em andamento. **Verificar:** RAM volta a 12 GB; o produto fica em `gerando` com o passo
   pendente.

Ao terminar, registrar no `CLAUDE.md` (seção nova "Produtos do Shop") o que mudou de comando ou armadilha.
