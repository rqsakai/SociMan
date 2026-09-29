/*
 * /app/assistente-ia (spec 008, R12). Abas na URL (?aba=regras|registro|resumo):
 * - Regras (todos): os 13 tipos de campo com onde são usados, idioma, "Padrão"/"Personalizada" e a
 *   última alteração; o detalhe fica em /app/assistente-ia/regras/:tipo.
 * - Registro e Resumo (só o dono): as chamadas ao assistente e o gasto do mês.
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { PageHeading } from "@/components/PageHeading";
import { HeaderCard, usePageMeta } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "../../lib/authStore";
import { iaTiposQuery, idiomaLabel, type TipoCampo } from "../../lib/ia";
import { formatDateTime } from "../../lib/tz";
import { RegistroTab } from "./RegistroTab";
import { ResumoTab } from "./ResumoTab";

const ABAS = ["regras", "registro", "resumo"] as const;
type Aba = (typeof ABAS)[number];

export default function AssistenteIa() {
  usePageMeta({ title: "Assistente de IA" });
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const [params, setParams] = useSearchParams();
  const pedida = params.get("aba") as Aba | null;
  const aba: Aba = pedida && ABAS.includes(pedida) && (pedida === "regras" || isOwner) ? pedida : "regras";

  return (
    <div className="flex flex-col gap-6">
      <PageHeading
        title="Assistente de IA"
        description="As regras que a IA segue em cada tipo de campo, o registro das chamadas e o gasto do mês. A IA só propõe textos: nada é salvo sem o seu clique."
      />
      <Tabs value={aba} onValueChange={(v) => setParams(v === "regras" ? {} : { aba: v }, { replace: true })} className="gap-4">
        <TabsList aria-label="Seções do assistente de IA">
          <TabsTrigger value="regras">Regras</TabsTrigger>
          {isOwner && <TabsTrigger value="registro">Registro</TabsTrigger>}
          {isOwner && <TabsTrigger value="resumo">Resumo do mês</TabsTrigger>}
        </TabsList>
        <TabsContent value="regras">
          <RegrasTab />
        </TabsContent>
        {isOwner && (
          <TabsContent value="registro">
            <RegistroTab chamadaInicial={params.get("chamada")} />
          </TabsContent>
        )}
        {isOwner && (
          <TabsContent value="resumo">
            <ResumoTab />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}

const col = dataTableColumns<TipoCampo>();

function RegrasTab() {
  const tipos = useQuery(iaTiposQuery);
  const columns = useMemo(
    () =>
      col.columns([
        col.accessor("rotulo", {
          header: "Tipo de campo",
          cell: (c) => (
            <Link to={`/app/assistente-ia/regras/${c.row.original.id}`} className="font-medium underline-offset-2 hover:underline">
              {c.getValue()}
            </Link>
          ),
        }),
        col.accessor("onde", { header: "Onde é usado", meta: { className: "hidden md:table-cell text-muted-foreground" } }),
        col.accessor("idioma", { header: "Idioma", cell: (c) => idiomaLabel[c.getValue()] }),
        col.display({
          id: "estado",
          header: "Regras",
          cell: (c) => {
            const r = c.row.original.regras;
            return (
              <span className="flex flex-wrap gap-1">
                {r.personalizada ? <Badge className="bg-info text-info-foreground">Personalizada</Badge> : <Badge variant="secondary">Padrão</Badge>}
                {r.padraoAtualizado && <Badge variant="outline">O padrão mudou</Badge>}
              </span>
            );
          },
        }),
        col.display({
          id: "alterada",
          header: "Última alteração",
          meta: { className: "hidden sm:table-cell text-muted-foreground" },
          cell: (c) => {
            const r = c.row.original.regras;
            return r.updatedAt ? `${r.updatedBy?.name ?? "—"} · ${formatDateTime(r.updatedAt)}` : "—";
          },
        }),
      ]),
    [],
  );
  if (tipos.isError) return <ApiErrorAlert error={tipos.error} />;
  return (
    <HeaderCard title="Regras por tipo de campo" description="O texto que a IA segue ao escrever cada campo. Só o dono edita.">
      <DataTable
        label="Tipos de campo"
        columns={columns}
        data={tipos.data?.items}
        loading={tipos.isPending}
        getRowId={(t) => t.id}
        initialPageSize={25}
        emptyMessage="Nenhum tipo de campo."
      />
    </HeaderCard>
  );
}
