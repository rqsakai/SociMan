import { useQuery } from "@tanstack/react-query";
import { Wand2 } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { rotaEstudio, rotuloTipo, type TipoEstudio } from "@/lib/estudio";

const TIPOS: { tipo: TipoEstudio; chave: "avatares" | "cenarios" | "assets" | "cenas" | "produtos" | "vozes" }[] = [
  { tipo: "avatares", chave: "avatares" },
  { tipo: "cenarios", chave: "cenarios" },
  { tipo: "produtos", chave: "produtos" },
  { tipo: "vozes", chave: "vozes" },
  { tipo: "cenas", chave: "cenas" },
  { tipo: "assets", chave: "assets" },
];

// "Ver no AI Studio" (spec 029, US4, T031; FR-018): um atalho por tipo para a lista da agência já
// filtrada por este perfil base, com a contagem dos itens ativos (`GET /api/estudio/resumo`).
export function VerNoEstudio({ perfilId }: { perfilId: string }) {
  const resumo = useQuery({ queryKey: ["estudio", "resumo", perfilId], queryFn: () => api.estudio.resumo(perfilId) });
  return (
    <Card className="shadow-card" aria-labelledby="ver-no-estudio" data-testid="ver-no-estudio">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Wand2 className="size-4 text-muted-foreground" aria-hidden="true" />
          <h2 id="ver-no-estudio">Ver no AI Studio</h2>
        </CardTitle>
        <CardDescription>Avatares, cenários, produtos, vozes, cenas e assets com este perfil como perfil base.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {TIPOS.map(({ tipo, chave }) => (
            <li key={tipo}>
              <Link
                to={rotaEstudio(tipo, perfilId)}
                className="flex flex-col rounded-lg border p-3 transition-colors hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
                data-testid={`ver-no-estudio-${tipo}`}
              >
                <span className="text-xl font-bold tabular-nums">{resumo.data ? resumo.data[chave] : "—"}</span>
                <span className="text-sm text-muted-foreground">{rotuloTipo[tipo]}</span>
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
