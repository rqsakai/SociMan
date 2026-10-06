/*
 * Registro do ECharts do analytics (spec 019, R1; ADR 0002).
 *
 * Só o que os cards usam entra no build: import modular de `echarts/core|charts|components|
 * renderers`, nunca o pacote `echarts` inteiro (ele traria o `new Function` do GeoJSON, que a
 * CSP não aceita). Renderer SVG (o e2e lê o DOM) e locale PT-br. Este módulo só é alcançado pela
 * rota lazy de /app/metricas; o chunk sai com o nome `graficos` (vite.config.ts).
 */
import { BarChart, BoxplotChart, FunnelChart, HeatmapChart, LineChart, RadarChart, SankeyChart, ScatterChart } from "echarts/charts";
import type {
  BarSeriesOption,
  BoxplotSeriesOption,
  FunnelSeriesOption,
  HeatmapSeriesOption,
  LineSeriesOption,
  RadarSeriesOption,
  SankeySeriesOption,
  ScatterSeriesOption,
} from "echarts/charts";
import {
  AriaComponent,
  CalendarComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import type {
  AriaComponentOption,
  CalendarComponentOption,
  DatasetComponentOption,
  GridComponentOption,
  LegendComponentOption,
  MarkLineComponentOption,
  RadarComponentOption,
  TitleComponentOption,
  TooltipComponentOption,
  VisualMapComponentOption,
} from "echarts/components";
import * as echarts from "echarts/core";
import type { ComposeOption } from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import langPTbr from "echarts/i18n/langPT-br-obj.js";

echarts.use([
  HeatmapChart,
  LineChart,
  BarChart,
  ScatterChart,
  RadarChart,
  BoxplotChart,
  SankeyChart,
  FunnelChart,
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
  CalendarComponent,
  LegendComponent,
  TitleComponent,
  DatasetComponent,
  MarkLineComponent,
  AriaComponent,
  SVGRenderer,
]);

export const LOCALE = "PT-br";
echarts.registerLocale(LOCALE, langPTbr as unknown as Parameters<typeof echarts.registerLocale>[1]);

export type OpcoesGrafico = ComposeOption<
  | HeatmapSeriesOption
  | LineSeriesOption
  | BarSeriesOption
  | ScatterSeriesOption
  | RadarSeriesOption
  | BoxplotSeriesOption
  | SankeySeriesOption
  | FunnelSeriesOption
  | GridComponentOption
  | TooltipComponentOption
  | VisualMapComponentOption
  | CalendarComponentOption
  | LegendComponentOption
  | TitleComponentOption
  | DatasetComponentOption
  | MarkLineComponentOption
  | RadarComponentOption
  | AriaComponentOption
>;

export { echarts };
