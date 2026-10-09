# Quickstart: validar a 025-cadastro-padronizado

Roteiro de validação. A §1 é automática (nenhum serviço real). As §2 a §5 são **manuais, com o dono**, na
GPU real, um passo por vez (comando → uma linha de explicação → rodar → ler a saída). Os pré-requisitos de
GPU, rede `gpu-local`, `dockerctl` e `gerador` são os da `specs/021-geracao-local/quickstart.md` §0.

## §0. Pré-requisitos (uma vez)

1. **021 pronta** e o quickstart dela passou (cena do cenário com GPU real).
2. **Constitution 4.3.0** com as 2 exceções do princípio VII:
   `grep -n "4.3.0\|lgpd" .specify/memory/constitution.md`.
3. **shop-tts com o contrato `v2` + `DELETE /v2/voices/{nome}`** (dependência externa,
   `contracts/shop-tts-025.md`). **Verificar** (de dentro do `gerador`, que está na `gpu-local`):
   ```bash
   docker compose exec gerador python -c "import httpx;print(httpx.get('http://shop-tts:8200/health').json())"
   ```
4. **Migration:** `docker compose exec api uv run alembic current` mostra `0021_cadastro_padronizado`.

## §1. Automático

```bash
npm run test:api                                   # pytest na stack efêmera (fakes da 021 + 025)
docker compose exec api uv run ruff check .
npm run gen:contract && npm run check:web          # contrato regenerado, typecheck, build, CSP, segredos
npm run test:e2e -- e2e/cadastro-padronizado.spec.ts
```
**Esperado:** tudo verde; `check:contract` sem divergência.

## §2. Kit de um avatar sintético (US1, US6)

1. No perfil de teste, **Assets → Novo → Avatar** "Teste Kit".
   **Verificar:** a seção "Kit padrão" mostra só "Rosto de origem" aberto.
2. Pedir o rosto de origem com uma descrição de pessoa adulta (inglês).
   **Verificar:** "Aguardando a GPU ficar livre" ou "Gerando opção i de 4"; depois, 4 opções.
3. Tentar uma descrição com "teen". **Verificar:** recusa "Menores de idade não são permitidos", sem job em
   `docker compose logs gerador`.
4. Escolher uma opção e seguir: frontal (2), 3/4 (2 pares: cada opção mostra esquerda e direita), corpo-base (2).
   **Verificar:** os 5 slots preenchidos; "Checagem de identidade" roda sozinha; notas por slot e a
   descrição para prompts em inglês; situação `completo` ou `atencao`.
5. **Verificar no Assistente de IA → Registro:** uma chamada `avatar.identidade` com custo.
6. Refazer o `rosto_34_esq` e escolher. **Verificar:** o anterior arquivado (Mostrar arquivados), as notas
   sumiram, nova checagem pedida; no Histórico, as duas versões.

## §3. Voz do perfil (US2, US3)

1. **Perfil → Vozes → Nova voz**, origem "Gravação", tom "vendas animada".
2. Tentar gerar sem consentimento. **Verificar:** "Registre o consentimento da pessoa antes de usar a gravação".
3. Registrar o consentimento (nome, data, observação) e enviar uma gravação de 15–30 s.
   **Verificar:** a análise com os avisos (ex.: áudio do WhatsApp) e até 3 candidatos com duração entre 8 e
   13 s, transcrição e teste.
4. Escolher um candidato. **Verificar:** `aprovada`; em até 1 min, "Sincronizada em …"; no shop-tts:
   ```bash
   docker compose exec gerador python -c "import httpx;print(list(httpx.get('http://shop-tts:8200/voices').json()))"
   ```
   lista `v_<32 hex>` (o `ttsId` da tela), não o nome da voz.
5. **Testar** com um texto livre. **Verificar:** o player toca a narração.
6. No avatar "Teste Kit", escolher a voz como **voz padrão**. **Verificar:** a voz mostra "Usada por: Teste Kit".

## §4. Looks, poses e cenário (US4, US5)

1. No avatar com kit, **Gerar look** "Cozinha" (descrição da roupa) e **Gerar pose** "apontando para o
   produto" (com "quando usar"). **Verificar:** 2 opções cada; a escolhida aparece no look e na grade de
   poses com "gerado".
2. Cenário "Cozinha retrô" → **Cena** pelo prompt. **Verificar:** 2 opções 768×1344 sem pessoas; situação
   `completo`. **Variação** "noite"; repetir "Noite" → recusa de rótulo.

## §5. Revogação (FR-033a) — só num avatar e numa voz de teste

1. Com o dono, abrir o avatar de **teste** com origem "Pessoa real" (ou a voz da §3) → **Revogar
   consentimento**. **Verificar:** a confirmação lista o que será apagado (imagens/áudios, candidatos,
   cenas afetadas).
2. Confirmar. **Verificar:** item arquivado; "Restaurar" e "Reverter" recusados; no histórico, a versão
   "revogado" sem mídia; para a voz, em até 1 min, `v_<…>` some de `GET /voices`.
3. **Verificar o evento** (sem dados pessoais na saída):
   ```bash
   docker compose exec postgres psql -U sociman -c "select type, occurred_at, details->>'excecao', details->>'imagens', details->>'audios' from security_events where type = 'eliminacao_lgpd' order by occurred_at desc limit 1"
   ```
4. Como membro, tentar revogar. **Verificar:** botão ausente e 403 pela API.
