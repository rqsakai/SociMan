/*
 * O avançado do vídeo guiado (spec 031, US7, T053; FR-015, FR-017, FR-026..028, R8): nas etapas da
 * 011, os quadros e os trechos de cada posição. Por quadro, a instrução (editável) e "Regerar daqui"
 * com 1 a 4 opções (com 2 ou mais, a cadeia espera a sua escolha; o quadro e os seguintes são
 * refeitos). Por trecho, o clipe, "Regerar o trecho" com 1 ou 2 versões e a escolha entre as tomadas
 * do trecho (com 2 versões, o roteiro espera a escolha em "Gerando clipes").
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ImageOff, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { OpcoesGeracao } from "@/components/geracao/OpcoesGeracao";
import { fmtSeg } from "@/components/roteiro/LinhaTempos";
import { PlayerVideo } from "@/components/roteiro/PlayerVideo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useGeracao } from "@/lib/geracoes";
import { invalidarRoteiro, LIM, MOTORES, motorLabel, roteiroKey, type CenaMotor, type Roteiro, type RoteiroPosicao } from "@/lib/roteiros";
import { papelLabel, type RoteiroQuadro } from "@/lib/videoGuiado";
import { Andamentos, type EtapaProps } from "./comum";

type Props = { roteiro: Roteiro; posicao: RoteiroPosicao } & Pick<EtapaProps, "rodar" | "travado">;

// ---------------------------------------------------------------------------------------------
// Quadros

export function QuadrosAvancado({ roteiro: r, posicao: p, rodar, travado }: Props) {
  const queryClient = useQueryClient();
  const n = p.ordem + 1;
  const abertas = p.geracoesAbertas.filter((g) => g.passo === "cena.keyframe");
  const [editando, setEditando] = useState<number | null>(null);
  const quadros = p.quadros ?? [];
  const aprovada = p.aprovadoKeyframesEm != null;

  return (
    <div className="flex flex-col gap-3" data-testid={`quadros-avancado-${n}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          {quadros.length} quadros · {p.trechos ?? 0} {p.trechos === 1 ? "trecho" : "trechos"}
        </span>
        {aprovada && <Badge className="bg-success text-success-foreground">Sequência aprovada</Badge>}
      </div>
      <Andamentos geracoes={abertas} />
      {abertas.map((g) => (
        <Opcoes key={g.id} geracaoId={g.id} alvoVersion={p.cena.version} disabled={travado} onEscolhido={() => void invalidarRoteiro(queryClient, r.id)} />
      ))}
      <ol className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label={`Quadros da cena ${n}`}>
        {quadros.map((q) => (
          <li key={q.ordem} className="flex min-w-0 flex-col gap-1.5" data-testid={`quadro-avancado-${q.ordem}`}>
            <p className="flex flex-wrap items-center gap-1 text-xs font-medium">
              {papelLabel[q.papel]}
              {q.imageId && q.provisorio && (
                <Badge variant="outline" className="h-4 px-1 text-[10px]">
                  provisório
                </Badge>
              )}
            </p>
            <div className="aspect-[9/16] overflow-hidden rounded-md border bg-muted">
              {q.imageUrl ? (
                <img src={q.imageUrl} alt={`Quadro ${papelLabel[q.papel]} da cena ${n}`} className="size-full object-cover" />
              ) : (
                <span className="flex size-full items-center justify-center text-muted-foreground">
                  <ImageOff className="size-4" aria-hidden="true" />
                </span>
              )}
            </div>
            <p className="line-clamp-3 text-[11px] break-words text-muted-foreground" lang="en">
              {q.instrucao}
            </p>
            {!travado && abertas.length === 0 && (
              <Button type="button" variant={editando === q.ordem ? "secondary" : "outline"} size="xs" aria-expanded={editando === q.ordem} onClick={() => setEditando(editando === q.ordem ? null : q.ordem)}>
                <RefreshCw aria-hidden="true" />
                Regerar daqui
              </Button>
            )}
          </li>
        ))}
      </ol>
      {editando !== null && quadros.some((q) => q.ordem === editando) && (
        <RegerarQuadro
          key={editando}
          roteiro={r}
          posicao={p}
          quadro={quadros.find((q) => q.ordem === editando)!}
          rodar={rodar}
          onFeito={() => setEditando(null)}
        />
      )}
    </div>
  );
}

function RegerarQuadro({
  roteiro: r,
  posicao: p,
  quadro: q,
  rodar,
  onFeito,
}: {
  roteiro: Roteiro;
  posicao: RoteiroPosicao;
  quadro: RoteiroQuadro;
  rodar: EtapaProps["rodar"];
  onFeito: () => void;
}) {
  const [instrucao, setInstrucao] = useState(q.instrucao);
  const [nOpcoes, setNOpcoes] = useState(2);
  const [busy, setBusy] = useState(false);
  const n = p.ordem + 1;
  const papel = papelLabel[q.papel];
  const seguintes = (p.quadros ?? []).length - 1 - q.ordem;

  return (
    <div className="flex flex-col gap-3 rounded-lg bg-muted/40 p-3" data-testid={`regerar-quadro-${n}-${q.ordem}`}>
      <Field label={`Instrução do quadro ${papel} da cena ${n} (inglês)`} hint="O estado final do quadro. Não peça mudança de luz (recolore o produto).">
        {({ id, describedBy }) => (
          <Textarea id={id} rows={3} lang="en" value={instrucao} maxLength={LIM.instrucao} aria-describedby={describedBy} onChange={(e) => setInstrucao(e.target.value)} />
        )}
      </Field>
      <Field label="Quantas opções" hint={nOpcoes === 1 ? "Com 1, a sequência segue sozinha." : "Com 2 ou mais, a sequência espera você escolher uma."} className="max-w-48">
        {({ id, describedBy }) => (
          <NativeSelect id={id} value={String(nOpcoes)} aria-describedby={describedBy} onChange={(e) => setNOpcoes(Number(e.target.value))}>
            {[1, 2, 3, 4].map((k) => (
              <option key={k} value={k}>
                {k} {k === 1 ? "opção" : "opções"}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      {seguintes > 0 && (
        <p className="text-xs text-muted-foreground">
          {seguintes === 1 ? "O quadro seguinte também é refeito" : `Os ${seguintes} quadros seguintes também são refeitos`}, a partir do escolhido, e os trechos que tocam neles.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          disabled={busy || instrucao.trim() === ""}
          aria-busy={busy}
          onClick={async () => {
            setBusy(true);
            const ok = await rodar(
              () =>
                api.roteiros.regerarKeyframe(r.id, p.ordem, {
                  version: r.version,
                  quadro: q.ordem,
                  nOpcoes,
                  instrucao: instrucao.trim() !== q.instrucao ? instrucao.trim() : null,
                }),
              `Quadro ${papel} da cena ${n} na fila (${nOpcoes} ${nOpcoes === 1 ? "opção" : "opções"}).`,
            );
            setBusy(false);
            if (ok) onFeito();
          }}
        >
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
          Gerar {nOpcoes} {nOpcoes === 1 ? "opção" : "opções"}
        </Button>
        <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={onFeito}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}

function Opcoes({ geracaoId, alvoVersion, disabled, onEscolhido }: { geracaoId: string; alvoVersion?: number; disabled?: boolean; onEscolhido: () => void }) {
  const geracao = useGeracao(geracaoId);
  if (!geracao.data) return null;
  return <OpcoesGeracao geracao={geracao.data} alvoVersion={alvoVersion} disabled={disabled} onRenovarLinks={() => void geracao.refetch()} onEscolhido={onEscolhido} />;
}

// ---------------------------------------------------------------------------------------------
// Trechos

export function TrechosAvancado({ roteiro: r, posicao: p, rodar, travado }: Props) {
  const n = p.ordem + 1;
  const trechos = Array.from({ length: p.trechos ?? 0 }, (_, t) => t);
  const abertas = p.geracoesAbertas.filter((g) => g.passo === "cena.clipe");
  // As tomadas da cena com o trecho de cada uma (o `trecho` vem nos extras da geração do clipe).
  const tomadas = useQuery({ queryKey: ["cena-tomadas", p.cena.id, false, "trechos", abertas.length], queryFn: () => api.cenas.tomadas(p.cena.id) });
  const geracoes = useQuery({
    queryKey: ["geracoes", "cena-clipe", p.cena.id, abertas.length],
    queryFn: () => api.geracoes.listarAgencia({ alvoTipo: "cena", alvoId: p.cena.id, passo: "cena.clipe", limite: 50 }),
  });
  const trechoDe = new Map((geracoes.data?.itens ?? []).map((g) => [g.id, typeof g.extras?.trecho === "number" ? (g.extras.trecho as number) : null]));

  return (
    <div className="flex flex-col gap-3" data-testid={`trechos-avancado-${n}`}>
      <Andamentos geracoes={abertas} />
      <ol className="flex flex-col gap-3" aria-label={`Trechos da cena ${n}`}>
        {trechos.map((t) => {
          const atual = p.tomadasTrechos?.find((x) => x.trecho === t)?.tomada ?? null;
          const doTrecho = (tomadas.data?.items ?? []).filter((tm) => !tm.arquivada && !tm.limpa && tm.geracaoId != null && trechoDe.get(tm.geracaoId) === t);
          return (
            <Trecho key={`${t}-${atual?.id ?? "sem"}`} roteiro={r} posicao={p} trecho={t} atual={atual} opcoes={doTrecho} gerando={abertas.length > 0} rodar={rodar} travado={travado} />
          );
        })}
      </ol>
    </div>
  );
}

type TomadaCena = NonNullable<Awaited<ReturnType<typeof api.cenas.tomadas>>>["items"][number];

function Trecho({
  roteiro: r,
  posicao: p,
  trecho: t,
  atual,
  opcoes,
  gerando,
  rodar,
  travado,
}: Props & { trecho: number; atual: NonNullable<RoteiroPosicao["tomadasTrechos"]>[number]["tomada"]; opcoes: TomadaCena[]; gerando: boolean }) {
  const queryClient = useQueryClient();
  const n = p.ordem + 1;
  const [motor, setMotor] = useState<CenaMotor>(p.cena.motor);
  const [nOpcoes, setNOpcoes] = useState(2);
  const [busy, setBusy] = useState<string | null>(null);
  // Sem tomada e sem geração andando: as versões prontas esperam a escolha (abre sozinho).
  const esperando = atual == null && !gerando && opcoes.length > 0;
  const [verOpcoes, setVerOpcoes] = useState(esperando);
  const outras = opcoes.filter((tm) => tm.id !== atual?.id);

  return (
    <li className="flex flex-col gap-2 rounded-lg border p-2.5" data-testid={`trecho-avancado-${n}-${t}`}>
      <p className="text-xs font-medium">
        Trecho {t + 1}
        {esperando && <span className="ml-2 text-warning-foreground">escolha uma das versões</span>}
      </p>
      {atual?.videoUrl && !atual.limpa ? (
        <PlayerVideo
          chave={atual.id}
          url={atual.videoUrl}
          miniaturaUrl={atual.miniaturaUrl}
          rotulo={`Clipe do trecho ${t + 1} da cena ${n}`}
          testId={`player-avancado-${n}-${t}`}
          onRenovar={() => void queryClient.invalidateQueries({ queryKey: roteiroKey(r.id) })}
        />
      ) : (
        <p className="text-xs text-muted-foreground">{atual ? "Arquivo removido." : gerando ? "Gerando…" : "Ainda sem clipe."}</p>
      )}

      {/* Também com o trecho gerando: o pedido novo cancela a geração aberta (troca de motor). */}
      {!travado && (
        <div className="flex flex-wrap items-end gap-2">
          <Field label={`Motor do trecho ${t + 1} da cena ${n}`} className="min-w-44 flex-1">
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
          <Field label="Versões" className="w-32">
            {({ id }) => (
              <NativeSelect id={id} value={String(nOpcoes)} onChange={(e) => setNOpcoes(Number(e.target.value))}>
                <option value="1">1 versão</option>
                <option value="2">2 versões</option>
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
              await rodar(
                () => api.roteiros.regerarClipe(r.id, p.ordem, { version: r.version, trecho: t, nOpcoes, motor: motor !== p.cena.motor ? motor : null }),
                `Trecho ${t + 1} da cena ${n} na fila (${nOpcoes} ${nOpcoes === 1 ? "versão" : "versões"}).`,
              );
              setBusy(null);
            }}
          >
            {busy === "regerar" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
            {gerando ? "Cancelar e refazer o trecho" : "Regerar o trecho"}
          </Button>
        </div>
      )}

      {outras.length > 0 && (
        <div className="flex flex-col gap-2">
          <Button type="button" variant="ghost" size="sm" className="self-start" aria-expanded={verOpcoes} onClick={() => setVerOpcoes((v) => !v)}>
            {verOpcoes ? "Esconder as outras tomadas" : `Ver as outras tomadas (${outras.length})`}
          </Button>
          {verOpcoes && (
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3" aria-label={`Tomadas do trecho ${t + 1} da cena ${n}`} data-testid={`tomadas-trecho-${n}-${t}`}>
              {outras.map((tm) => (
                <li key={tm.id} className="flex flex-col gap-1 rounded-md border p-1.5 text-xs">
                  {tm.videoUrl ? (
                    <PlayerVideo chave={tm.id} url={tm.videoUrl} miniaturaUrl={tm.thumbUrl} rotulo={`Tomada do trecho ${t + 1}`} onRenovar={() => void queryClient.invalidateQueries({ queryKey: ["cena-tomadas", p.cena.id, false] })} />
                  ) : (
                    <div className="aspect-[9/16] overflow-hidden rounded bg-muted">{tm.thumbUrl && <img src={tm.thumbUrl} alt="" className="size-full object-cover" />}</div>
                  )}
                  <p className="flex flex-wrap items-center gap-1">
                    <span className="tabular-nums">{fmtSeg(tm.duracaoMs / 1000)}</span>
                    {tm.motor && <Badge variant="secondary">{motorLabel[tm.motor]}</Badge>}
                  </p>
                  {!travado && (
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      disabled={busy !== null}
                      aria-busy={busy === tm.id}
                      onClick={async () => {
                        setBusy(tm.id);
                        await rodar(() => api.roteiros.escolherTomada(r.id, p.ordem, r.version, tm.id, t), `Tomada escolhida no trecho ${t + 1} da cena ${n}.`);
                        setBusy(null);
                      }}
                    >
                      <Check aria-hidden="true" />
                      Usar esta tomada
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}
