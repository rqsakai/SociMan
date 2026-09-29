/*
 * "Enviar para corte" (spec 006, US3; T054). Mostra os vídeos selecionados de um perfil, a
 * configuração pré-preenchida pelos padrões de corte do perfil (ajustável só para este envio) e
 * envia tudo de uma vez (POST /api/envios/enviar, tudo ou nada, até 20).
 *
 * <EnviarDialog open onOpenChange perfilId envios onSent />
 *   - vídeo de canal "Sem acordo" ou avulso: antes de enviar, o AvisoDireito (AlertDialog);
 *     o 409 `aviso_direito` da API também abre o aviso;
 *   - 409 `already_sent`: pede confirmação de duplicado e reenvia com `confirmarDuplicado`.
 */
import { ApiError } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Scissors, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { padroesApiField, padroesKey, validatePadroes, type Envio, type EnvioConfig } from "@/lib/envios";
import { DireitoBadge } from "../canais/DireitoBadge";
import { AvisoDireito, type AvisoItem } from "./AvisoDireito";
import { ConfigCampos, configFrom, type ConfigValues } from "./ConfigCampos";

export const MAX_LOTE = 20;

export const envioTitulo = (e: Pick<Envio, "video" | "sourceTitle" | "sourceUrl">) =>
  e.video?.title ?? (e.sourceTitle || e.sourceUrl || "Vídeo avulso");

export const envioDireito = (e: Pick<Envio, "origem" | "canal">): AvisoItem["direito"] =>
  e.origem === "canal" && e.canal ? e.canal.direito : "avulso";

