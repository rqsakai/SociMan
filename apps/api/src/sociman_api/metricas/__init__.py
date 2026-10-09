"""Métricas das redes (spec 016): só leitura (princípio I); genérico, sem HTTP.

Chega ao leitor da rede só por `publicacao.registro.leitor_para`, e ao token só por
`publicacao.conexoes.token_valido`. Nunca importa `publicacao.tiktok`, a trilha, o service nem o
executor de publicação (guardas da spec 016).
"""
