import { partesComProibidas } from "@/lib/guia";

// Texto com as palavras proibidas do guia marcadas (spec 017, FR-004). A detecção é a mesma da API;
// a marca é só visual e tem nome acessível próprio.
export function ProibidasMarcadas({ texto, proibidas }: { texto: string; proibidas: string[] }) {
  if (proibidas.length === 0) return <>{texto}</>;
  return (
    <>
      {partesComProibidas(texto, proibidas).map((p, i) =>
        p.proibida ? (
          <mark
            key={i}
            title="Palavra proibida pelo guia"
            data-proibida=""
            className="rounded-sm bg-destructive/15 px-0.5 text-destructive underline decoration-wavy"
          >
            {p.texto}
          </mark>
        ) : (
          <span key={i}>{p.texto}</span>
        ),
      )}
    </>
  );
}
