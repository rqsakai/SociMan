import { defineConfig, minimal2023Preset } from "@vite-pwa/assets-generator/config";

// Gera os ícones do PWA a partir de pwa/icon.svg (`npm run icons`). O gerador
// grava ao lado do SVG; o script `icons` move os PNGs e o favicon para public/.
// O SVG já traz o fundo e a margem segura do maskable, então não há padding extra.
export default defineConfig({
  headLinkOptions: { preset: "2023" },
  preset: {
    ...minimal2023Preset,
    transparent: { ...minimal2023Preset.transparent, padding: 0 },
    maskable: { ...minimal2023Preset.maskable, padding: 0, resizeOptions: { background: "#0f172a" } },
    apple: { ...minimal2023Preset.apple, padding: 0, resizeOptions: { background: "#0f172a" } },
  },
  images: ["pwa/icon.svg"],
});
