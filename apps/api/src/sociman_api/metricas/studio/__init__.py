"""Histórico do TikTok Studio (spec 020): importa os arquivos exportados pelo dono (ZIP da Visão
geral e de Seguidores, ou os CSVs soltos) como uma fonte separada da série da 016.

Só lê arquivos enviados: nenhuma rede, nenhum `publicacao`, nenhum MinIO, nada em disco
(guardas da spec 020 em `test_constitution_guards.py`). O `analytics/` importa `efetivo` (só
leitura), nunca o contrário.
"""
