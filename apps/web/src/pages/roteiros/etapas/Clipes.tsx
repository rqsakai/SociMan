import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { PlayerVideo } from "@/components/roteiro/PlayerVideo";
import { fmtSeg } from "@/components/roteiro/LinhaTempos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import { MOTORES, motorLabel, roteiroKey, type CenaMotor, type RoteiroPosicao } from "@/lib/roteiros";
import { Andamentos, BotaoAprovar, type EtapaProps } from "./comum";

// Etapa Clipes (spec 011, US4, T038): por posição, a tomada do roteiro (player), o motor, "Regerar
// clipe" (com outro motor, se quiser), as tomadas da cena (com "keyframe antigo" e "arquivo
// removido") para escolher outra sem gerar nada, os avisos e aprovar.
export function Clipes({ roteiro, rodar, travado }: EtapaProps) {
  return (
    <div className="space-y-4" data-testid="etapa-clipes">
      <BotaoAprovar roteiro={roteiro} rodar={rodar} travado={travado} portao="clipes" />
      <ol className="grid gap-4 lg:grid-cols-2" aria-label="Clipes por cena">
        {roteiro.posicoes.map((p) => (
          <ClipePosicao key={p.ordem} roteiroId={roteiro.id} version={roteiro.version} posicao={p} rodar={rodar} travado={travado} />
        ))}
      </ol>
    </div>
  );
}

function ClipePosicao({
  roteiroId,
  version,
  posicao: p,
  rodar,
  travado,
}: { roteiroId: string; version: number; posicao: RoteiroPosicao } & Pick<EtapaProps, "rodar" | "travado">) {
  const queryClient = useQueryClient();
  const [motor, setMotor] = useState<CenaMotor>(p.cena.motor);
  const [busy, setBusy] = useState<string | null>(null);
  const [verTomadas, setVerTomadas] = useState(false);
  const tomadas = useQuery({ queryKey: ["cena-tomadas", p.cena.id, false], queryFn: () => api.cenas.tomadas(p.cena.id), enabled: verTomadas });
  const aberta = p.geracoesAbertas.some((g) => g.passo === "cena.clipe");
  const n = p.ordem + 1;
  const t = p.tomada;
  const curta = t && p.duracaoS != null && t.duracaoMs / 1000 < p.duracaoS;

  return (
    <li className="space-y-3 rounded-xl border p-3" data-testid={`clipe-cena-${n}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">
          Cena {n}: {p.cena.nome}
        </h3>
        {p.duracaoS != null && <span className="text-xs text-muted-foreground tabular-nums">dura {fmtSeg(p.duracaoS)}</span>}
      </div>
      {p.aviso && (
        <p role="status" className="text-sm text-warning-foreground" data-testid="aviso-posicao">
          {p.aviso}
        </p>
      )}
      <Andamentos geracoes={p.geracoesAbertas} filtro={(g) => g.passo === "cena.clipe"} />
      {t ? (
        <div className="space-y-2">
          {t.videoUrl && !t.limpa ? (
            <PlayerVideo chave={t.id} url={t.videoUrl} miniaturaUrl={t.miniaturaUrl} rotulo={`Clipe da cena ${n}`} testId={`player-clipe-${n}`} onRenovar={() => void queryClient.invalidateQueries({ queryKey: roteiroKey(roteiroId) })} />
          ) : (
            <p className="text-sm text-muted-foreground">Arquivo removido.</p>
          )}
          <p className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="tabular-nums">{fmtSeg(t.duracaoMs / 1000)}</span>
            {t.motor && <Badge variant="secondary">{motorLabel[t.motor]}</Badge>}
            <Badge variant="outline">{t.origem === "geracao_local" ? "gerado aqui" : "Flow (manual)"}</Badge>
            {t.keyframeAntigo && <Badge className="bg-warning text-warning-foreground">keyframe antigo</Badge>}
            {t.limpa && <Badge variant="outline">arquivo removido</Badge>}
            {curta && <Badge className="bg-warning text-warning-foreground">tomada curta</Badge>}
          </p>
        </div>
      ) : (
        !aberta && <p className="text-sm text-muted-foreground">Ainda sem tomada.</p>
      )}

      {!travado && !aberta && (
        <div className="flex flex-wrap items-end gap-2">
          <Field label={`Motor da cena ${n}`} className="min-w-52 flex-1">
            {({ id }) => (
              <NativeSelect id={id} value={motor} onChange={(e) => setMotor(e.target.value as CenaMotor)}>
                {MOTORES.map((m) => (
                  <option key={m} value={m}>
                    {motorLabel[m]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Button
            type="button"
            variant="outline"
            disabled={busy !== null}
            aria-busy={busy === "regerar"}
            onClick={async () => {
              setBusy("regerar");
              await rodar(() => api.roteiros.regerarClipe(roteiroId, p.ordem, { version, motor }), `Novo clipe da cena ${n} na fila.`);
              setBusy(null);
            }}
          >
            {busy === "regerar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
            Regerar clipe
          </Button>
        </div>
      )}

      <div className="space-y-2">
        <Button type="button" variant="ghost" size="sm" onClick={() => setVerTomadas((v) => !v)} aria-expanded={verTomadas}>
          {verTomadas ? "Esconder as tomadas da cena" : "Ver as tomadas da cena"}
        </Button>
        {verTomadas && (
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3" aria-label={`Tomadas da cena ${n}`} data-testid={`tomadas-cena-${n}`}>
            {tomadas.isPending && <li className="text-xs text-muted-foreground">Carregando…</li>}
            {tomadas.data?.items.length === 0 && <li className="text-xs text-muted-foreground">Nenhuma tomada.</li>}
            {tomadas.data?.items.map((tm) => {
              const atual = tm.id === t?.id;
              return (
                <li key={tm.id} className="space-y-1 rounded-md border p-1.5 text-xs">
                  <div className="aspect-[9/16] overflow-hidden rounded bg-muted">{tm.thumbUrl && <img src={tm.thumbUrl} alt="" className="size-full object-cover" />}</div>
                  <p className="tabular-nums">{fmtSeg(tm.duracaoMs / 1000)}</p>
                  <p className="flex flex-wrap gap-1">
                    {tm.motor && <Badge variant="secondary">{tm.motor}</Badge>}
                    {tm.keyframeAntigo && <Badge className="bg-warning text-warning-foreground">keyframe antigo</Badge>}
                    {tm.limpa && <Badge variant="outline">arquivo removido</Badge>}
                  </p>
                  {atual ? (
                    <Badge className="bg-success text-success-foreground">Em uso</Badge>
                  ) : (
                    !travado &&
                    !tm.limpa && (
                      <Button
                        type="button"
                        variant="outline"
                        size="xs"
                        disabled={busy !== null}
                        aria-busy={busy === tm.id}
                        onClick={async () => {
                          setBusy(tm.id);
                          await rodar(() => api.roteiros.escolherTomada(roteiroId, p.ordem, version, tm.id), `Tomada trocada na cena ${n}.`);
                          setBusy(null);
                        }}
                      >
                        <Check aria-hidden="true" />
                        Usar esta tomada
                      </Button>
                    )
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </li>
  );
}
