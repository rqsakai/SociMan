import type { Notificacao, NotificacaoTipo } from "@sociman/contract";

export type { Notificacao, NotificacaoTipo } from "@sociman/contract";

// Notificações do app (spec 006, R11): rótulos, preferências locais e a notificação do navegador.
// Só com o app aberto (aba ou instalado); sem Web Push (Q1 = A).

export const notificacoesKey = ["notificacoes"] as const;

export const tipoLabel: Record<NotificacaoTipo, string> = {
  envio_pronto: "Cortes prontos",
  envio_sem_clipes: "Sem clipes",
  envio_falhou: "Geração falhou",
  envio_confirmar_qualidade: "Confirmar qualidade",
  envio_momentos: "Momentos escolhidos",
  openshorts_fora: "SociShorts fora do ar",
  hora_de_postar: "Hora de postar",
  cota_youtube: "Cota do YouTube",
  canal_erro: "Erro no canal",
  // spec 014
  aprovacao_pedida: "Aprovação pedida",
  aprovacao_respondida: "Aprovação respondida",
  // spec 015
  rascunho_criado: "Rascunho criado",
  envio_publicado: "Publicado",
  envio_rede_falhou: "Envio para a rede falhou",
  envio_aguardando_vaga: "Aguardando vaga na rede",
  conexao_precisa_reconectar: "Conta precisa reconectar",
  // spec 016 (o link vem da API: /app/conteudos/{conteudoId}?conta={contaId})
  post_detectado: "Post detectado",
  vinculo_a_confirmar: "Escolha o post",
};

// Polling (R11): 20 s com a aba visível e 60 s em segundo plano.
export const POLL_VISIBLE_MS = 20_000;
export const POLL_HIDDEN_MS = 60_000;

// localStorage pode lançar (modo privado, dados bloqueados): tudo com try/catch.
const PREF_KEY = "sociman.notificacoes.navegador";
const LAST_KEY = "sociman.notificacoes.ultimaMostrada";

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // sem armazenamento: a preferência vale só nesta aba
  }
}

export const browserNotificationsSupported = () => typeof window !== "undefined" && "Notification" in window;

export function browserPref(): boolean {
  return readStorage(PREF_KEY) === "1";
}

export function setBrowserPref(on: boolean): void {
  writeStorage(PREF_KEY, on ? "1" : "0");
}

export function lastShownId(): number {
  return Number(readStorage(LAST_KEY) ?? 0) || 0;
}

export function setLastShownId(id: number): void {
  if (id > lastShownId()) writeStorage(LAST_KEY, String(id));
}

// Ponto de partida ao ligar o aviso: só as notificações posteriores aparecem no navegador. Sem
// nenhuma ainda, grava -1 (diferente de 0, que é "nunca leu" e não mostra nada).
export function setShownBaseline(id: number): void {
  writeStorage(LAST_KEY, String(id > 0 ? id : -1));
}

// Mostra a notificação do navegador: pelo service worker quando há um ativo (Android e app
// instalado), senão `new Notification`. O `tag` com o id evita duplicata entre abas.
export async function showBrowserNotification(n: Notificacao, onClick: (link: string) => void): Promise<void> {
  if (!browserNotificationsSupported() || Notification.permission !== "granted") return;
  const options: NotificationOptions = {
    body: n.corpo || tipoLabel[n.tipo],
    tag: `sociman-${n.id}`,
    icon: "/pwa-192x192.png",
    data: { link: n.link },
  };
  try {
    const registration = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : undefined;
    if (registration?.active) {
      await registration.showNotification(n.titulo, options);
      return;
    }
  } catch {
    // cai no `new Notification`
  }
  try {
    const notification = new Notification(n.titulo, options);
    notification.onclick = () => {
      window.focus();
      notification.close();
      onClick(n.link);
    };
  } catch {
    // Chrome no Android só aceita pelo service worker: sem ele, o aviso fica só no sino
  }
}
