# Insumo da 030: clonagem de movimento

Pedido do dono em 2026-10-09. Este arquivo é insumo para o `/speckit-specify`, não é spec. Depende da 029 (o item "Movimentos" do AI Studio) e da 021 (geração local na GPU).

## Objetivo
Clonar o movimento de um vídeo de referência de **até 10 s** (uma pessoa apontando para o produto, girando, mostrando o tecido) para o avatar do kit (025), com mais precisão do que descrever o movimento em texto no prompt da cena.

## Decisões já tomadas (valem também aqui)
- **Tudo local, nada de API ou nuvem** (decisão do dono de 2026-10-01). O modelo roda no `comfyui` da RTX 5060 Ti de 16 GB, pela fila de GPU da 021.
- Só humano escolhe o resultado (opções da 021); a IA nunca publica.
- O vídeo de referência pode ter pessoa real. Na **2026-10-09**, a lista é a seguinte:
  - [ ] consentimento como o da 025, quando a pessoa do vídeo for identificável;
  - [ ] ou só a pose/esqueleto extraído, sem guardar o vídeo original?

  Decidir no clarify.

## Pesquisa necessária (fase 0 do plan)
- **Modelos candidatos:**
  - Wan 2.2 Animate 14B (já temos o Wan 2.2 14B no HD; ver `comfyui-docker/pipeline/MODELOS.md`);
  - UniAnimate-DiT, MimicMotion, Champ;
  - VACE (pose/depth control).
- **O que comparar em cada um:**
  - licença para uso comercial;
  - VRAM em 16 GB;
  - tempo por segundo de vídeo;
  - fidelidade do rosto e do produto (a lição da 2026-10-07: o LTX deformou o produto).
- **Extração de pose/esqueleto:** DWPose ou OpenPose, e a licença dos detectores. A InsightFace foi trocada pela MediaPipe na 2026-10-07 porque a InsightFace é só para pesquisa.
- **Formato de entrada:**
  - até 10 s;
  - corte automático para a resolução nativa do modelo (a lição da 2026-10-08: gerar na nativa, nada de 480p + upscale);
  - fps.

## O que a spec precisa cobrir
- **Biblioteca "Movimentos" no AI Studio (029):**
  - enviar um vídeo de até 10 s, cortar o trecho, prévia do esqueleto extraído;
  - rótulo e "quando usar";
  - perfil base opcional.
- **Passo novo na 021 (`movimento.clonar`):** avatar (kit, look ou pose) + movimento + cenário opcional → 2 opções → escolha humana → vira tomada da cena (010) ou vídeo próprio (014).
- **Cena (010):** campo "Movimento" opcional; quando há movimento, o prompt descreve só o resto.
- **Limpeza (90 dias) e LGPD (025):** o vídeo de referência entra na revogação quando houver consentimento.
- **Teste:** fake no pytest e no e2e e teste real na GPU com o dono.
