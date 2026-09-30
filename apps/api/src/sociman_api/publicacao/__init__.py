"""Publicação em rede social (spec 015): o **único** pacote que fala com rede social.

Princípio I da constitution 4.0.0 ("Publicação só com decisão humana"): só destino aprovado e
agendado por dono humano, no modo que ele escolheu, com o interruptor ligado nos dois níveis.
Cada rede tem uma subpasta (`publicacao/tiktok/`); a parte genérica (trilha, conexões, cifra,
limites) só conhece o `ExecutorRede` (`executor.py`). Só `registro.py` importa
`publicacao.tiktok` (guarda R16.2).
"""
