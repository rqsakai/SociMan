import { Link } from "react-router-dom";
import { emojisLabel, exemploTipoLabel, guiaPerfilPath, type Guia } from "@/lib/guia";

// "Vem do perfil" (spec 017, US1-2): o guia do perfil, só leitura, na tela do guia da conta. O da
// conta complementa este; em conflito, vale a conta.
export function GuiaHerdado({ perfil }: { perfil: Guia }) {
  const c = perfil.campos;
  const linhas: [string, string][] = [
    ["Tom de voz", c.tom],
    ["Faça", (c.faca ?? []).join(" · ")],
    ["Não faça", (c.naoFaca ?? []).join(" · ")],
    ["Vocabulário da casa", (c.vocabulario ?? []).join(" · ")],
    ["Palavras proibidas", (c.proibidas ?? []).join(" · ")],
    ["Emojis", [c.emojis ? emojisLabel[c.emojis] : "", (c.emojisPreferidos ?? []).join(" ")].filter(Boolean).join(" · ")],
    ["Hashtags fixas", (c.hashtagsFixas ?? []).join(" ")],
    ["Exemplos", (c.exemplos ?? []).map((e) => `${exemploTipoLabel[e.tipo]}: ${e.texto}`).join("\n")],
  ];
  const preenchidas = linhas.filter(([, v]) => v);
  return (
    <section aria-label="Vem do perfil" className="space-y-2 text-sm">
      {perfil.version === 0 || preenchidas.length === 0 ? (
        <p className="text-muted-foreground">O perfil ainda não tem guia; vale só o desta conta.</p>
      ) : (
        <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[12rem_1fr]">
          {preenchidas.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-xs font-semibold text-muted-foreground uppercase sm:pt-0.5">{k}</dt>
              <dd className="break-words whitespace-pre-wrap">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      <p>
        <Link to={guiaPerfilPath(perfil.perfilId)} className="text-primary underline-offset-4 hover:underline">
          Abrir o guia do perfil
        </Link>
        {perfil.version > 0 && <span className="text-muted-foreground"> · versão {perfil.version}</span>}
      </p>
    </section>
  );
}
