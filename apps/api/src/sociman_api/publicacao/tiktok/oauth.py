"""Login Kit da TikTok (research R1 a R3): URL de autorização, PKCE, troca do código, refresh,
revogação e `user/info`. Toda chamada HTTP passa por `cliente.py` (lista fechada, `redact`).

Nada aqui registra código, verifier ou token: eles entram e saem como valores de retorno.
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from sociman_api.config import Settings, get_settings
from sociman_api.publicacao.tiktok.cliente import AUTORIZAR_URL, TikTokCliente

__all__ = ["AUTORIZAR_URL", "Identidade", "Tokens", "code_challenge", "consultar_criador",
           "escopos", "identidade", "novo_code_verifier", "novo_state", "renovar", "revogar",
           "trocar_codigo", "url_autorizacao"]

TOKEN = "/v2/oauth/token/"
REVOKE = "/v2/oauth/revoke/"
USER_INFO = "/v2/user/info/"
CREATOR_INFO = "/v2/post/publish/creator_info/query/"
CAMPOS_USUARIO = "open_id,username,display_name,avatar_url"


@dataclass(frozen=True)
class Tokens:
    """Resposta da troca do código ou do refresh. Os tokens nunca aparecem no `repr`."""

    open_id: str
    escopos: tuple[str, ...]
    expira_em_s: int
    refresh_expira_em_s: int
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)


@dataclass(frozen=True)
class Identidade:
    open_id: str
    username: str | None  # sem `@`; None se a TikTok não informou
    display_name: str
    avatar_url: str | None = field(default=None, repr=False)  # link da CDN (expira)


def novo_state() -> str:
    """32 bytes aleatórios em base64url (R2)."""
    return secrets.token_urlsafe(32)


def novo_code_verifier() -> str:
    """64 caracteres base64url (R1; o PKCE aceita de 43 a 128)."""
    return secrets.token_urlsafe(48)


def code_challenge(verifier: str) -> str:
    """O `code_challenge` S256 do Login Kit Desktop, numa função só (R1).

    A doc do Desktop descreve o desafio como SHA-256 do verifier em **hex** (não o base64url do
    RFC 7636) [testar no sandbox, quickstart §2]: se o portal recusar, a troca é só aqui.
    """
    return hashlib.sha256(verifier.encode()).hexdigest()


def escopos(texto: str | None) -> list[str]:
    """`scope` da resposta (vírgulas ou espaços) → lista sem vazios, na ordem."""
    if not texto:
        return []
    return [e for e in texto.replace(",", " ").split() if e]


def url_autorizacao(state: str, redirect_uri: str, code_verifier: str | None = None,
                    s: Settings | None = None) -> str:
    """URL para o navegador do dono. Com `code_verifier` (Desktop), leva o PKCE."""
    s = s or get_settings()
    params = {
        "client_key": s.tiktok_client_key.get_secret_value(),
        "response_type": "code",
        "scope": ",".join(escopos(s.tiktok_scopes)),
        "redirect_uri": redirect_uri,
        "state": state,
    }
    if code_verifier is not None:
        params["code_challenge"] = code_challenge(code_verifier)
        params["code_challenge_method"] = "S256"
    return f"{AUTORIZAR_URL}?{urlencode(params)}"


# ---- pedidos (todos pelo `cliente.py`) ----

def _app(s: Settings) -> dict[str, str]:
    return {"client_key": s.tiktok_client_key.get_secret_value(),
            "client_secret": s.tiktok_client_secret.get_secret_value()}


def _tokens(dados: dict[str, Any]) -> Tokens:
    return Tokens(
        open_id=str(dados.get("open_id") or ""),
        escopos=tuple(escopos(dados.get("scope"))),
        expira_em_s=int(dados.get("expires_in") or 0),
        refresh_expira_em_s=int(dados.get("refresh_expires_in") or 0),
        access_token=str(dados["access_token"]),
        refresh_token=str(dados["refresh_token"]),
    )


def trocar_codigo(client: TikTokCliente, code: str, redirect_uri: str,
                  code_verifier: str | None = None) -> Tokens:
    """`authorization_code` → tokens. No Desktop, com o `code_verifier` do PKCE."""
    data = {**_app(get_settings()), "code": code, "grant_type": "authorization_code",
            "redirect_uri": redirect_uri}
    if code_verifier is not None:
        data["code_verifier"] = code_verifier
    return _tokens(client.api("POST", TOKEN, data=data))


def renovar(client: TikTokCliente, refresh_token: str) -> Tokens:
    """`refresh_token` → tokens novos (a TikTok pode rotacionar o refresh). `invalid_grant`
    sai como `ConexaoPerdida` (cliente)."""
    data = {**_app(get_settings()), "grant_type": "refresh_token",
            "refresh_token": refresh_token}
    return _tokens(client.api("POST", TOKEN, data=data))


def revogar(client: TikTokCliente, access_token: str) -> None:
    client.api("POST", REVOKE, data={**_app(get_settings()), "token": access_token})


def identidade(client: TikTokCliente, access_token: str) -> Identidade:
    dados = client.api("GET", USER_INFO, token=access_token,
                       params={"fields": CAMPOS_USUARIO})
    user = (dados.get("data") or {}).get("user") or {}
    username = str(user.get("username") or "").strip().lstrip("@") or None
    return Identidade(open_id=str(user.get("open_id") or ""), username=username,
                      display_name=str(user.get("display_name") or ""),
                      avatar_url=user.get("avatar_url") or None)


def consultar_criador(client: TikTokCliente, access_token: str) -> dict[str, Any]:
    """`creator_info/query` cru (`data`): usado na tela do Publicar e como plano B da
    identidade quando o `username` não vem no `user/info` (R3)."""
    dados = client.api("POST", CREATOR_INFO, token=access_token, json={})
    return dict(dados.get("data") or {})
