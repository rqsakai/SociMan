/*
 * Tela obrigatória da TikTok para "Publicar no horário" (spec 015, US3; T088; research R13).
 *
 * <TikTokPostForm contaId conteudo legenda inicial? onChange />
 *   - consulta o criador NA HORA (GET /api/contas/{id}/conexao/criador): apelido, @ e foto;
 *     `podePostar = false` para a tela;
 *   - privacidade sem valor padrão, só as opções que a conta permite (no sandbox, só "Só eu", com o
 *     motivo nas outras);
 *   - comentários, dueto e costura desmarcados; bloqueados (e desligados) quando a conta os desligou;
 *   - divulgação comercial ("Sua marca" ou "Conteúdo de marca"): parceria paga não pode ser "só você";
 *   - conteúdo gerado por IA; a frase de consentimento de música (e da Política de Conteúdo de Marca);
 *   - prévia do vídeo e da legenda; "a TikTok leva alguns minutos para processar".
 * `onChange(opcoes)` recebe as opções completas e válidas, ou `null` enquanto falta escolher algo
 * (o AgendarDialog deixa "Agendar" desabilitado).
 */
import type { Criador, OpcoesTikTok } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { Info, Loader2, RefreshCw, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import {
  comercialLabel,
  consentimentoTexto,
  opcoesProblemas,
  privacidadeLabel,
  PRIVACIDADES,
  type Comercial,
  type Privacidade,
} from "@/lib/publicacao";

interface Rascunho {
  privacidade: Privacidade | "";
  permitirComentario: boolean;
  permitirDueto: boolean;
  permitirCostura: boolean;
  comercial: Comercial;
  conteudoIa: boolean;
}

const VAZIO: Rascunho = {
  privacidade: "",
  permitirComentario: false,
  permitirDueto: false,
  permitirCostura: false,
  comercial: "nenhum",
  conteudoIa: false,
};

function deOpcoes(o: OpcoesTikTok | null | undefined): Rascunho {
  if (!o) return VAZIO;
  return {
    privacidade: o.privacidade,
    permitirComentario: o.permitirComentario,
    permitirDueto: o.permitirDueto,
    permitirCostura: o.permitirCostura,
    comercial: o.comercial ?? "nenhum",
    conteudoIa: o.conteudoIa ?? false,
  };
}


export function TikTokPostForm({
  contaId,
  videoUrl,
  posterUrl,
  legenda,
  inicial,
  onChange,
}: {
  contaId: string;
  videoUrl?: string | null;
  posterUrl?: string | null;
  legenda: string;
  inicial?: OpcoesTikTok | null;
  onChange: (opcoes: OpcoesTikTok | null) => void;
}) {
  // Sem cache: a TikTok exige os dados da conta consultados ao abrir a tela.
  const criador = useQuery({
    queryKey: ["conexao-criador", contaId],
    queryFn: () => api.conexoes.criador(contaId),
    staleTime: 0,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const c: Criador | undefined = criador.data?.criador;
  const [r, setR] = useState<Rascunho>(() => deOpcoes(inicial));
  const set = (patch: Partial<Rascunho>) => setR((x) => ({ ...x, ...patch }));

  // A conta desligou uma interação: fica desmarcada e bloqueada.
  useEffect(() => {
    if (!c) return;
    setR((x) => ({
      ...x,
      permitirComentario: c.comentarioDesligado ? false : x.permitirComentario,
      permitirDueto: c.duetoDesligado ? false : x.permitirDueto,
      permitirCostura: c.costuraDesligada ? false : x.permitirCostura,
    }));
  }, [c]);

  const comercial = r.comercial;
  const texto = consentimentoTexto(comercial);
  const problemas = useMemo(() => (c ? opcoesProblemas(c, { privacidade: r.privacidade, comercial }) : []), [c, r, comercial]);
  const valido = Boolean(c?.podePostar) && r.privacidade !== "" && problemas.length === 0;

  useEffect(() => {
    if (!valido || r.privacidade === "") return onChange(null);
    onChange({
      privacidade: r.privacidade,
      permitirComentario: r.permitirComentario,
      permitirDueto: r.permitirDueto,
      permitirCostura: r.permitirCostura,
      comercial,
      conteudoIa: r.conteudoIa,
      // aceitar = agendar com a frase à vista (a TikTok pede a frase, não uma caixa)
      consentimento: { texto, aceitoEm: new Date().toISOString() },
    });
  }, [valido, r, comercial, texto]); // eslint-disable-line react-hooks/exhaustive-deps

  if (criador.isPending) {
    return (
      <div className="space-y-2 rounded-lg border p-3" aria-busy="true">
        <p className="flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Consultando a conta na TikTok…
        </p>
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (criador.isError || !c) {
    return (
      <div className="space-y-2">
        <ApiErrorAlert error={criador.error} />
        <Button type="button" size="sm" variant="outline" onClick={() => void criador.refetch()}>
          <RefreshCw aria-hidden="true" />
          Consultar de novo
        </Button>
      </div>
    );
  }

  const sandbox = c.situacaoApp === "sandbox";
  const opcaoMotivo = (p: Privacidade): string | null => {
    if (!c.privacyLevelOptions.includes(p)) return sandbox ? "sem auditoria da TikTok, só \"Só eu\"" : "a conta não permite";
    if (p === "SELF_ONLY" && comercial === "parceria_paga") return "parceria paga não pode ser só você";
    return null;
  };

  const toggle = (label: string, checked: boolean, desligado: boolean, onToggle: (v: boolean) => void) => (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" className="size-4 accent-primary" checked={checked} disabled={desligado} onChange={(e) => onToggle(e.target.checked)} />
      <span className={desligado ? "text-muted-foreground" : undefined}>
        {label}
        {desligado && " (desligado nas configurações da conta)"}
      </span>
    </label>
  );

  return (
    <fieldset className="space-y-4 rounded-lg border p-3" aria-label="Publicar na TikTok">
      <legend className="px-1 text-sm font-medium">Publicar na TikTok</legend>

      <div className="flex items-center gap-3">
        {c.avatarUrl ? (
          <img src={c.avatarUrl} alt="" className="size-10 rounded-full bg-muted object-cover" />
        ) : (
          <span className="size-10 rounded-full bg-muted" aria-hidden="true" />
        )}
        <div className="min-w-0">
          <p className="font-semibold">{c.displayName}</p>
          <p className="text-xs text-muted-foreground">Publicando como @{c.username}</p>
        </div>
      </div>

      {!c.podePostar ? (
        <Alert variant="destructive" role="alert">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>A TikTok não deixa esta conta postar agora</AlertTitle>
          <AlertDescription>Tente mais tarde ou crie um rascunho no lugar.</AlertDescription>
        </Alert>
      ) : (
        <>
          {sandbox && (
            <Alert>
              <Info aria-hidden="true" />
              <AlertTitle>App sem auditoria da TikTok</AlertTitle>
              <AlertDescription>O post sai só para você ("Só eu") e a conta precisa estar privada no app. Para publicar para todos, use "Criar rascunho".</AlertDescription>
            </Alert>
          )}

          <Field label="Privacidade" hint="Quem pode ver este vídeo. Escolha uma opção: a TikTok não aceita valor padrão.">
            {({ id, describedBy }) => (
              <NativeSelect id={id} aria-describedby={describedBy} value={r.privacidade} onChange={(e) => set({ privacidade: e.target.value as Privacidade | "" })}>
                <option value="" disabled>
                  Escolha…
                </option>
                {PRIVACIDADES.map((p) => {
                  const motivo = opcaoMotivo(p);
                  return (
                    <option key={p} value={p} disabled={motivo !== null}>
                      {privacidadeLabel[p]}
                      {motivo ? ` (${motivo})` : ""}
                    </option>
                  );
                })}
              </NativeSelect>
            )}
          </Field>

          <div className="space-y-1.5" role="group" aria-label="Interações">
            {toggle("Permitir comentários", r.permitirComentario, c.comentarioDesligado, (v) => set({ permitirComentario: v }))}
            {toggle("Permitir dueto", r.permitirDueto, c.duetoDesligado, (v) => set({ permitirDueto: v }))}
            {toggle("Permitir costura", r.permitirCostura, c.costuraDesligada, (v) => set({ permitirCostura: v }))}
          </div>

          <Field
            label="Divulgação comercial"
            hint={
              comercial === "sua_marca"
                ? "Você promove a si mesmo ou o seu negócio: o vídeo sai marcado como \"Conteúdo promocional\"."
                : comercial === "parceria_paga"
                  ? "Você promove outra marca ou terceiro: o vídeo sai marcado como \"Parceria paga\" e não pode ser só você."
                  : "Marque se o vídeo promove você, o seu negócio ou outra marca."
            }
          >
            {({ id, describedBy }) => (
              <NativeSelect id={id} aria-describedby={describedBy} value={comercial} onChange={(e) => set({ comercial: e.target.value as Comercial })}>
                {(["nenhum", "sua_marca", "parceria_paga"] as const).map((v) => (
                  <option key={v} value={v}>
                    {comercialLabel[v]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={r.conteudoIa} onChange={(e) => set({ conteudoIa: e.target.checked })} />
            Conteúdo gerado por IA
          </label>

          {problemas.length > 0 && (
            <Alert variant="destructive">
              <TriangleAlert aria-hidden="true" />
              <AlertTitle>Ajuste antes de agendar</AlertTitle>
              <AlertDescription>
                <ul className="list-disc pl-5">
                  {problemas.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          <div className="space-y-2" aria-label="Prévia" role="group">
            <p className="text-sm font-medium">Prévia</p>
            <div className="flex gap-3">
              {videoUrl ? (
                <video src={videoUrl} poster={posterUrl ?? undefined} controls playsInline preload="metadata" aria-label="Prévia do vídeo" className="h-48 w-auto rounded-md bg-black" />
              ) : (
                <Skeleton className="h-48 w-28 rounded-md" />
              )}
              <p className="min-w-0 flex-1 text-xs whitespace-pre-wrap text-muted-foreground">{legenda || "Sem legenda."}</p>
            </div>
            <p className="text-xs text-muted-foreground">Duração máxima nesta conta: {Math.floor(c.duracaoMaximaS / 60)} min {c.duracaoMaximaS % 60} s.</p>
          </div>

          <p className="text-xs text-muted-foreground">{texto}</p>
          <p className="text-xs text-muted-foreground">Depois do horário, a TikTok leva alguns minutos para processar o vídeo antes de ele aparecer no perfil.</p>
        </>
      )}
    </fieldset>
  );
}
