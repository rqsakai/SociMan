/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/react" />

declare const __BUILD_DATE__: string;

// Locale do ECharts (spec 019): o pacote não traz tipos para os arquivos de i18n.
declare module "echarts/i18n/langPT-br-obj.js" {
  const locale: Record<string, unknown>;
  export default locale;
}
