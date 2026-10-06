"""Pasta sintética da agência para os testes da spec 013 (nada da pasta real entra aqui).

`Agencia(tmp_path)` grava `shared/` e `clipes/` com os moldes da agência; cada método monta um
arquivo com parâmetros para o caso do teste. A fixture `agencia` aponta `AGENCIA_SHARED_DIR` e
`AGENCIA_CLIPES_DIR` para essas pastas (sem montagem), e `yt` troca a fábrica do YouTube da
importação pelo fake da 006.
"""

import io
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fakes.youtube_fake import YoutubeFake
from PIL import Image

from sociman_api import storage
from sociman_api.agencia import aplicar
from sociman_api.config import get_settings
from sociman_api.main import app

PW = "senha-forte-123"
UC = "UC" + "a" * 22
UC2 = "UC" + "b" * 22
UC3 = "UC" + "c" * 22


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args],
                   check=True, timeout=120)


def png(cor=(200, 30, 30, 255), tamanho=(300, 300), alfa: bool = False) -> bytes:
    im = Image.new("RGBA", tamanho, cor)
    if alfa:
        for x in range(20):
            for y in range(20):
                im.putpixel((x, y), (0, 0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def jpg(cor=(30, 120, 200), tamanho=(300, 300)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(buf, "JPEG")
    return buf.getvalue()


PERFIL_MD = """---
slug: {slug}
status: {status}
atualizado: 2026-10-01
---
# Perfil: {nome}

## 1. Identidade
- Nome do perfil: {nome}
- @ no YouTube: {yt}
- @ no TikTok: {tt}
- Idioma: pt-BR
- Data de início: 2026-09-28

## 2. Nicho
- Nicho principal: {nicho}
- Pilares de conteúdo (3 a 5): RPG, colecionáveis
- Fora do escopo (o que NÃO é deste perfil): política

## 3. Público
- Quem é (idade, gênero predominante, região): {publico}
- Dores e desejos:
- Por que assiste cortes deste nicho:
- Horários prováveis de consumo: Noite

## 4. Posicionamento e tom
- Promessa do perfil em 1 frase: A taverna pra relaxar
- Tom (ex.: polêmico, educativo, humor): {tom}
- Expressões da casa: {expressoes}
- Proibido (temas, palavras, tipos de corte): {proibido}

## 5. Estilo visual
- Legenda (fonte, cor, posição): pergaminho
- Filtro / moldura / marca: {estilo}

## 6. Monetização
- Modelo (programa de cortes, afiliado, TikTok Shop, parceria): Afiliado
- Produtos e marcas foco:
- CTA padrão: "Segue a taverna"

## 7. Metas
- Clipes por dia:
- Meta de 30 dias (seguidores, views, receita): A DEFINIR
- Meta de 90 dias:

## 8. Decisões e histórico
| Data | Decisão | Por quê |
|---|---|---|
{decisoes}
"""

FONTES_MD = """# Fontes: {slug}

Status possíveis: `autorizado` | `programa-de-cortes` | `pendente` | `negado` | `desconhecido`.

| Criador | Canal (ID ou link) | Status | Evidência (link, print ou contrato) | Regras do programa | Confirmado por | Data |
|---|---|---|---|---|---|---|
{linhas}
"""

REGISTRO_MD = """# Registro de clipes: {slug}

| ID | Data | Fonte (URL + trecho) | Título | Produto/CTA | Status | Motivo (se reprovado) | Postado (YT/TT) | Views 24h | Views 7d | Receita (R$) | Obs |
|---|---|---|---|---|---|---|---|---|---|---|---|
{linhas}
"""

PERSONA_MD = """# Persona: {nome}

## Descrição para prompts (inglês)
> {prompt}

## Cenários
- **Cozinha retrô:** {cenario}

## Imagens de referência (ingredientes no Flow)
| Look | Arquivo / origem | Uso |
|---|---|---|
| Cozinha, corpo inteiro | `shared/shop/persona/{imagem}` | cenas de cozinha |

## Voz
- Tom: animado, próximo.

## Regras de imagem
- Evitar textos em inglês no fundo.
"""


class Agencia:
    def __init__(self, raiz: Path):
        self.shared = raiz / "shared"
        self.clipes = raiz / "clipes"
        (self.shared / "perfis" / "_modelo").mkdir(parents=True)
        self.clipes.mkdir()
        (self.shared / "perfis" / "_modelo" / "perfil.md").write_text("# Perfil: <Nome>\n")
        (self.shared / "agencia.md").write_text("# Manual\n")

    def escrever(self, rel: str, dados: str | bytes) -> Path:
        p = self.shared / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(dados, bytes):
            p.write_bytes(dados)
        else:
            p.write_text(dados)
        return p

    def index(self, *slugs: str) -> None:
        linhas = "\n".join(f"| {s} | {s.title()} | nicho | ativo | 2026-09-28 | x |" for s in slugs)
        self.escrever("perfis/INDEX.md", "# Perfis\n\n| Slug | Nome | Nicho | Status | Início | "
                      f"Pasta |\n|---|---|---|---|---|---|\n{linhas}\n")

    def perfil(self, slug: str = "taverna-teste", nome: str = "Taverna Teste", **kw: Any) -> None:
        campos = {"slug": slug, "nome": nome, "status": "ativo",
                  "yt": f"@{slug.replace('-', '')} (https://www.youtube.com/@{slug.replace('-', '')})",
                  "tt": f"@{slug.replace('-', '')}", "nicho": "RPG e colecionáveis",
                  "publico": "Nerds de 18 a 40", "tom": "Humor descontraído",
                  "expressoes": '"Senta que tem lugar" · "Essa foi crit 1"',
                  "proibido": "NSFW, política", "estilo": "texto",
                  "decisoes": "| 2026-09-25 | Nome fechado | Disponível |\n"
                              "| 2026-09-28 | Começar | Pedido do dono |"} | kw
        self.escrever(f"perfis/{slug}/perfil.md", PERFIL_MD.format(**campos))

    def fontes(self, slug: str, *linhas: tuple[str, ...]) -> None:
        corpo = "\n".join("| " + " | ".join(ln) + " |" for ln in linhas)
        self.escrever(f"perfis/{slug}/fontes.md", FONTES_MD.format(slug=slug, linhas=corpo))

    def pesquisa(self, slug: str, secoes: dict[str, str]) -> None:
        corpo = "\n\n".join(f"## {t}\n{c}" for t, c in secoes.items())
        self.escrever(f"perfis/{slug}/pesquisa.md", f"# Pesquisa: {slug}\n\n{corpo}\n")

    def registro(self, slug: str, *ids: str, data: str = "2026-09-25") -> None:
        corpo = "\n".join(f"| {i} | {data} | https://www.youtube.com/watch?v=abcdefghijk (1:00–2:00)"
                          f" | Título do {i} | Segue | pronto | | | | | | obs {i} |" for i in ids)
        self.escrever(f"perfis/{slug}/registro-clipes.md",
                      REGISTRO_MD.format(slug=slug, linhas=corpo))

    def clipe(self, slug: str, ident: str, data: str = "2026-09-25", cor: str = "0x808080",
              valido: bool = True) -> Path:
        p = self.clipes / slug / data / f"{ident}.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        if not valido:
            p.write_text("isto não é vídeo\n" * 20)
            return p
        ffmpeg("-f", "lavfi", "-i", f"color=c={cor}:s=360x640:d=2:r=10", "-c:v", "libx264",
               "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(p))
        return p

    def persona(self, nome: str = "Achadinha", imagem: str = "achadinha.png",
                dados: bytes | None = None, prompt: str = "A cheerful pin-up woman.",
                cenario: str = "1950s kitchen.") -> bytes:
        self.escrever("shop/persona.md", PERSONA_MD.format(nome=nome, prompt=prompt,
                                                           cenario=cenario, imagem=imagem))
        dados = dados or png((10, 200, 10, 255))
        self.escrever(f"shop/persona/{imagem}", dados)
        return dados


@pytest.fixture(scope="module", autouse=True)
def _buckets():
    storage.ensure_buckets()


@pytest.fixture
def agencia(tmp_path, monkeypatch) -> Agencia:
    ag = Agencia(tmp_path / "agencia")
    monkeypatch.setattr(get_settings(), "agencia_shared_dir", str(ag.shared))
    monkeypatch.setattr(get_settings(), "agencia_clipes_dir", str(ag.clipes))
    return ag


@pytest.fixture
def yt() -> YoutubeFake:
    fake = YoutubeFake()
    app.dependency_overrides[aplicar.fabrica_youtube] = lambda: fake.client
    return fake


@pytest.fixture
def dono(client, make_user, login):
    user = make_user(role="dono", name="Dono")
    return user, login(client, user.email, PW)


@pytest.fixture
def membro(client, make_user, login):
    user = make_user(role="membro", name="Membro")
    return user, login(client, user.email, PW)


def previa(client, h, status: int = 201) -> dict:
    r = client.post("/api/agencia/previa", headers=h)
    assert r.status_code == status, r.text
    return r.json()


def confirmar(client, h, p: dict, escolhas: list[dict] | None = None, status: int = 202,
              **extra: Any) -> dict:
    r = client.post("/api/agencia/importacoes", headers=h,
                    json={"previaId": p["previaId"], "escolhas": escolhas or [], **extra})
    assert r.status_code == status, r.text
    if status != 202:
        return r.json()
    imp = client.get(f"/api/agencia/importacoes/{r.json()['id']}", headers=h)
    assert imp.status_code == 200, imp.text
    return imp.json()


def itens(p: dict, tipo: str | None = None, situacao: str | None = None,
          **kw: Any) -> list[dict]:
    out = [i for i in p["itens"] if (tipo is None or i["tipo"] == tipo)
           and (situacao is None or i["situacao"] == situacao)]
    for k, v in kw.items():
        out = [i for i in out if i.get(k) == v]
    return out


def um(p: dict, tipo: str, **kw: Any) -> dict:
    achados = itens(p, tipo, **kw)
    assert len(achados) == 1, [(i["tipo"], i["situacao"], i["origem"]) for i in itens(p, tipo)]
    return achados[0]


def importar(client, h, escolhas: list[dict] | None = None, **extra: Any) -> tuple[dict, dict]:
    p = previa(client, h)
    imp = confirmar(client, h, p, escolhas, **extra)
    assert imp["estado"] == "concluida", imp
    return p, imp
