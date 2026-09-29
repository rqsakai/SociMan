import { toApiError, type Corte } from "@sociman/contract";
import { refreshSession } from "./api";
import { useAuth } from "./authStore";

const enc = encodeURIComponent;

// Envio de corte por XHR (o fetch não informa o progresso do upload). Mesmo protocolo do
// authFetch: Bearer; num 401, um refresh e uma nova tentativa.
export function uploadCorte(
  perfilId: string,
  file: File,
  hookText: string,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<{ corte: Corte }> {
  const send = (token: string | null) =>
    new Promise<{ status: number; body: unknown }>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/perfis/${enc(perfilId)}/cortes`);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.responseType = "json";
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => resolve({ status: xhr.status, body: xhr.response as unknown });
      xhr.onerror = () => reject(new TypeError("Falha de rede no envio"));
      xhr.onabort = () => reject(new DOMException("Envio cancelado", "AbortError"));
      signal?.addEventListener("abort", () => xhr.abort(), { once: true });
      const form = new FormData();
      form.append("hookText", hookText);
      form.append("file", file);
      xhr.send(form);
    });

  return (async () => {
    let res = await send(useAuth.getState().accessToken);
    if (res.status === 401) {
      const token = await refreshSession();
      if (!token) {
        useAuth.getState().clearSession();
        throw toApiError(401, res.body);
      }
      onProgress(0);
      res = await send(token);
    }
    if (res.status < 200 || res.status >= 300) throw toApiError(res.status, res.body);
    return res.body as { corte: Corte };
  })();
}
