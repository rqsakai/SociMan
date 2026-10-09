import { toApiError, type Conteudo, type Corte } from "@sociman/contract";
import { refreshSession } from "./api";
import { useAuth } from "./authStore";

const enc = encodeURIComponent;

// Envio multipart por XHR (o fetch não informa o progresso do upload). Mesmo protocolo do
// authFetch: Bearer; num 401, um refresh e uma nova tentativa.
export function uploadMultipart<T>(
  url: string,
  buildForm: () => FormData,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  const send = (token: string | null) =>
    new Promise<{ status: number; body: unknown }>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.responseType = "json";
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => resolve({ status: xhr.status, body: xhr.response as unknown });
      xhr.onerror = () => reject(new TypeError("Falha de rede no envio"));
      xhr.onabort = () => reject(new DOMException("Envio cancelado", "AbortError"));
      signal?.addEventListener("abort", () => xhr.abort(), { once: true });
      xhr.send(buildForm());
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
    return res.body as T;
  })();
}

export function uploadCorte(
  perfilId: string,
  file: File,
  hookText: string,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<{ corte: Corte }> {
  return uploadMultipart(
    `/api/perfis/${enc(perfilId)}/cortes`,
    () => {
      const form = new FormData();
      form.append("hookText", hookText);
      form.append("file", file);
      return form;
    },
    onProgress,
    signal,
  );
}

// Vídeo próprio (spec 014, US5): entra em Conteúdos como pronto, com o aviso "não é vertical".
export function uploadVideoProprio(
  perfilId: string,
  file: File,
  titulo: string,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<{ conteudo: Conteudo }> {
  return uploadMultipart(
    `/api/perfis/${enc(perfilId)}/conteudos/arquivo`,
    () => {
      const form = new FormData();
      if (titulo.trim()) form.append("titulo", titulo.trim());
      form.append("file", file);
      return form;
    },
    onProgress,
    signal,
  );
}
