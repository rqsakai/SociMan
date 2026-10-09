"""Configuração local do coletor: `~/.config/sociman-coletor/` (contracts/coletor.md,
"Configuração").

- `config.toml`: `api_url`, `ca_cert`, `chrome_bin`, `perfil_dir`, `[limites]`, `[log]`,
  `screenshots`.
- `token`: o `scol_…`, uma linha, modo 600. Com modo mais aberto o coletor recusa iniciar
  (`token_permissao`). O token nunca vem por argumento nem por variável de ambiente (apareceria
  em `ps`), e nunca é impresso: `Segredo` mascara o `repr` e o `str`.
"""

from __future__ import annotations

import os
import stat
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

DIR_PADRAO = Path("~/.config/sociman-coletor")
ARQUIVO_CONFIG = "config.toml"
ARQUIVO_TOKEN = "token"
ARQUIVO_PARAR = "PARAR"
ARQUIVO_ESTADO = "estado.json"
PASTA_PERFIL = "chrome-profile"
PREFIXO_TOKEN = "scol_"


class ErroConfig(Exception):
    """Configuração local inválida. `codigo` é curto e estável (vai para o log e o autoteste)."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


class Segredo(str):
    """Um `str` que nunca se mostra: `repr` e `str` saem mascarados; `revelar()` dá o valor."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"Segredo('{self._mascara()}')"

    def __str__(self) -> str:
        return self._mascara()

    def _mascara(self) -> str:
        bruto = str.__str__(self)
        if bruto.startswith(PREFIXO_TOKEN):
            return PREFIXO_TOKEN + "****"
        return "****"

    def revelar(self) -> str:
        return str.__str__(self)


class LimitesLocais(BaseModel):
    """Opcionais, com os mesmos nomes do servidor. `None` = usar o do servidor."""

    model_config = ConfigDict(extra="forbid")

    paginas_dia: int | None = Field(default=None, ge=1)
    imagens_dia: int | None = Field(default=None, ge=0)
    pausa_min_s: int | None = Field(default=None, ge=1)
    pausa_max_s: int | None = Field(default=None, ge=1)
    janela_inicio: int | None = Field(default=None, ge=0, le=23)
    janela_fim: int | None = Field(default=None, ge=0, le=23)


class ConfigLog(BaseModel):
    # `validate_default`: o padrão com `~` também passa pelo `_expandir` (sem isso o `~` ficava
    # literal e virava uma pasta `~/` no diretório atual).
    model_config = ConfigDict(extra="forbid", validate_default=True)

    nivel: str = "INFO"
    arquivo: Path | None = Path("~/.local/state/sociman-coletor/coletor.log")

    @field_validator("arquivo", mode="before")
    @classmethod
    def _expandir(cls, v: object) -> object:
        if isinstance(v, str) and v:
            return Path(v).expanduser()
        if v == "":
            return None
        if isinstance(v, Path):
            return v.expanduser()
        return v


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_url: str = "https://192.168.86.47:8543"
    ca_cert: Path | None = None
    chrome_bin: str | None = None
    perfil_dir: Path = DIR_PADRAO / PASTA_PERFIL
    screenshots: bool = False
    limites: LimitesLocais = Field(default_factory=LimitesLocais)
    log: ConfigLog = Field(default_factory=ConfigLog)

    # Preenchidos por `carregar`; não vêm do TOML.
    dir: Path = DIR_PADRAO

    @field_validator("ca_cert", "perfil_dir", mode="before")
    @classmethod
    def _expandir(cls, v: object) -> object:
        if isinstance(v, str) and v:
            return Path(v).expanduser()
        if v == "":
            return None
        if isinstance(v, Path):
            return v.expanduser()
        return v

    @field_validator("api_url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("https://", "http://")):
            raise ValueError("api_url precisa começar com https:// ou http://")
        return v

    @property
    def caminho_token(self) -> Path:
        return self.dir / ARQUIVO_TOKEN

    @property
    def caminho_parar(self) -> Path:
        return self.dir / ARQUIVO_PARAR

    @property
    def caminho_estado(self) -> Path:
        return self.dir / ARQUIVO_ESTADO


def diretorio(dir_config: Path | str | None = None) -> Path:
    """A pasta de configuração: o argumento, ou `~/.config/sociman-coletor`."""
    return Path(dir_config).expanduser() if dir_config else DIR_PADRAO.expanduser()


def carregar(dir_config: Path | str | None = None) -> Config:
    """Lê `config.toml` (ausente = padrões). Erro de formato → `ErroConfig("config_invalida")`."""
    pasta = diretorio(dir_config)
    caminho = pasta / ARQUIVO_CONFIG
    dados: dict = {}
    if caminho.exists():
        try:
            dados = tomllib.loads(caminho.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            raise ErroConfig("config_invalida", f"config.toml ilegível: {exc}") from exc
    try:
        cfg = Config.model_validate({**dados, "dir": pasta})
    except ValueError as exc:
        raise ErroConfig("config_invalida", f"config.toml inválido: {exc}") from exc
    if cfg.perfil_dir == DIR_PADRAO / PASTA_PERFIL:
        cfg.perfil_dir = pasta / PASTA_PERFIL
    return cfg


def conferir_permissao(caminho: Path, maximo: int = 0o600) -> None:
    """Recusa o arquivo quando alguém além do dono pode lê-lo (modo mais aberto que `maximo`)."""
    try:
        modo = stat.S_IMODE(caminho.stat().st_mode)
    except FileNotFoundError as exc:
        raise ErroConfig("token_ausente", f"arquivo de token não encontrado: {caminho}") from exc
    if modo & ~maximo:
        raise ErroConfig(
            "token_permissao",
            f"o arquivo de token tem modo {modo:o}; precisa ser {maximo:o} (chmod 600)",
        )


def ler_token(cfg: Config) -> Segredo:
    """O token do arquivo `token` (modo 600, uma linha, prefixo `scol_`)."""
    caminho = cfg.caminho_token
    conferir_permissao(caminho)
    try:
        texto = caminho.read_text(encoding="utf-8").strip().splitlines()
    except OSError as exc:
        raise ErroConfig("token_ilegivel", "não foi possível ler o arquivo de token") from exc
    valor = texto[0].strip() if texto else ""
    if not valor.startswith(PREFIXO_TOKEN) or len(valor) < 20:
        raise ErroConfig("token_formato", "o arquivo de token não tem um token scol_ válido")
    return Segredo(valor)


def tem_tela(ambiente: dict[str, str] | None = None) -> bool:
    """Há sessão gráfica? (`DISPLAY` ou `WAYLAND_DISPLAY`). Sem ela o coletor não abre o Chrome."""
    env = os.environ if ambiente is None else ambiente
    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))
