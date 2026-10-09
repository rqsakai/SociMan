import { useSyncExternalStore } from "react";

// Tema do app (spec 018, US1): escuro por padrão, claro ou "do sistema", guardado no aparelho.
// A classe `dark` no <html> liga os tokens escuros de index.css. A primeira pintura já sai
// certa: o index.html nasce com class="dark" e public/tema-inicial.js (externo, bloqueante,
// sem violar a CSP) aplica "claro"/"sistema" antes do bundle. A regra está duplicada lá.
export type Tema = "escuro" | "claro" | "sistema";

const CHAVE = "sociman:tema";
// cores da barra do navegador/PWA: iguais ao --background de cada tema (index.css)
const THEME_COLOR = { escuro: "#0f172a", claro: "#f0f2f5" } as const;

const listeners = new Set<() => void>();
const mqClaro = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;

function ler(): Tema {
  try {
    const v = window.localStorage.getItem(CHAVE);
    if (v === "claro" || v === "sistema" || v === "escuro") return v;
  } catch {
    // modo privado / dados bloqueados: fica o padrão
  }
  return "escuro";
}

let atual: Tema = typeof window !== "undefined" ? ler() : "escuro";

export function temaEfetivo(tema: Tema): "escuro" | "claro" {
  if (tema === "sistema") return mqClaro?.matches ? "claro" : "escuro";
  return tema;
}

function aplicar() {
  const efetivo = temaEfetivo(atual);
  document.documentElement.classList.toggle("dark", efetivo === "escuro");
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[efetivo]);
  listeners.forEach((l) => l());
}

export function setTema(tema: Tema) {
  atual = tema;
  try {
    window.localStorage.setItem(CHAVE, tema);
  } catch {
    // sem persistência: vale só nesta aba
  }
  aplicar();
}

// Chamado em main.tsx antes do primeiro render: confirma a classe e acompanha o sistema.
export function iniciarTema() {
  aplicar();
  mqClaro?.addEventListener("change", () => {
    if (atual === "sistema") aplicar();
  });
  // outra aba trocou o tema
  window.addEventListener("storage", (e) => {
    if (e.key === CHAVE) {
      atual = ler();
      aplicar();
    }
  });
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useTema(): { tema: Tema; efetivo: "escuro" | "claro" } {
  const tema = useSyncExternalStore(subscribe, () => atual);
  const efetivo = useSyncExternalStore(subscribe, () => temaEfetivo(atual));
  return { tema, efetivo };
}
