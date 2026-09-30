/*
 * Evolução de uma conta (spec 016, US4), na aba "Contas" de /app/metricas: seguidores ou curtidas
 * ao longo do tempo, com os vídeos publicados marcados, e o estado da coleta. Período e resolução
 * na URL (`cde`, `cate`, `resolucao`); padrão: últimos 30 dias, resolução automática (hora até 14
 * dias, dia além disso).
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { useFiltroUrl } from "@/components/conteudos/FiltrosConteudos";
import { HeaderCard } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCompacto, formatNumero, useMetricasConta, type FotoConta, type Resolucao } from "@/lib/metricas";
import { addDays, formatDateTime, localDateKey } from "@/lib/tz";
import { ColetaStatus } from "./ColetaStatus";
import { FiltroContas, useContasTikTok } from "./FiltroContas";
import { LinhaChart } from "./LinhaChart";

type Vista = "seguidores" | "curtidas";

const formatData = (ms: number) => new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit" }).format(new Date(ms));

export function ContaMetricas() {
  const [params, set] = useFiltroUrl();
  const perfilId = params.get("perfil") ?? "";
  const contas = useContasTikTok(perfilId);
  const contaId = params.get("conta") ?? (contas.length === 1 ? contas[0]!.id : "");
  const hoje = localDateKey(new Date());
  const de = params.get("cde") ?? addDays(hoje, -29);
  const ate = params.get("cate") ?? hoje;
  const invertido = de > ate;
  const resolucao = (params.get("resolucao") as Resolucao | null) ?? "auto";
  const [vista, setVista] = useState<Vista>("seguidores");
  const dados = useMetricasConta(contaId, invertido ? { resolucao } : { de, ate, resolucao });
  const conta = contas.find((c) => c.id === contaId);

  const fotos = dados.data?.fotos ?? [];
  const ultima: FotoConta | undefined = fotos[fotos.length - 1];
  const campo = vista === "seguidores" ? "seguidores" : "curtidas";
  const pontos = fotos.map((f) => ({ x: new Date(f.coletadoEm).getTime(), y: [f[campo]] }));
  const marcadores = (dados.data?.publicacoes ?? []).map((p) => ({ x: new Date(p.publicadoEm).getTime(), label: `Vídeo publicado em ${formatDateTime(p.publicadoEm)}` }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <FiltroContas perfilId={perfilId} contaId={contaId} set={set} todasAsContas={false} />
        <fieldset className="space-y-1.5">
          <legend className="text-sm font-medium">Período</legend>
          <div className="flex items-center gap-1.5">
            <Input type="date" aria-label="Período de" value={de} onChange={(e) => set({ cde: e.target.value })} className="w-auto" />
            <span className="text-sm text-muted-foreground">a</span>
            <Input type="date" aria-label="Período até" value={ate} aria-invalid={invertido} onChange={(e) => set({ cate: e.target.value })} className="w-auto" />
          </div>
          {invertido && (
            <p role="alert" className="text-xs text-destructive">
              O início é depois do fim; o período foi ignorado.
            </p>
          )}
        </fieldset>
        <Field label="Resolução" className="w-full sm:w-40">
          {({ id }) => (
            <NativeSelect id={id} value={resolucao} onChange={(e) => set({ resolucao: e.target.value === "auto" ? null : e.target.value })}>
              <option value="auto">Automática</option>
              <option value="hora">Por hora</option>
              <option value="dia">Por dia</option>
            </NativeSelect>
          )}
        </Field>
      </div>

      {!contaId ? (
        <p className="text-sm text-muted-foreground">Escolha o perfil e a conta TikTok para ver a evolução.</p>
      ) : (
        <HeaderCard title={conta ? `@${conta.handle}` : "Conta"} description="Seguidores e curtidas ao longo do tempo; as marcas são os vídeos publicados." tone="dark">
          <div className="space-y-4">
            {dados.isError ? (
              <ApiErrorAlert error={dados.error} />
            ) : dados.isPending ? (
              <Skeleton className="h-60 w-full" />
            ) : (
              <>
                <ColetaStatus coleta={dados.data.coleta} />
                {dados.data.coleta.permissao === "faltando" && perfilId && (
                  <p className="text-xs text-muted-foreground">
                    Reconecte na{" "}
                    <Link to={`/app/perfis/${perfilId}?aba=contas`} className="underline">
                      aba Contas do perfil
                    </Link>
                    .
                  </p>
                )}
                {ultima && (
                  <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {(
                      [
                        ["Seguidores", ultima.seguidores],
                        ["Seguindo", ultima.seguindo],
                        ["Curtidas", ultima.curtidas],
                        ["Vídeos públicos", ultima.videos],
                      ] as const
                    ).map(([label, v]) => (
                      <div key={label} className="rounded-lg border bg-muted/30 p-3">
                        <dt className="text-xs text-muted-foreground">{label}</dt>
                        <dd className="text-xl font-bold tabular-nums">{formatNumero(v)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
                {fotos.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Nenhuma foto da conta neste período.</p>
                ) : (
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-1" role="group" aria-label="O que mostrar no gráfico">
                      {(["seguidores", "curtidas"] as const).map((v) => (
                        <Button key={v} type="button" size="sm" variant={vista === v ? "default" : "outline"} aria-pressed={vista === v} onClick={() => setVista(v)}>
                          {v === "seguidores" ? "Seguidores" : "Curtidas"}
                        </Button>
                      ))}
                    </div>
                    <LinhaChart
                      titulo={vista === "seguidores" ? "Seguidores ao longo do tempo" : "Curtidas totais ao longo do tempo"}
                      series={[{ label: vista === "seguidores" ? "Seguidores" : "Curtidas", cor: vista === "seguidores" ? "primary" : "success" }]}
                      pontos={pontos}
                      marcadores={marcadores}
                      formatX={(x) => (pontos.length > 1 && pontos[pontos.length - 1]!.x - pontos[0]!.x < 2 * 86_400_000 ? formatDateTime(new Date(x).toISOString()) : formatData(x))}
                      formatY={formatCompacto}
                    />
                    <p className="text-xs text-muted-foreground">
                      {fotos.length} {fotos.length === 1 ? "foto" : "fotos"} · {marcadores.length} {marcadores.length === 1 ? "vídeo publicado" : "vídeos publicados"} no período
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        </HeaderCard>
      )}
    </div>
  );
}
