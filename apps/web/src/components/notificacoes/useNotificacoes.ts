import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import {
  browserNotificationsSupported,
  browserPref,
  lastShownId,
  notificacoesKey,
  POLL_HIDDEN_MS,
  POLL_VISIBLE_MS,
  setBrowserPref,
  setLastShownId,
  setShownBaseline,
  showBrowserNotification,
  type Notificacao,
} from "@/lib/notificacoes";

interface NotificacoesData {
  items: Notificacao[];
  naoLidas: number;
}

const KEEP = 50;
const CHANNEL = "sociman-notificacoes";

function useVisible(): boolean {
  const [visible, setVisible] = useState(() => typeof document === "undefined" || document.visibilityState === "visible");
  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);
  return visible;
}

// Sino (spec 006, T052): polling de GET /api/notificacoes?after=<id> (20 s visível, 60 s em
// segundo plano, refetch ao focar), a contagem de não lidas, marcar lidas e a notificação do
// navegador para as novas, só com o app aberto. Duas abas não mostram a mesma: o último id
// mostrado fica no localStorage e as abas se avisam por BroadcastChannel.
export function useNotificacoes() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const visible = useVisible();
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(() =>
    browserNotificationsSupported() ? Notification.permission : "unsupported",
  );
  const [browserOn, setBrowserOn] = useState(() => browserPref());
  const shown = useRef(new Set<number>());
  const channel = useRef<BroadcastChannel | null>(null);

  const query = useQuery({
    queryKey: notificacoesKey,
    queryFn: async (): Promise<NotificacoesData> => {
      const prev = queryClient.getQueryData<NotificacoesData>(notificacoesKey);
      const newest = prev?.items[0]?.id;
      if (newest === undefined) return api.notificacoes.list({ limit: 30 });
      const res = await api.notificacoes.list({ after: newest, limit: 30 });
      return { items: [...res.items, ...prev!.items].slice(0, KEEP), naoLidas: res.naoLidas };
    },
    refetchInterval: visible ? POLL_VISIBLE_MS : POLL_HIDDEN_MS,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
    staleTime: 5_000,
  });

  // Lista completa de novo (ao abrir o sino): pega as marcadas como lidas em outra aba.
  const reload = useCallback(async () => {
    const data = await api.notificacoes.list({ limit: 30 });
    queryClient.setQueryData<NotificacoesData>(notificacoesKey, data);
  }, [queryClient]);

  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const bc = new BroadcastChannel(CHANNEL);
    bc.onmessage = (e: MessageEvent<{ shown?: number }>) => {
      if (typeof e.data?.shown === "number") shown.current.add(e.data.shown);
    };
    channel.current = bc;
    return () => {
      bc.close();
      channel.current = null;
    };
  }, []);

  // Clique numa notificação mostrada pelo service worker (public/sw-notificacoes.js).
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const onMessage = (e: MessageEvent<{ type?: string; link?: string }>) => {
      if (e.data?.type === "sociman:abrir" && typeof e.data.link === "string") void navigate(e.data.link);
    };
    navigator.serviceWorker.addEventListener("message", onMessage);
    return () => navigator.serviceWorker.removeEventListener("message", onMessage);
  }, [navigate]);

  const items = query.data?.items;
  useEffect(() => {
    if (!items || items.length === 0) return;
    const newest = items[0]!.id;
    const last = lastShownId();
    // Primeira leitura neste navegador: marca o ponto de partida sem despejar o histórico.
    if (last === 0 || !browserOn || permission !== "granted") {
      setLastShownId(newest);
      return;
    }
    const fresh = items.filter((n) => n.id > last && !n.lida && !shown.current.has(n.id)).slice(0, 3);
    setLastShownId(newest);
    for (const n of fresh.reverse()) {
      shown.current.add(n.id);
      channel.current?.postMessage({ shown: n.id });
      void showBrowserNotification(n, (link) => void navigate(link));
    }
  }, [items, browserOn, permission, navigate]);

  const marcarLidas = useCallback(
    async (target: { ids: number[] } | { todas: true }) => {
      const { naoLidas } = await api.notificacoes.marcarLidas(target);
      queryClient.setQueryData<NotificacoesData>(notificacoesKey, (prev) =>
        prev
          ? {
              naoLidas,
              items: prev.items.map((n) => ("todas" in target || target.ids.includes(n.id) ? { ...n, lida: true } : n)),
            }
          : prev,
      );
    },
    [queryClient],
  );

  // Liga/desliga o aviso do navegador; ligar pede a permissão (precisa de gesto do usuário).
  const toggleBrowser = useCallback(async () => {
    if (!browserNotificationsSupported()) return;
    if (browserOn) {
      setBrowserPref(false);
      setBrowserOn(false);
      return;
    }
    let result = Notification.permission;
    if (result === "default") result = await Notification.requestPermission();
    setPermission(result);
    if (result === "granted") {
      setShownBaseline(items?.[0]?.id ?? 0);
      setBrowserPref(true);
      setBrowserOn(true);
    }
  }, [browserOn, items]);

  return {
    items: query.data?.items ?? [],
    naoLidas: query.data?.naoLidas ?? 0,
    loading: query.isPending,
    error: query.error,
    reload,
    marcarLidas,
    browser: { supported: permission !== "unsupported", permission, on: browserOn && permission === "granted", toggle: toggleBrowser },
  };
}
