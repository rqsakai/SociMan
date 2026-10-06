"""Regras padrão de cada tipo de campo (research R2): o que vem com o SociMan.

Cada item é `(padrao_versao, texto)`. Mudou o texto, suba a versão: quem personalizou vê "O
padrão mudou desde a sua edição" (nada é trocado sozinho). A base fixa do prompt (formato,
limites, idioma exigido e segurança) fica em `prompt.py` e não é editável; estas regras só dizem
como escrever.
"""

PADROES: dict[str, tuple[int, str]] = {
    "avatar.descricao_prompt": (1, """\
Escreva a descrição do avatar para prompts de geração de imagem e vídeo (Flow/Veo), em inglês.
- Descreva a aparência fixa: idade aparente, rosto, cabelo, pele, corpo, roupa típica e \
acessórios marcantes, com detalhes concretos e visuais.
- Mantenha os traços que já estão no texto atual; mude só o que a instrução pedir.
- Frases curtas e diretas, em terceira pessoa, sem nome próprio, sem emoção passageira, sem \
cenário e sem ação (isso vem em cada cena).
- Nada de marcas registradas, pessoas reais ou celebridades."""),
    "avatar.tom_de_voz": (1, """\
Escreva o tom de voz do avatar: como ele fala nos vídeos.
- Diga o registro (informal, técnico, animado…), o ritmo, o vocabulário típico e as expressões \
que ele usa ou evita.
- Coerente com o perfil, o nicho e os bordões do kit.
- Curto: 2 a 4 frases."""),
    "avatar.regras_imagem": (1, """\
Escreva as regras de imagem do avatar, no idioma do perfil (pt-BR, salvo indicação).
- Uma regra por linha, em frases curtas que começam com "Sempre" ou "Nunca".
- Cubra o que mantém o avatar reconhecível entre as cenas (rosto, cabelo, roupa, proporções) e \
o que costuma dar errado na geração (mãos, texto na imagem, marcas).
- Não repita a descrição para prompts; complemente."""),
    "cenario.prompt_ambiente": (1, """\
Escreva o prompt do ambiente do cenário para geração de imagem e vídeo (Flow/Veo), em inglês.
- Descreva o lugar: tipo de ambiente, móveis e objetos principais, cores, luz, hora do dia e \
estilo de câmera.
- Concreto e visual; sem pessoas, sem ação e sem texto na imagem.
- Mantenha o que já está no texto atual; mude só o que a instrução pedir."""),
    "asset.nome": (1, """\
Sugira um nome curto para o asset da biblioteca.
- Uma linha, até 80 caracteres, sem aspas e sem ponto final.
- Descritivo: dá para achar o asset pelo nome na busca (ex.: "Cozinha clara de manhã")."""),
    "asset.descricao": (1, """\
Escreva as notas do asset: para que ele serve e quando usar.
- 1 a 3 frases, objetivas, para a equipe.
- Cite restrições de uso quando houver (ex.: só em vídeos de receita)."""),
    "perfil.bio": (1, """\
Escreva a descrição do perfil, no tom dele.
- Diga o tema, para quem é e o que a pessoa ganha seguindo.
- 1 a 3 frases curtas; pode usar um bordão do kit se couber de forma natural.
- Sem promessas exageradas e sem hashtags."""),
    "kit.bordoes": (1, """\
Sugira bordões novos para o perfil: frases curtas que o apresentador repete nos vídeos.
- Até 120 caracteres cada, fáceis de falar em voz alta, no tom do perfil.
- Diferentes entre si e dos bordões que já existem; mantenha o estilo dos já aceitos.
- Sem hashtags e sem emoji."""),
    "kit.series": (1, """\
Sugira nomes de séries (quadros recorrentes) para o perfil.
- Até 60 caracteres cada, curtos e memoráveis, que funcionem como título de uma sequência de \
vídeos (ex.: "Atalho do dia").
- Diferentes entre si e das séries que já existem; mantenha o estilo das já aceitas."""),
    "postagem.titulo": (1, """\
Escreva o título da postagem do corte.
- Até 100 caracteres, uma linha, sem aspas em volta e sem hashtags.
- Chamativo, mas fiel ao clipe: sem clickbait enganoso e sem inventar fatos.
- Siga os costumes da plataforma da conta."""),
    "postagem.descricao": (1, """\
Escreva a descrição da postagem do corte.
- 1 a 3 frases (o limite é 2.000 caracteres, mas o normal é bem menos), sem hashtags no texto.
- Combine com o título; não invente fatos, nomes, números ou promessas que não estão no clipe.
- Siga os costumes da plataforma da conta."""),
    "postagem.hashtags": (1, """\
Escolha as hashtags da postagem.
- De 3 a 8, cada uma começando com #, uma palavra só, sem espaço, sem acento e sem pontuação, \
em minúsculas, sem repetir.
- Misture o nicho do perfil com o tema do clipe; evite hashtags genéricas demais."""),
    "postagem.textos": (1, """\
Escreva os textos de postagem do corte: título, descrição e hashtags, coerentes entre si.
- Título: até 100 caracteres, sem aspas em volta, sem hashtags.
- Descrição: 1 a 3 frases, sem hashtags no texto.
- Hashtags: de 3 a 8, com #, uma palavra só, sem acento e sem pontuação, em minúsculas.
- Use os bordões e as séries quando couberem de forma natural; sem clickbait enganoso e sem \
inventar nada que não esteja no clipe."""),
    "guia.montar": (1, """\
Monte o guia de comunicação a partir da descrição da pessoa e do contexto do perfil.
- Tom: 1 a 3 frases dizendo como o perfil fala (registro, ritmo, energia, para quem).
- Faça e não faça: regras curtas e concretas, uma por item, que dê para conferir num texto.
- Vocabulário: palavras e expressões da casa; palavras proibidas: termos que nunca podem \
aparecer (uma palavra ou expressão por item, sem frases).
- Emojis: "nao", "moderado" ou "livre", e até 10 preferidos quando fizer sentido.
- Mantenha o que já está no guia atual e mude só o que a descrição pedir.
- No guia de uma conta, escreva só o que a conta acrescenta ou muda em relação ao \
<guia_perfil>; não repita o que já está lá."""),
    # Spec 010 (R10): as regras do shop-diretor para as cenas do Flow/Veo.
    "cena.acao": (1, """\
Escreva a ação da cena para o Flow/Veo, em inglês: o que acontece em até 8 segundos.
- Uma ação simples e contínua, com gestos claros (pegar, abrir, mostrar, apontar); nada de \
cortes nem de várias ações em sequência.
- Em terceira pessoa, no presente, sem descrever a aparência do avatar nem o cenário (isso vem \
dos assets).
- Com produto, diga como ele aparece e use "exactly as in the reference image".
- Nada de texto legível na imagem; nas cenas com fala, mãos longe do rosto."""),
    "cena.camera": (1, """\
Escreva o detalhe de câmera da cena, em inglês: ângulo, altura, lente ou foco.
- Curto (uma frase ou uma lista com vírgulas), complementando o plano e o movimento escolhidos.
- Nada de cortes nem de mudanças de plano dentro da cena."""),
    "cena.estilo": (1, """\
Escreva a iluminação e o estilo da cena, em inglês.
- Luz (natural, suave, de estúdio…), paleta de cores e acabamento (realista, retrô…).
- Vertical 9:16; coerente com o perfil e com os outros vídeos; sem texto na imagem."""),
    "cena.audio": (1, """\
Escreva o áudio ambiente da cena, em inglês: os sons do lugar e da ação.
- Curto e concreto (sons da cozinha, vapor, música suave…). A fala é um campo separado: não a \
repita aqui."""),
    "cena.ajustar": (1, """\
Ajuste a cena para o Flow/Veo, em inglês: proponha juntos a ação, o detalhe de câmera, a \
iluminação e estilo e o áudio ambiente, coerentes entre si.
- Siga a instrução; mantenha o que já funciona e mude só o necessário.
- Ação simples e contínua em até 8 segundos, gestos claros, produto "exactly as in the \
reference image", nada de texto legível, mãos longe do rosto nas cenas com fala.
- Não descreva a aparência do avatar nem o cenário: eles vêm dos assets e não mudam."""),
}
