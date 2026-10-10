import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import { useRef, useState } from "react";
import { LinhaTempos, fmtSeg } from "@/components/roteiro/LinhaTempos";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { perfilNomeDe, usePerfisTodos } from "@/lib/estudio";
import { useLinkEstavel } from "@/lib/linkEstavel";
import { roteiroKey, VELOCIDADE } from "@/lib/roteiros";
import { useVozesAprovadas } from "@/lib/vozes";
import { Andamentos, BotaoAprovar, type EtapaProps } from "./comum";

const pct = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 0 });

// Etapa Narração (spec 011, US2, T026): o take contínuo de todas as frases, a linha do tempo (clicar
// numa frase toca dali), a similaridade da retranscrição, a velocidade e a voz (mudar qualquer uma
// marca a narração como desatualizada e pede outra) e aprovar.
export function Narracao({ roteiro, rodar, travado }: EtapaProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [ativa, setAtiva] = useState<number | null>(null);
  const [velocidade, setVelocidade] = useState(String(roteiro.velocidade));
  const [busy, setBusy] = useState<"velocidade" | "voz" | null>(null);
  const perfis = usePerfisTodos();
  const vozes = useVozesAprovadas(roteiro.perfilId);
  const queryClient = useQueryClient();
  const n = roteiro.narracao;
  // o roteiro recarrega a cada 2 s com um link novo: o player segura o atual (chave = a narração)
  const audio = useLinkEstavel(n?.audioUrl ? { url: n.audioUrl } : null, n?.id ?? null, () => void queryClient.invalidateQueries({ queryKey: roteiroKey(roteiro.id) }));
  const tempos = roteiro.frases.map((_, i) => {
    const t = n?.tempos.find((x) => x.frase === i);
    return t ? { inicio: t.inicioS, fim: t.fimS } : { inicio: 0, fim: 0 };
  });

  function tocar(inicio: number, i: number) {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = inicio;
    setAtiva(i);
    void a.play();
  }

  function aoTocar() {
    const a = audioRef.current;
    if (!a || !n) return;
    const t = a.currentTime;
    const i = n.tempos.findIndex((x) => t >= x.inicioS && t < x.fimS);
    setAtiva(i >= 0 ? (n.tempos[i]?.frase ?? null) : null);
  }

  const v = Number(velocidade.replace(",", "."));
  const velocidadeValida = Number.isFinite(v) && v >= VELOCIDADE.min && v <= VELOCIDADE.max;

  return (
    <div className="space-y-4" data-testid="etapa-narracao">
      <BotaoAprovar roteiro={roteiro} rodar={rodar} travado={travado} portao="narracao" />
      <Andamentos geracoes={roteiro.geracoesAbertas} filtro={(g) => g.passo === "roteiro.narracao"} />

      {n ? (
        <section className="space-y-3" aria-label="Narração">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">Take inteiro · {fmtSeg(n.totalS)}</span>
            <Badge variant="secondary">Similaridade {pct.format(n.similaridade)}</Badge>
            <Badge variant="outline">Velocidade {String(n.velocidade).replace(".", ",")}</Badge>
            {n.desatualizada && (
              <Badge className="bg-warning text-warning-foreground" data-testid="narracao-desatualizada">
                Desatualizada
              </Badge>
            )}
            {n.limpa && <Badge variant="outline">Arquivo removido</Badge>}
            {roteiro.narracoesAnteriores > 0 && <span className="text-xs text-muted-foreground">{roteiro.narracoesAnteriores} narrações anteriores no histórico</span>}
          </div>
          {audio.url && !n.limpa && (
            <audio
              key={n.id}
              ref={audioRef}
              controls
              preload="metadata"
              src={audio.url}
              onError={audio.onErro}
              aria-label="Narração do roteiro"
              className="w-full"
              data-testid="player-narracao"
              onTimeUpdate={aoTocar}
            />
          )}
          <LinhaTempos frases={roteiro.frases} tempos={tempos} totalS={n.totalS} ativa={ativa} onTocar={n.audioUrl && !n.limpa ? tocar : undefined} />
        </section>
      ) : (
        <p className="text-sm text-muted-foreground">A narração sai depois do texto aprovado.</p>
      )}

      {!travado && (
        <div className="grid gap-4 rounded-lg border p-3 sm:grid-cols-[12rem_auto_1fr] sm:items-end">
          <Field label="Velocidade" hint={`De ${VELOCIDADE.min} a ${VELOCIDADE.max}; padrão ${String(VELOCIDADE.padrao).replace(".", ",")}.`}>
            {({ id, describedBy }) => (
              <Input id={id} inputMode="decimal" value={velocidade} aria-describedby={describedBy} onChange={(e) => setVelocidade(e.target.value)} />
            )}
          </Field>
          <Button
            type="button"
            variant="outline"
            disabled={busy !== null || !velocidadeValida || v === roteiro.velocidade}
            aria-busy={busy === "velocidade"}
            onClick={async () => {
              setBusy("velocidade");
              await rodar(() => api.roteiros.editar(roteiro.id, { version: roteiro.version, velocidade: v }), "Velocidade salva. A narração vai ser refeita.");
              setBusy(null);
            }}
          >
            {busy === "velocidade" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
            Salvar velocidade
          </Button>
          <Field label="Voz do roteiro" hint={roteiro.voz?.revogada ? "A voz atual foi revogada: escolha outra." : "Trocar a voz refaz a narração."}>
            {({ id, describedBy }) => (
              <NativeSelect
                id={id}
                value={roteiro.voz?.id ?? ""}
                disabled={busy !== null}
                aria-describedby={describedBy}
                onChange={async (e) => {
                  if (!e.target.value) return;
                  setBusy("voz");
                  await rodar(() => api.roteiros.editar(roteiro.id, { version: roteiro.version, vozId: e.target.value }), "Voz trocada. A narração vai ser refeita.");
                  setBusy(null);
                }}
              >
                {!roteiro.voz && <option value="">Sem voz</option>}
                {roteiro.voz && !(vozes.itens ?? []).some((x) => x.id === roteiro.voz?.id) && <option value={roteiro.voz.id}>{roteiro.voz.nome}</option>}
                {(vozes.itens ?? []).map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name} · {perfilNomeDe(x, perfis.data)}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </div>
      )}
    </div>
  );
}
