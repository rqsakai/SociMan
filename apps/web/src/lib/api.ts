import { createApiClient, toApiError, type User } from "@sociman/contract";
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

// Coordenação ENTRE abas (o single-flight acima só vale dentro de uma). O
// cookie de renovação é do navegador inteiro e gira a cada uso: duas abas (ou
// aba + PWA) renovando juntas faziam a segunda apresentar o token já girado, e
// o servidor tratava como roubo. Agora a renovação roda sob um Web Lock, e quem
// renova publica o access token novo no canal; quem esperava o lock reaproveita
// esse token em vez de girar de novo. O refresh token continua só no cookie
// HttpOnly: o canal leva só o access token (que já vive em memória).
const REFRESH_LOCK = "sociman-refresh";
type Shared = { token: string; user: User; at: number };
let shared: Shared | null = null;

const channel: BroadcastChannel | null =
  typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("sociman-auth");
channel?.addEventListener("message", (event: MessageEvent<Shared>) => {
  const data = event.data;
  if (data && typeof data.token === "string" && typeof data.at === "number") shared = data;
});

async function doRefresh(): Promise<RefreshResult> {
  const startedAt = Date.now();
  const epochAtStart = useAuth.getState().sessionEpoch;
  const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
  if (!locks) return refreshFromServer(epochAtStart);
  return locks.request(REFRESH_LOCK, () => {
    // Outra aba renovou enquanto esperávamos o lock: o token dela serve.
    const fresh = shared && shared.at >= startedAt ? shared : null;
    if (fresh) return adopt(fresh.token, fresh.user, epochAtStart);
    return refreshFromServer(epochAtStart);
  });
}

function adopt(token: string, user: User, epochAtStart: number): RefreshResult {
  // Logout durante o refresh em voo: o epoch mudou → esta resposta pertence
  // a uma sessão que o usuário já encerrou. Aplicá-la "des-desfaria" o
  // logout na UI (até o próximo 401). Descarta.
  if (useAuth.getState().sessionEpoch !== epochAtStart) return { status: "failed" };
  useAuth.getState().setSession(token, user);
  return { status: "ok", token };
}

async function refreshFromServer(epochAtStart: number): Promise<RefreshResult> {
  try {
    const data = await bareApi.auth.refresh();
    const result = adopt(data.accessToken, data.user, epochAtStart);
    if (result.status === "ok") {
      // Publica antes de soltar o lock: a próxima aba da fila já encontra o token.
      shared = { token: data.accessToken, user: data.user, at: Date.now() };
      channel?.postMessage(shared);
    }
    return result;
  } catch (err) {
    // fetch rejeita com TypeError quando não há rede (servidor desligado, fora
    // da rede de casa). Resposta de erro do servidor vira ApiError, não TypeError.
    return { status: err instanceof TypeError ? "offline" : "failed" };
  }
}

// Interceptor: anexa o Bearer; num 401 de requisição autenticada, tenta refresh
// UMA vez e repete UMA vez; se o refresh falhar, derruba a sessão local.
export const authFetch: typeof fetch = async (input, init) => {
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

