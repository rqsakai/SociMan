import { createApiClient, toApiError } from "@sociman/contract";
import { useAuth } from "./authStore";

// Cliente sem interceptor: refresh autentica pelo cookie, e passar pelo
// authFetch causaria recursão no 401.
const bareApi = createApiClient();

// Resultado do refresh. "offline" = o fetch nem chegou ao servidor (TypeError
// de rede); "failed" = o servidor respondeu erro (401, sem cookie etc.) ou a
// resposta foi descartada pelo epoch. Só o boot distingue os dois (US2).
export type RefreshResult =
  | { status: "ok"; token: string }
  | { status: "failed" }
  | { status: "offline" };

// Refresh concorrente deduplicado: várias requisições que tomam 401 ao mesmo
// tempo compartilham UMA promessa de refresh (§7 do brief).
let refreshPromise: Promise<RefreshResult> | null = null;

export function refreshSessionResult(): Promise<RefreshResult> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

export async function refreshSession(): Promise<string | null> {
  const result = await refreshSessionResult();
  return result.status === "ok" ? result.token : null;
}

async function doRefresh(): Promise<RefreshResult> {
  const epochAtStart = useAuth.getState().sessionEpoch;
  try {
    const data = await bareApi.auth.refresh();
    // Logout durante o refresh em voo: o epoch mudou → esta resposta pertence
    // a uma sessão que o usuário já encerrou. Aplicá-la "des-desfaria" o
    // logout na UI (até o próximo 401). Descarta.
    if (useAuth.getState().sessionEpoch !== epochAtStart) return { status: "failed" };
    useAuth.getState().setSession(data.accessToken, data.user);
    return { status: "ok", token: data.accessToken };
  } catch (err) {
    // fetch rejeita com TypeError quando não há rede (servidor desligado, fora
    // da rede de casa). Resposta de erro do servidor vira ApiError, não TypeError.
    return { status: err instanceof TypeError ? "offline" : "failed" };
  }
}

// Interceptor: anexa o Bearer; num 401 de requisição autenticada, tenta refresh
// UMA vez e repete UMA vez; se o refresh falhar, derruba a sessão local.
const authFetch: typeof fetch = async (input, init) => {
  const token = useAuth.getState().accessToken;
  // O cliente gerado passa um Request pronto; o corpo só pode ser lido uma
  // vez, então guarda uma cópia para o retry.
  const request = new Request(input, init);
  const retry = token ? request.clone() : null;
  if (token && !request.headers.has("authorization")) {
    request.headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(request);

  if (res.status === 401 && retry) {
    const newToken = await refreshSession();
    if (!newToken) {
      useAuth.getState().clearSession();
      return res;
    }
    retry.headers.set("Authorization", `Bearer ${newToken}`);
    return fetch(retry);
  }

  if (res.status === 403) {
    // Troca de senha pendente: o servidor recusa tudo exceto me, change e
    // logout. Marca o usuário e o RequireAuth redireciona.
    const body = await res.clone().json().catch(() => null);
    if (toApiError(403, body).code === "password_change_required") {
      useAuth.getState().requirePasswordChange();
    }
  }

  return res;
};

export const api = createApiClient({ fetchFn: authFetch });

