// Interface do Image Processor do starter (análogo do Image Processor da
// Azion; imgproxy no docker-compose). O app não processa imagem — ele monta a
// URL que o edge serve (ex.: /img/...); o processamento acontece na borda.
// Implementação em adapters/imgproxy.ts, selecionada por IMAGE_DRIVER.
export interface ImageOptions {
  width?: number;
  height?: number;
  fit?: "fit" | "fill";
  format?: "webp" | "avif" | "jpg" | "png";
}

export interface ImageProcessor {
  // URL pública (relativa ao domínio do app) da imagem processada.
  // `source` é a origem: s3://bucket/chave (storage) ou URL http(s) permitida.
  url(source: string, opts?: ImageOptions): Promise<string>;
}