export function EnviarDialog({
  open,
  onOpenChange,
  perfilId,
  perfilName,
  envios,
  onSent,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  perfilId: string;
  perfilName?: string;
  envios: Envio[];
  onSent?: (enviados: Envio[]) => void;
}) {
  const queryClient = useQueryClient();
  const padroes = useQuery({ queryKey: padroesKey(perfilId), queryFn: () => api.padroesCorte.get(perfilId), enabled: open });
  const [config, setConfig] = useState<ConfigValues | null>(null);
  const [removed, setRemoved] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [sending, setSending] = useState(false);
  const [aviso, setAviso] = useState(false);
  const [duplicado, setDuplicado] = useState(false);
  const [lastFlags, setLastFlags] = useState({ confirmarAviso: false, confirmarDuplicado: false });

  // Padrões do perfil entram quando o diálogo abre; as mudanças valem só para este envio.
  const base = padroes.data?.padroes;
  useEffect(() => {
    if (open && base) setConfig(configFrom(base));
  }, [open, base]);
  useEffect(() => {
    if (!open) {
      setRemoved([]);
      setErrors({});
      setError(null);
      setLastFlags({ confirmarAviso: false, confirmarDuplicado: false });
    }
  }, [open]);

  const items = envios.filter((e) => !removed.includes(e.id)).slice(0, MAX_LOTE);
  const avisoItems: AvisoItem[] = items.filter((e) => e.precisaAviso).map((e) => ({ id: e.id, titulo: envioTitulo(e), direito: envioDireito(e) }));

  // Só manda o que difere dos padrões (o servidor completa com os padrões e o kit).
  function override(): Partial<EnvioConfig> | undefined {
    if (!config || !base) return undefined;
    const diff: Partial<EnvioConfig> = {};
    for (const key of Object.keys(config) as (keyof ConfigValues)[]) {
      if (config[key] !== (base[key] ?? null)) (diff as Record<string, unknown>)[key] = config[key];
    }
    return Object.keys(diff).length > 0 ? diff : undefined;
  }

  function start() {
    if (!config) return;
    const errs = validatePadroes(config);
    setErrors(errs);
    if (Object.keys(errs).length > 0 || items.length === 0) return;
    if (avisoItems.length > 0) setAviso(true);
    else void send({ confirmarAviso: false, confirmarDuplicado: false });
  }

  async function send(flags: { confirmarAviso: boolean; confirmarDuplicado: boolean }) {
    setError(null);
    setSending(true);
    try {
      const res = await api.envios.enviar({
        items: items.map((e) => ({ envioId: e.id, version: e.version })),
        config: override(),
        confirmarAviso: flags.confirmarAviso || undefined,
        confirmarDuplicado: flags.confirmarDuplicado || undefined,
      });
      toast.success(res.items.length === 1 ? "Vídeo enviado para corte." : `${res.items.length} vídeos enviados para corte.`, {
        description: "Você recebe uma notificação no sino quando terminar.",
      });
      await queryClient.invalidateQueries({ queryKey: ["envios"] });
      await queryClient.invalidateQueries({ queryKey: ["videos-fonte"] });
      onOpenChange(false);
      onSent?.(res.items);
    } catch (err) {
      if (err instanceof ApiError && err.code === "aviso_direito") setAviso(true);
      else if (err instanceof ApiError && err.code === "already_sent") setDuplicado(true);
      else if (err instanceof ApiError && err.code === "invalid_config" && err.field) {
        setErrors({ [padroesApiField[err.field] ?? err.field]: err.message });
      } else setError(err);
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Enviar para corte</DialogTitle>
            <DialogDescription>
              {items.length === 1 ? "1 vídeo" : `${items.length} vídeos`}
              {perfilName ? ` para ${perfilName}` : ""}. A configuração vem dos padrões de corte do perfil; mudar aqui vale só para
              este envio.
            </DialogDescription>
          </DialogHeader>

          <ul aria-label="Vídeos do envio" className="max-h-48 space-y-1.5 overflow-y-auto rounded-md border p-2">
            {items.map((e) => (
              <li key={e.id} className="flex items-center gap-2 text-sm">
                <span className="min-w-0 flex-1 truncate">{envioTitulo(e)}</span>
                {e.precisaAviso && <DireitoBadge direito={envioDireito(e)} />}
                {items.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    aria-label={`Tirar do envio: ${envioTitulo(e)}`}
                    onClick={() => setRemoved((r) => [...r, e.id])}
                  >
                    <X aria-hidden="true" />
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {envios.length > MAX_LOTE && (
            <p className="text-xs text-muted-foreground">Vão os {MAX_LOTE} primeiros; envie o resto em seguida.</p>
          )}

          {padroes.isError && <ApiErrorAlert error={padroes.error} />}
          {config ? (
            <ConfigCampos value={config} onChange={setConfig} errors={errors} disabled={sending} />
          ) : (
            <Skeleton className="h-40 w-full" />
          )}
          <p className="text-xs text-muted-foreground">O gancho automático do OpenShorts fica desligado: o gancho vem do kit do perfil.</p>

          {error !== null && <ApiErrorAlert error={error} />}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="button" disabled={!config || sending || items.length === 0} aria-busy={sending} onClick={start}>
              {sending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Scissors aria-hidden="true" />}
              {items.length === 1 ? "Enviar 1 vídeo" : `Enviar ${items.length} vídeos`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AvisoDireito
        open={aviso}
        onOpenChange={setAviso}
        items={avisoItems.length > 0 ? avisoItems : items.map((e) => ({ id: e.id, titulo: envioTitulo(e), direito: envioDireito(e) }))}
        onConfirm={() => {
          const flags = { ...lastFlags, confirmarAviso: true };
          setLastFlags(flags);
          void send(flags);
        }}
      />

      <AlertDialog open={duplicado} onOpenChange={setDuplicado}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Vídeo já enviado para este perfil</AlertDialogTitle>
            <AlertDialogDescription>
              Pelo menos um destes vídeos já foi enviado para corte neste perfil. Enviar de novo gera outro job no OpenShorts.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                const flags = { ...lastFlags, confirmarDuplicado: true };
                setLastFlags(flags);
                void send(flags);
              }}
            >
              Enviar mesmo assim
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
