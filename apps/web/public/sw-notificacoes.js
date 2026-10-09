// Importado pelo service worker gerado (vite.config.ts, workbox.importScripts). Spec 006, R11:
// o clique numa notificação do SociMan foca uma janela aberta do app e pede para ela navegar até
// o link; sem janela aberta, abre uma nova no link.
self.addEventListener("notificationclick", (event) => {
  const link = (event.notification.data && event.notification.data.link) || "/app";
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      const client = clients.find((c) => new URL(c.url).origin === self.location.origin);
      if (client) {
        client.postMessage({ type: "sociman:abrir", link });
        return client.focus();
      }
      return self.clients.openWindow(link);
    }),
  );
});
