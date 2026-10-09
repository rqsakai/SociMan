# Specification Quality Checklist: Geração local com candidatos (021)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-06
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- 0 marcadores [NEEDS CLARIFICATION]: Q1 (FR-030) = A, `cenario.cena` como piloto; Q2 (FR-031) = A,
  `produto.recorte` direto (respostas do dono em 2026-10-06).
- Pré-requisito: emenda 4.2.0 → 4.3.0 da constitution (exceções nomeadas do princípio VII para a limpeza
  de 90 dias e a revogação LGPD da 025), 1ª tarefa da implementação.
- As 6 decisões do dono de 2026-10-06 estão em Clarifications e não devem ser perguntadas de novo.
- Os nomes dos motores (ComfyUI, shop-tts, Claude), os limites de RAM (28/12 GB) e os passos aparecem na
  spec porque são decisões e vocabulário do dono, não escolhas de implementação. Colunas, tipos, rotas
  dos serviços, rede e edge ficam só em "Notas para o plano".
- Riscos para o plano (Notas para o plano): limpeza de 90 dias x princípio VII e `images` sem delete;
  acesso do worker ao Docker (princípios V e VIII); `avatar.rostos_34` em pares x CHECK de uma imagem por
  opção.
