import { useQueryClient } from "@tanstack/react-query";
import { ImageOff, Loader2, RefreshCw, Upload, X } from "lucide-react";
import { useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { LibraryImageDialog } from "@/components/assets/LibraryImageDialog";
import { OpcoesGeracao } from "@/components/geracao/OpcoesGeracao";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { FileField } from "@/components/ui/file-field";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { cenaKey } from "@/lib/cenas";
import { useGeracao } from "@/lib/geracoes";
import { enviarKeyframe, invalidarRoteiro, KEYFRAME_ACCEPT, LIM, roteiroKey, type RoteiroPosicao } from "@/lib/roteiros";
import { Andamentos, BotaoAprovar, type EtapaProps } from "./comum";

// Etapa Keyframes (spec 011, US3, T033): por posição, o keyframe atual, as opções da geração aberta
// (componentes da 021, "Usar opção N" com a versão da cena), "Regerar esta cena" com a instrução e as
// referências, o envio de uma imagem pronta, os avisos e aprovar.
export function Keyframes({ roteiro, rodar, travado }: EtapaProps) {
  const pendentes = roteiro.posicoes.filter((p) => !p.cena.keyframeUrl).length;
  return (
    <div className="space-y-4" data-testid="etapa-keyframes">
      <BotaoAprovar
        roteiro={roteiro}
        rodar={rodar}
        travado={travado}
        portao="keyframes"
        motivo={pendentes > 0 ? `Falta escolher o keyframe de ${pendentes} ${pendentes === 1 ? "cena" : "cenas"}.` : undefined}
      />
      <ol className="grid gap-4 lg:grid-cols-2" aria-label="Keyframes por cena">
        {roteiro.posicoes.map((p) => (
          <KeyframePosicao key={p.ordem} roteiroId={roteiro.id} version={roteiro.version} posicao={p} rodar={rodar} travado={travado} />
        ))}
      </ol>
    </div>
  );
}

function KeyframePosicao({
  roteiroId,
  version,
  posicao: p,
  rodar,
  travado,
}: {
  roteiroId: string;
  version: number;
  posicao: RoteiroPosicao;
} & Pick<EtapaProps, "rodar" | "travado">) {
  const queryClient = useQueryClient();
  const aberta = p.geracoesAbertas.find((g) => g.passo === "cena.keyframe");
  const usada = p.cena.status === "usada";
  const [regerando, setRegerando] = useState(false);
  const [instrucao, setInstrucao] = useState(p.cena.keyframeInstrucao ?? "");
  const [refs, setRefs] = useState<{ id: string; thumb: string | null }[] | null>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const [enviando, setEnviando] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const refsAtuais = refs ?? p.cena.keyframeRefs.filter((r) => !r.removida).map((r) => ({ id: r.imageId, thumb: r.thumbUrl }));
  const n = p.ordem + 1;

  async function regerar() {
    setBusy(true);
    const ok = await rodar(
      () => api.roteiros.regerarKeyframe(roteiroId, p.ordem, { version, instrucao: instrucao.trim() || null, referencias: refsAtuais.map((r) => r.id) }),
      `Novo keyframe da cena ${n} na fila.`,
    );
    setBusy(false);
    if (ok) {
      setRegerando(false);
      setRefs(null);
      void queryClient.invalidateQueries({ queryKey: cenaKey(p.cena.id) });
    }
  }

  async function enviar() {
    if (!arquivo) return;
    setError(null);
    setEnviando(0);
    try {
      const novo = await enviarKeyframe(roteiroId, p.ordem, version, arquivo, setEnviando);
      queryClient.setQueryData(roteiroKey(roteiroId), novo);
      setArquivo(null);
      setInputKey((k) => k + 1);
      await rodar(async () => novo, `Keyframe da cena ${n} enviado.`);
      void queryClient.invalidateQueries({ queryKey: cenaKey(p.cena.id) });
    } catch (err) {
      setError(err);
    } finally {
      setEnviando(null);
    }
  }

  return (
    <li className="space-y-3 rounded-xl border p-3" data-testid={`keyframe-cena-${n}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">
          Cena {n}: {p.cena.nome}
        </h3>
        {usada && <Badge variant="outline">usada</Badge>}
        <span className="text-xs text-muted-foreground tabular-nums">
          {p.cena.largura}×{p.cena.altura}
        </span>
      </div>
      {p.aviso && (
        <p role="status" className="text-sm text-warning-foreground" data-testid="aviso-posicao">
          {p.aviso}
        </p>
      )}
      <div className="grid grid-cols-[6rem_1fr] gap-3">
        <div className="aspect-[9/16] overflow-hidden rounded-md border bg-muted">
          {p.cena.keyframeUrl ? (
            <a href={p.cena.keyframeUrl} target="_blank" rel="noreferrer">
              <img src={p.cena.keyframeUrl} alt={`Keyframe da cena ${n}`} className="size-full object-cover" />
            </a>
          ) : (
            <span className="flex size-full items-center justify-center text-muted-foreground">
              <ImageOff className="size-5" aria-hidden="true" />
            </span>
          )}
        </div>
        <div className="min-w-0 space-y-2 text-sm">
          <p className="text-muted-foreground">{p.cena.keyframeUrl ? "Keyframe atual." : "Ainda sem keyframe."}</p>
          {p.cena.keyframeInstrucao && <p className="text-xs break-words text-muted-foreground" lang="en">{p.cena.keyframeInstrucao}</p>}
        </div>
      </div>

      <Andamentos geracoes={p.geracoesAbertas} filtro={(g) => g.passo === "cena.keyframe"} />
      {aberta && <OpcoesKeyframe geracaoId={aberta.id} alvoVersion={p.cena.version} disabled={travado || usada} onEscolhido={() => void invalidarRoteiro(queryClient, roteiroId)} />}

      {!travado && !usada && !aberta && (
        <div className="flex flex-wrap gap-2">
          {!regerando && (
            <Button type="button" variant="outline" size="sm" onClick={() => setRegerando(true)}>
              <RefreshCw aria-hidden="true" />
              Regerar esta cena
            </Button>
          )}
        </div>
      )}
      {usada && <p className="text-xs text-muted-foreground">Cena usada num vídeo: duplique para variar.</p>}

      {regerando && (
        <div className="space-y-3 rounded-lg bg-muted/40 p-3" data-testid={`regerar-keyframe-${n}`}>
          <Field label={`Instrução do keyframe da cena ${n} (inglês)`} hint="Descreva o estado final do quadro; não peça mudança de luz (recolore o produto).">
            {({ id, describedBy }) => (
              <Textarea id={id} rows={3} lang="en" value={instrucao} maxLength={LIM.instrucao} aria-describedby={describedBy} onChange={(e) => setInstrucao(e.target.value)} />
            )}
          </Field>
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Referências ({refsAtuais.length}/{LIM.referencias})</p>
            <ul className="flex flex-wrap gap-2" aria-label="Referências do keyframe">
              {refsAtuais.map((r) => (
                <li key={r.id} className="relative">
                  <span className="block size-14 overflow-hidden rounded-md border bg-muted">{r.thumb && <img src={r.thumb} alt="" className="size-full object-cover" />}</span>
                  <Button
                    type="button"
                    variant="secondary"
                    size="icon-xs"
                    className="absolute -top-1.5 -right-1.5"
                    aria-label="Tirar esta referência"
                    onClick={() => setRefs(refsAtuais.filter((x) => x.id !== r.id))}
                  >
                    <X aria-hidden="true" />
                  </Button>
                </li>
              ))}
            </ul>
            {refsAtuais.length < LIM.referencias && (
              <LibraryImageDialog
                perfilId={p.cena.perfilId}
                tipos={["avatar", "cenario", "imagem", "fundo"]}
                value={null}
                onPick={(image) => {
                  if (!refsAtuais.some((x) => x.id === image.id)) setRefs([...refsAtuais, { id: image.id, thumb: image.urls.thumb }]);
                }}
              />
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" disabled={busy} aria-busy={busy} onClick={() => void regerar()}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}
              Gerar 2 opções
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={() => {
                setRegerando(false);
                setRefs(null);
              }}
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}

      {!travado && !usada && (
        <div className="space-y-2 border-t pt-3">
          <Field label={`Keyframe pronto da cena ${n}`} hint={`PNG, JPG ou WebP, até 20 MB, em ${p.cena.largura}×${p.cena.altura}. Vira o keyframe sem passar pela GPU.`}>
            {({ id, describedBy }) => (
              <FileField key={inputKey} id={id} accept={KEYFRAME_ACCEPT} aria-describedby={describedBy} onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} />
            )}
          </Field>
          <Button type="button" variant="outline" size="sm" disabled={!arquivo || enviando !== null} aria-busy={enviando !== null} onClick={() => void enviar()}>
            {enviando !== null ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
            {enviando !== null ? `Enviando ${Math.round(enviando * 100)}%` : "Enviar keyframe"}
          </Button>
        </div>
      )}
      {error !== null && <ApiErrorAlert error={error} />}
    </li>
  );
}

function OpcoesKeyframe({ geracaoId, alvoVersion, disabled, onEscolhido }: { geracaoId: string; alvoVersion?: number; disabled?: boolean; onEscolhido: () => void }) {
  const geracao = useGeracao(geracaoId);
  if (!geracao.data) return null;
  return <OpcoesGeracao geracao={geracao.data} alvoVersion={alvoVersion} disabled={disabled} onRenovarLinks={() => void geracao.refetch()} onEscolhido={onEscolhido} />;
}
