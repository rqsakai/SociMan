import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "@fontsource-variable/roboto";
import "./index.css";
import { iniciarTema } from "./lib/tema";

// Identifica o build no <html> (US3): o e2e de atualização compara antes/depois.
document.documentElement.dataset.build = import.meta.env.VITE_BUILD_ID ?? __BUILD_DATE__;

iniciarTema();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
