import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

// Identifica o build no <html> (US3): o e2e de atualização compara antes/depois.
document.documentElement.dataset.build = import.meta.env.VITE_BUILD_ID ?? __BUILD_DATE__;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
