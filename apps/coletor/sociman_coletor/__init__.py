"""sociman-coletor: o coletor de mercado do SociMan (spec 026, constitution IX).

Serviço Python no desktop do dono, fora do Docker. Controla o Chrome real num perfil dedicado,
navega como pessoa pelas páginas que o SociMan pediu e devolve o que viu pela API de ingestão.
Nunca fala com banco, armazenamento nem com a API interna assinada da rede.
"""

__version__ = "0.1.0"
PROTOCOLO = 1
