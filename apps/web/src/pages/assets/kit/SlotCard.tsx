import { Loader2, Lock, RefreshCw, TriangleAlert, Upload } from "lucide-react";
import { useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { GeracaoAberta } from "@/components/geracao/GeracaoAberta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { FileField } from "@/components/ui/file-field";
import { cn } from "@/lib/utils";
import { fileRule, uploadAssetFile, type Asset } from "@/lib/assets";
import type { AssetFileEnviado } from "@sociman/contract";
import { arquivoDoSlot, NOTA_MINIMA, passoDoKit, slotLabel, type KitSlot, type PassoConfig } from "@/lib/padrao";
import { PedirPasso } from "./PedirPasso";

// Um passo do kit do avatar (spec 025, US1/US3/US6, T019): os slots que ele preenche (o par 3/4 tem
// dois), a nota e a observação da checagem, o bloqueio com o motivo, a geração aberta com as opções
// (o par lado a lado), o pedido de opções, "Refazer este passo" e "Enviar no slot".
export function SlotCard({
  asset,
  config,
  numero,
  temConsentimento,
  onEnviado,
}: {
  asset: Asset;
  config: PassoConfig;
  numero: number;
  temConsentimento: boolean;
  onEnviado: (r: AssetFileEnviado) => Promise<void>;
}) {
  const kit = asset.kit!;
  const slots = config.slots.map((s) => kit.slots.find((k) => k.slot === s)).filter((s): s is KitSlot => Boolean(s));
  const passo = passoDoKit(asset, config.passo);
  const preenchido = slots.length > 0 && slots.every((s) => s.fileId);
  const refazerSugerido = slots.some((s) => s.refazer);
  const slotAberto = slots.every((s) => s.aberto);
  const motivo = slots.find((s) => !s.aberto)?.motivo ?? passo?.motivo ?? null;
  const [refazendo, setRefazendo] = useState(false);
  const travado = asset.archived || asset.revogado;
  const titulo = config.passo === "avatar.rostos_34" ? "Rostos 3/4" : slotLabel[config.slots[0]!];
  const geracao = passo?.geracaoAberta ?? null;
  const podePedir = Boolean(passo?.aberto) && !geracao && !travado && (!preenchido || refazendo);

  return (
    <li
      aria-label={`Passo ${numero}: ${titulo}`}
      data-testid={`slot-${config.slots[0]}`}
      className={cn("space-y-4 rounded-xl border p-4", refazerSugerido && "border-warning")}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">
          {numero}. {titulo}
        </h3>
        <div className="flex flex-wrap items-center gap-1.5">
          {preenchido ? (
            <Badge className="bg-success text-success-foreground">Escolhido</Badge>
          ) : slotAberto && passo?.aberto !== false ? (
            <Badge variant="secondary">A fazer</Badge>
          ) : (
            <Badge variant="outline">
              <Lock aria-hidden="true" />
              Bloqueado
            </Badge>
          )}
        </div>
      </div>

      {!slotAberto && motivo && (
        <p className="text-sm text-muted-foreground" data-testid="motivo-bloqueio">
          {motivo}
        </p>
      )}

      {slots.some((s) => s.fileId) && (
        <div className={cn("grid gap-3", slots.length > 1 && "grid-cols-2")}>
          {slots.map((s) => {
            const f = arquivoDoSlot(asset, s.fileId);
            return (
              <figure key={s.slot} className="space-y-1.5" data-testid={`slot-arquivo-${s.slot}`}>
                {f ? (
                  <a href={f.downloadUrl} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg border bg-muted">
                    <img src={f.image.urls.medium} alt={slotLabel[s.slot]} className="aspect-square w-full object-cover" />
                  </a>
                ) : (
                  <div className="aspect-square rounded-lg border border-dashed bg-muted/40" />
                )}
                <figcaption className="space-y-0.5 text-xs">
                  <span className="font-medium">{slotLabel[s.slot]}</span>
                  {f && <span className="text-muted-foreground"> · {f.origemArquivo === "gerado" ? "gerado" : "enviado"}</span>}
                  {s.nota !== null && (
                    <span className="block" data-testid={`nota-${s.slot}`}>
                      <Badge className={s.nota >= NOTA_MINIMA ? "bg-success text-success-foreground" : "bg-warning text-warning-foreground"}>
                        Nota {s.nota}/10
                      </Badge>{" "}
                      {s.observacao && <span className="text-muted-foreground">{s.observacao}</span>}
                    </span>
                  )}
                </figcaption>
              </figure>
            );
          })}
        </div>
      )}

      {refazerSugerido && !geracao && (
        <p className="flex items-start gap-1.5 text-sm" role="status">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
          Nota abaixo de {NOTA_MINIMA}: a identidade ficou diferente da origem neste passo.
        </p>
      )}

      {geracao && (
        <GeracaoAberta resumo={geracao} alvoVersion={asset.version} disabled={travado} onEscolhido={() => setRefazendo(false)} />
      )}

      {preenchido && !geracao && passo?.aberto && !travado && !refazendo && (
        <Button type="button" variant={refazerSugerido ? "default" : "outline"} size="sm" onClick={() => setRefazendo(true)}>
          <RefreshCw aria-hidden="true" />
          Refazer este passo
        </Button>
      )}

      {podePedir && (
        <div className="space-y-2 rounded-lg bg-muted/40 p-3">
          <PedirPasso
            perfilId={asset.perfilId}
            alvoTipo="asset"
            alvoId={asset.id}
            passo={config.passo}
            n={config.n}
            instrucao={config.instrucao ?? undefined}
            submitLabel={config.n === 4 ? "Gerar 4 opções" : "Gerar 2 opções"}
          />
          {refazendo && (
            <Button type="button" variant="ghost" size="sm" onClick={() => setRefazendo(false)}>
              Desistir de refazer
            </Button>
          )}
        </div>
      )}

      {slotAberto && !geracao && !travado && config.slots.length === 1 && (
        <EnviarNoSlot asset={asset} slot={config.slots[0]!} temConsentimento={temConsentimento} onEnviado={onEnviado} />
      )}
    </li>
  );
}

// "Enviar no slot": uma imagem pronta vira o arquivo do slot (sem gerar opções). No rosto de origem,
// a origem é "Upload" (feita em outra ferramenta) ou "Pessoa real" (exige o consentimento antes).
function EnviarNoSlot({
  asset,
  slot,
  temConsentimento,
  onEnviado,
}: {
  asset: Asset;
  slot: KitSlot["slot"];
  temConsentimento: boolean;
  onEnviado: (r: AssetFileEnviado) => Promise<void>;
}) {
  const ehOrigem = slot === "rosto_origem";
  const [origem, setOrigem] = useState<"upload" | "pessoa_real">(asset.origem === "pessoa_real" ? "pessoa_real" : "upload");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const [progresso, setProgresso] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [aberto, setAberto] = useState(false);
  const rule = fileRule.avatar;

  if (!aberto) {
    return (
      <Button type="button" variant="ghost" size="sm" onClick={() => setAberto(true)}>
        <Upload aria-hidden="true" />
        Enviar no slot
      </Button>
    );
  }

  async function enviar() {
    if (!arquivo) return;
    setError(null);
    setProgresso(0);
    try {
      const r = await uploadAssetFile(asset.id, arquivo, { role: "kit", slot, ...(ehOrigem ? { origem } : {}) }, setProgresso);
      setArquivo(null);
      setInputKey((k) => k + 1);
      setAberto(false);
      await onEnviado(r);
    } catch (err) {
      setError(err);
    } finally {
      setProgresso(null);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-dashed p-3" data-testid={`enviar-${slot}`}>
      {ehOrigem && (
        <Field
          label="Origem da foto"
          hint={
            origem === "pessoa_real"
              ? temConsentimento
                ? "Foto de uma pessoa real, com o consentimento registrado."
                : "Registre o consentimento da pessoa em \"Origem e consentimento\" antes de enviar."
              : "Imagem feita em outra ferramenta, que não é de uma pessoa real."
          }
        >
          {({ id, describedBy }) => (
            <NativeSelect id={id} value={origem} aria-describedby={describedBy} onChange={(e) => setOrigem(e.target.value as "upload" | "pessoa_real")}>
              <option value="upload">Upload (não é pessoa real)</option>
              <option value="pessoa_real">Pessoa real</option>
            </NativeSelect>
          )}
        </Field>
      )}
      <Field label={`Imagem para ${slotLabel[slot].toLowerCase()}`} hint={rule.hint}>
        {({ id, describedBy }) => (
          <FileField
            key={inputKey}
            id={id}
            accept={rule.accepted.join(",")}
            aria-describedby={describedBy}
            onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
          />
        )}
      </Field>
      {error !== null && <ApiErrorAlert error={error} />}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" disabled={!arquivo || progresso !== null} aria-busy={progresso !== null} onClick={() => void enviar()}>
          {progresso !== null ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
          {progresso !== null ? `Enviando ${Math.round(progresso * 100)}%` : "Enviar imagem"}
        </Button>
        <Button type="button" variant="ghost" size="sm" disabled={progresso !== null} onClick={() => setAberto(false)}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}
