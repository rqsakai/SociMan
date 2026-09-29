import { describe, expect, it } from "vitest";
import { createImgproxyProcessor } from "../src/lib/adapters/imgproxy";

describe("imgproxy adapter", () => {
  it("monta URL unsafe com resize, formato e source em base64url", async () => {
    const images = createImgproxyProcessor({ publicPath: "/img" });
    const url = await images.url("s3://volans-dev/avatar.png", {
      width: 300,
      height: 200,
      fit: "fill",
      format: "webp",
    });
    expect(url).toMatch(/^\/img\/unsafe\/rs:fill:300:200\/f:webp\/[A-Za-z0-9_-]+$/);
    // o último segmento decodifica de volta para o source
    const encoded = url.split("/").at(-1)!;
    const decoded = Buffer.from(encoded, "base64url").toString();
    expect(decoded).toBe("s3://volans-dev/avatar.png");
  });

  it("sem opções, só o source; com key/salt, assina em vez de unsafe", async () => {
    const unsafe = createImgproxyProcessor({ publicPath: "/img" });
    expect(await unsafe.url("s3://b/k.png")).toMatch(/^\/img\/unsafe\/[A-Za-z0-9_-]+$/);

    const signed = createImgproxyProcessor({ publicPath: "/img", keyHex: "aabb", saltHex: "ccdd" });
    const url = await signed.url("s3://b/k.png");
    const [, , signature] = url.split("/");
    expect(signature).not.toBe("unsafe");
    expect(signature).toMatch(/^[A-Za-z0-9_-]{43}$/); // HMAC-SHA256 em base64url
    // determinístico para o mesmo path
    expect(await signed.url("s3://b/k.png")).toBe(url);
  });
});
