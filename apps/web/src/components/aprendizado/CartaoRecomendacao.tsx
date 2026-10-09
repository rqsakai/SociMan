/*
 * Cartão de uma recomendação aberta (spec 023, US3; FR-034 a FR-039): o tipo, o alvo, o motivo, a
 * evidência no momento (efeito, intervalo, n e confiança), o que muda se aceitar e, para o dono,
 * Aceitar e Rejeitar (com motivo), ambos em AlertDialog. O servidor recalcula ao decidir: se a
 * evidência mudou, responde 409 `recomendacao_mudou` e a lista recarrega. "Fixar hashtag" numa conta
 * já no máximo de fixas pede qual fixa sai (409 `fixas_no_maximo`); proibida é recusada (400).
 */
import { ApiError } from "@sociman/contract";
import { Check, Loader2, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { formatIntervalo, fraseEfeito, tipoRecomendacaoLabel, type AprendizadoRecomendacao, type MedidaAprendizado } from "@/lib/aprendizado";
import { guiaContaPath, guiaPerfilPath } from "@/lib/guia";
import { formatNumero } from "@/lib/metricas";
import { formatDateTime } from "@/lib/tz";
import { ChipConfianca, textoAviso } from "./EfeitoLinha";

export function alvoTexto(r: Pick<AprendizadoRecomendacao, "alvo" | "tipo">): string {
  return r.alvo.temaNome ?? r.alvo.hashtag ?? r.alvo.padrao ?? tipoRecomendacaoLabel[r.tipo] ?? r.tipo;
}

export function CartaoRecomendacao({
  rec,
  perfilId,
  medida,
  contaRotulo,
  dono,
  onDecidido,
}: {
  rec: AprendizadoRecomendacao;
  perfilId: string;
  medida: MedidaAprendizado;
  contaRotulo: string | null;
  dono: boolean;
  onDecidido: () => Promise<unknown>;
}) {
  const [dialogo, setDialogo] = useState<"aceitar" | "rejeitar" | null>(null);
  const [motivo, setMotivo] = useState("");
  const [fixas, setFixas] = useState<string[] | null>(null);
  const [substituir, setSubstituir] = useState("");
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  const e = rec.evidencia;
  const titulo = `${tipoRecomendacaoLabel[rec.tipo] ?? rec.tipo}: ${alvoTexto(rec)}`;

  function abrir(d: "aceitar" | "rejeitar") {
    setErro(null);
    setFixas(null);
    setSubstituir("");
    setMotivo("");
    setDialogo(d);
  }

  async function decidir() {
    if (!dialogo) return;
    setBusy(true);
    setErro(null);
    try {
      const out = await api.aprendizado.decidir(perfilId, {
        chave: rec.chave,
        decisao: dialogo === "aceitar" ? "aceita" : "rejeitada",
        medida,
        ...(dialogo === "rejeitar" && motivo.trim() ? { motivo: motivo.trim() } : {}),
        ...(substituir ? { substituir } : {}),
      });
      if (dialogo === "rejeitar") toast.success("Recomendação rejeitada. Ela só volta se a evidência mudar bastante.");
      else if (out.guia) toast.success(`Hashtag fixada no guia ${out.guia.nivel === "conta" ? "da conta" : "do perfil"} (versão ${out.guia.version}).`);
      else toast.success("Recomendação aceita: as preferências ganharam uma versão nova.");
      setDialogo(null);
      await onDecidido();
    } catch (err) {
      if (err instanceof ApiError && err.code === "fixas_no_maximo") {
        const lista = Array.isArray(err.details.fixas) ? (err.details.fixas as string[]) : [];
        setFixas(lista);
        setSubstituir(lista[0] ?? "");
      } else if (err instanceof ApiError && err.code === "recomendacao_mudou") {
        toast.info("A evidência mudou desde que a lista carregou. A lista foi atualizada; confira de novo.");
        setDialogo(null);
        await onDecidido();
      } else {
        setErro(err);
      }
    } finally {
      setBusy(false);
    }
  }

  const linkGuia = rec.tipo === "hashtag_fixar" ? (rec.escopo.tipo === "conta" && rec.escopo.contaId ? guiaContaPath(rec.escopo.contaId) : guiaPerfilPath(perfilId)) : null;

  return (
    <li className="flex flex-col gap-2 rounded-lg border p-3" aria-label={titulo} data-chave={rec.chave}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-medium break-words">{titulo}</span>
            <Badge variant="outline">{rec.escopo.tipo === "conta" ? (contaRotulo ?? "conta") : "perfil"}</Badge>
            {rec.origem === "hipotese" && <Badge variant="secondary">da análise da IA</Badge>}
            {rec.jaRejeitadaEm && <Badge variant="outline">já rejeitada em {formatDateTime(rec.jaRejeitadaEm)}</Badge>}
          </p>
          <p className="text-sm">{rec.motivo}</p>
          {e && (
            <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground tabular-nums">
              <span>
                {fraseEfeito(e)} · intervalo {formatIntervalo(e)} · {formatNumero(e.nPosts)} posts em {formatNumero(e.nDias)} dias
              </span>
              <ChipConfianca confianca={e.confianca} />
              {e.avisos.map((a, i) => (
                <span key={i}>{textoAviso(a, e.parte)}</span>
              ))}
            </p>
          )}
          <p className="text-sm">
            <span className="font-medium">Se aceitar: </span>
            {rec.oQueMuda}
          </p>
          {rec.bloqueio && (
            <p className="text-xs text-warning-foreground" data-bloqueio={rec.bloqueio.code}>
              {rec.bloqueio.code === "fixas_no_maximo"
                ? `A conta já está no máximo de hashtags fixas${rec.bloqueio.fixas?.length ? ` (${rec.bloqueio.fixas.join(", ")})` : ""}: ao aceitar, escolha qual sai.`
                : rec.bloqueio.code}
            </p>
          )}
        </div>
        {dono && (
          <div className="flex flex-wrap gap-1.5">
            <Button type="button" size="sm" onClick={() => abrir("aceitar")} aria-label={`Aceitar: ${titulo}`}>
              <Check aria-hidden="true" />
              Aceitar
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => abrir("rejeitar")} aria-label={`Rejeitar: ${titulo}`}>
              <X aria-hidden="true" />
              Rejeitar
            </Button>
          </div>
        )}
      </div>

      <AlertDialog open={dialogo !== null} onOpenChange={(o) => !o && !busy && setDialogo(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{dialogo === "aceitar" ? "Aceitar" : "Rejeitar"} &quot;{titulo}&quot;?</AlertDialogTitle>
            <AlertDialogDescription>
              {dialogo === "aceitar"
                ? `${rec.oQueMuda} A decisão fica no histórico e pode ser revertida. Nada é agendado nem publicado.`
                : "A recomendação some e só volta se o número de posts que a sustenta dobrar ou a confiança mudar de faixa."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {dialogo === "rejeitar" && (
            <Field label="Motivo (opcional)">
              {({ id }) => <Textarea id={id} rows={2} maxLength={300} value={motivo} onChange={(ev) => setMotivo(ev.target.value)} />}
            </Field>
          )}
          {dialogo === "aceitar" && fixas !== null && (
            <div className="flex flex-col gap-2" role="group" aria-label="Escolher a fixa que sai">
              <p className="text-sm">A conta já está no máximo de hashtags fixas. Escolha qual sai para {alvoTexto(rec)} entrar:</p>
              <Field label="Hashtag fixa que sai">
                {({ id }) => (
                  <NativeSelect id={id} value={substituir} onChange={(ev) => setSubstituir(ev.target.value)}>
                    {fixas.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
              {linkGuia && (
                <Link to={linkGuia} className="text-xs underline">
                  Abrir o guia de comunicação
                </Link>
              )}
            </div>
          )}
          {erro !== null && <ApiErrorAlert error={erro} />}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancelar</AlertDialogCancel>
            <Button type="button" disabled={busy} aria-busy={busy} onClick={() => void decidir()}>
              {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
              {dialogo === "aceitar" ? (fixas ? "Substituir e aceitar" : "Aceitar") : "Rejeitar"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  );
}
