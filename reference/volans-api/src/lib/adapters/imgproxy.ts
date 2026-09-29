// Adapter imgproxy (docker-compose): monta URLs no formato
//   {publicPath}/{assinatura|unsafe}/{opções}/{source em base64url}
// Com IMGPROXY_KEY/IMGPROXY_SALT (hex) as URLs são assinadas via HMAC-SHA256
// (WebCrypto — edge-compatible); sem eles, /unsafe — aceitável SÓ em dev, e o
// serviço restringe IMGPROXY_ALLOWED_SOURCES para não virar proxy aberto.
import { toBase64Url } from "../crypto";
import type { ImageOptions, ImageProcessor } from "../imaging";

export interface ImgproxyConfig {
  publicPath: string; // prefixo servido pelo edge, ex.: "/img"
  keyHex?: string;
  saltHex?: string;
}

function fromHex(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

function processingPath(source: string, opts?: ImageOptions): string {
  const parts: string[] = [];
  if (opts?.width || opts?.height) {
    parts.push(`rs:${opts.fit ?? "fit"}:${opts.width ?? 0}:${opts.height ?? 0}`);
  }
  if (opts?.format) parts.push(`f:${opts.format}`);
  const encodedSource = toBase64Url(new TextEncoder().encode(source));
  return `/${[...parts, encodedSource].join("/")}`;
}

export function createImgproxyProcessor(config: ImgproxyConfig): ImageProcessor {
  const signed = Boolean(config.keyHex && config.saltHex);

  async function sign(path: string): Promise<string> {
    const key = await crypto.subtle.importKey(
      "raw",
      fromHex(config.keyHex!) as BufferSource,
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const message = new Uint8Array([...fromHex(config.saltHex!), ...new TextEncoder().encode(path)]);
    const digest = await crypto.subtle.sign("HMAC", key, message as BufferSource);
    return toBase64Url(new Uint8Array(digest));
  }

  return {
    async url(source, opts) {
      const path = processingPath(source, opts);
      const prefix = signed ? await sign(path) : "unsafe";
      return `${config.publicPath}/${prefix}${path}`;
    },
  };
}
