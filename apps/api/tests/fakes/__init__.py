"""Fakes das integrações HTTP da spec 006 (T019): YouTube, OpenShorts e Anthropic.

Padrão (vale para as trilhas A, B e C; nenhuma mexe em `tests/conftest.py` por causa disto):

- **Injeção do transporte.** Cada cliente (`canais/youtube.py`, `envios/openshorts.py`,
  `postagem/textos.py`) é criado por uma fábrica `get_*_client()` que aceita um
  `transport: httpx.BaseTransport | None` (None = rede de verdade). Nunca há chamada real nos
  testes, e nenhuma chave de verdade entra neles.
- **Nas rotas**, o cliente chega por dependência FastAPI (`Depends(get_*_client)`); o teste troca
  com `app.dependency_overrides[get_*_client] = lambda: <cliente com o fake>`. O `conftest` limpa
  os overrides depois de cada teste.
- **No agendador**, o `rodar(db, ...)` de cada trilha aceita o cliente por parâmetro com padrão
  de fábrica (`client=None` → `get_*_client()`); os testes chamam `rodar(db, client=fake)` direto,
  ou montam um `Agendador(trilhas=[Trilha(nome, intervalo, partial(rodar, client=fake))])`.
- **Um arquivo por fake**, `tests/fakes/<nome>_fake.py` (`youtube_fake.py`, `openshorts_fake.py`,
  `anthropic_fake.py`): uma classe com estado que monta um `httpx.MockTransport`, registra os
  pedidos (`.requests`, para os guardas do princípio I) e permite simular queda, erro e retorno.
  As respostas gravadas ficam em `tests/fixtures/<nome>/*.json`, sempre **sem a chave**.
- **Fixtures pytest** dos fakes ficam no próprio módulo do fake; o teste as importa
  explicitamente (`from fakes.youtube_fake import youtube_fake  # noqa: F401`): o pytest põe
  `tests/` no `sys.path` (modo `prepend`; `tests/` não tem `__init__.py`).
"""
