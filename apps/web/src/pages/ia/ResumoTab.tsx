/*
 * Aba "Resumo do mês" do assistente de IA (spec 008, US3, SC-005; só o dono): chamadas, custo
 * aproximado, taxa de aplicação e erros do mês (no horário de Brasília), e o gasto por tipo de campo
 * e por perfil. "Quanto gastei este mês e em quê" fica na primeira dobra.
 */
import { useQuery } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, DollarSign, Sparkles } from "lucide-react";
import { useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { HeaderCard, MetricCard, Page } from "@/components/shell";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "../../lib/api";
import { custoText, iaResumoKey, iaTiposQuery } from "../../lib/ia";
import { localParts } from "../../lib/tz";

function mesAtual(): string {
  const p = localParts(new Date());
  return `${p.year}-${String(p.month).padStart(2, "0")}`;
}

export function ResumoTab() {
  const [mes, setMes] = useState(mesAtual);
  const resumo = useQuery({ queryKey: iaResumoKey(mes), queryFn: () => api.ia.resumo(mes) });
  const tipos = useQuery(iaTiposQuery);
  const rotulo = (id: string) => tipos.data?.items.find((t) => t.id === id)?.rotulo ?? id;
  const r = resumo.data;
  const usadas = r ? r.aplicadas + r.editadas : 0;
  const taxa = r && r.chamadas > 0 ? `${Math.round((usadas / r.chamadas) * 100)}%` : "—";

  return (
    <Page>
      <Field label="Mês" className="w-full sm:w-48">
        {({ id }) => <Input id={id} type="month" value={mes} max={mesAtual()} onChange={(e) => e.target.value && setMes(e.target.value)} />}
      </Field>
      {resumo.isError && <ApiErrorAlert error={resumo.error} />}
      <div className="grid gap-x-6 gap-y-10 pt-6 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={DollarSign} tone="primary" label="Custo aproximado" value={r ? custoText(r.custoUsd) : "—"} loading={resumo.isPending} footer={r ? `preços de ${r.precosVersao}` : undefined} />
        <MetricCard icon={Sparkles} tone="info" label="Chamadas" value={r?.chamadas ?? "—"} loading={resumo.isPending} />
        <MetricCard
          icon={CircleCheck}
          tone="success"
          label="Taxa de aplicação"
          value={taxa}
          loading={resumo.isPending}
          footer={r ? `${r.aplicadas} aplicadas · ${r.editadas} editadas · ${r.descartadas} descartadas` : undefined}
        />
        <MetricCard icon={CircleAlert} tone="warning" label="Erros" value={r?.erros ?? "—"} loading={resumo.isPending} />
      </div>
      {r && (
        <div className="grid gap-6 lg:grid-cols-2">
          <HeaderCard title="Por tipo de campo">
            <Table aria-label="Gasto por tipo de campo">
              <TableHeader>
                <TableRow>
                  <TableHead>Tipo de campo</TableHead>
                  <TableHead className="text-right">Chamadas</TableHead>
                  <TableHead className="text-right">Custo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {r.porTipo.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={3} className="text-muted-foreground">
                      Nenhuma chamada neste mês.
                    </TableCell>
                  </TableRow>
                )}
                {r.porTipo.map((t) => (
                  <TableRow key={t.tipoCampo}>
                    <TableCell>{rotulo(t.tipoCampo)}</TableCell>
                    <TableCell className="text-right">{t.chamadas}</TableCell>
                    <TableCell className="text-right">{custoText(t.custoUsd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </HeaderCard>
          <HeaderCard title="Por perfil">
            <Table aria-label="Gasto por perfil">
              <TableHeader>
                <TableRow>
                  <TableHead>Perfil</TableHead>
                  <TableHead className="text-right">Chamadas</TableHead>
                  <TableHead className="text-right">Custo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {r.porPerfil.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={3} className="text-muted-foreground">
                      Nenhuma chamada neste mês.
                    </TableCell>
                  </TableRow>
                )}
                {r.porPerfil.map((p) => (
                  <TableRow key={p.perfil?.id ?? "sem-perfil"}>
                    <TableCell>{p.perfil?.name ?? "Sem perfil"}</TableCell>
                    <TableCell className="text-right">{p.chamadas}</TableCell>
                    <TableCell className="text-right">{custoText(p.custoUsd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </HeaderCard>
        </div>
      )}
    </Page>
  );
}
