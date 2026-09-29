import { createApiClient, toApiError } from "@sociman/contract";
import { useAuth } from "./authStore";

// Cliente sem interceptor: refresh autentica pelo cookie, e passar pelo
// authFetch causaria recursão no 401.
const bareApi = createApiClient();

// Refresh concorrente deduplicado: várias requisições que tomam 401 ao mesmo
// tempo compartilham UMA promessa de refresh (§7 do brief).
let refreshPromise: Promise<string | null> | null = null;

export function refreshSession(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function doRefresh(): Promise<string | null> {
  const epochAtStart = useAuth.getState().sessionEpoch;
  try {
    const data = await bareApi.auth.refresh();
    // Logout durante o refresh em voo: o epoch mudou → esta resposta pertence
    // a uma sessão que o usuário já encerrou. Aplicá-la "des-desfaria" o
    // logout na UI (até o próximo 401). Descarta.
    if (useAuth.getState().sessionEpoch !== epochAtStart) return null;
    useAuth.getState().setSession(data.accessToken, data.user);
    return data.accessToken;
  } catch {
    return null;
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

