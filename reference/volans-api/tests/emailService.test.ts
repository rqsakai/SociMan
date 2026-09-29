import { afterEach, describe, expect, it, vi } from "vitest";
import { createResendEmailProvider } from "../src/lib/adapters/resendEmail";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("resend email provider (BYOK, fetch)", () => {
  it("faz POST autenticado ao endpoint do Resend com from/to/subject", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ id: "abc" }), { status: 200 }));

    const provider = createResendEmailProvider({
      apiKey: "re_test_key",
      from: "Volans <no-reply@volan.theitnerd.io>",
    });
    await provider.sendVerificationEmail("user@example.com", "https://app/verify-email?token=xyz");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("https://api.resend.com/emails");
    expect((init!.headers as Record<string, string>).Authorization).toBe("Bearer re_test_key");
    const body = JSON.parse(init!.body as string);
    expect(body.from).toContain("no-reply@volan.theitnerd.io");
    expect(body.to).toBe("user@example.com");
    expect(body.subject).toBe("Confirme seu e-mail");
    expect(body.text).toContain("verify-email?token=xyz");
  });

  it("lança erro quando o Resend responde não-2xx (não engole a falha)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("forbidden", { status: 403 }),
    );
    const provider = createResendEmailProvider({ apiKey: "bad", from: "x@y.z" });
    await expect(
      provider.sendPasswordResetEmail("user@example.com", "https://app/reset-password?token=t"),
    ).rejects.toThrow(/Resend 403/);
  });
});
