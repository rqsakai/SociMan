import { Check, ExternalLink, Loader2, RefreshCw, RotateCcw, XCircle, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
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
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  metricasAudio,
  podeCancelar,
  useAcaoGeracao,
  useEscolherGeracao,
  type Candidato,
  type Geracao,
  type ImagemCandidato,
} from "../../lib/geracoes";
import { PlayerAudio } from "./PlayerAudio";

// Opções de uma geração (spec 021, T027/T044/T054): grade numerada, imagens grandes lado a lado
// para comparar (com o par quando há `imagemPar`), áudio com o teste e as métricas; "Usar opção N"
// e as ações da geração ("Gerar outras", "Cancelar geração", "Tentar de novo"), todas com
// confirmação em AlertDialog. O botão de confirmar repete o rótulo da ação (como o ConfirmButton).
export function OpcoesGeracao({
  geracao,
  alvoVersion,
  onRenovarLinks,
  onEscolhido,
  disabled,
}: {
  geracao: Geracao;
  // A versão do alvo lida pela tela (controle otimista da escolha). Sem ela, não há "Usar opção".
  alvoVersion?: number;
  onRenovarLinks: () => void;
  onEscolhido?: (numero: number) => void;
  disabled?: boolean;
}) {
  const escolher = useEscolherGeracao();
  const cancelar = useAcaoGeracao("cancelar");
  const tentar = useAcaoGeracao("tentarDeNovo");
  const outras = useAcaoGeracao("gerarOutras");
  const [erro, setErro] = useState<unknown>(null);
  const ocupado = escolher.isPending || cancelar.isPending || tentar.isPending || outras.isPending;

  const candidatos = [...geracao.candidatos].sort((a, b) => a.numero - b.numero);
  const emRevisao = geracao.status === "revisao";
  const podeEscolher = emRevisao && !geracao.semEscolha && alvoVersion !== undefined && !disabled;

  async function rodar(acao: () => Promise<unknown>, ok: string): Promise<boolean> {
    setErro(null);
    try {
      await acao();
      toast.success(ok);
      return true;
    } catch (err) {
      setErro(err);
      return false;
    }
  }

  async function usar(c: Candidato) {
    if (alvoVersion === undefined) return;
    if (await rodar(() => escolher.mutateAsync({ geracao, candidatoId: c.id, alvoVersion }), `Opção ${c.numero} escolhida.`)) {
      onEscolhido?.(c.numero);
    }
  }

  return (
    <div className="space-y-4" data-testid="opcoes-geracao">
      {geracao.status === "falhou" && geracao.erro && (
        <p role="alert" className="text-sm text-destructive" data-testid="erro-geracao">
          {geracao.erro.message}
        </p>
      )}

      {candidatos.length > 0 && (
        <ul aria-label="Opções" className={cn("grid gap-4", candidatos.length > 1 && "md:grid-cols-2")}>
          {candidatos.map((c) => {
            const escolhida = geracao.escolhidoId === c.id;
            return (
              <li
                key={c.id}
                data-testid={`opcao-${c.numero}`}
                className={cn("space-y-3 rounded-xl border p-3", escolhida && "ring-2 ring-success")}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-semibold">Opção {c.numero}</h3>
                  <div className="flex items-center gap-1.5">
                    {escolhida && <Badge className="bg-success text-success-foreground">Escolhida</Badge>}
                    {c.seed !== null && <span className="text-xs text-muted-foreground tabular-nums">seed {c.seed}</span>}
                  </div>
                </div>

                {(c.imagem || c.imagemPar) && (
                  <div className={cn("grid gap-2", c.imagem && c.imagemPar && "grid-cols-2")}>
                    {c.imagem && <ImagemOpcao imagem={c.imagem} alt={`Opção ${c.numero}${c.imagemPar ? ", lado esquerdo" : ""}`} onErro={onRenovarLinks} />}
                    {c.imagemPar && <ImagemOpcao imagem={c.imagemPar} alt={`Opção ${c.numero}, lado direito`} onErro={onRenovarLinks} />}
                  </div>
                )}

                {c.audio && <AudioOpcao candidato={c} onRenovar={onRenovarLinks} />}

                {podeEscolher && (
                  <Confirmar
                    label={`Usar opção ${c.numero}`}
                    icon={Check}
                    variant="default"
                    busy={escolher.isPending && escolher.variables?.candidatoId === c.id}
                    disabled={ocupado}
                    title={`Usar a opção ${c.numero}?`}
                    description="A opção escolhida vai para o item, e a geração fica decidida. As outras opções são apagadas 90 dias depois."
                    onConfirm={() => usar(c)}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}

      {!disabled && podeCancelar(geracao.status) && (
        <div className="flex flex-wrap gap-2">
          {emRevisao && (
            <Confirmar
              label="Gerar outras"
              icon={RefreshCw}
              busy={outras.isPending}
              disabled={ocupado}
              title="Gerar outras opções?"
              description="Estas opções são descartadas e uma geração nova entra na fila, com outras seeds e o mesmo pedido."
              onConfirm={() => void rodar(() => outras.mutateAsync(geracao), "Nova geração na fila.")}
            />
          )}
          {geracao.status === "falhou" && (
            <Confirmar
              label="Tentar de novo"
              icon={RotateCcw}
              busy={tentar.isPending}
              disabled={ocupado}
              title="Tentar de novo?"
              description="A geração volta para a fila com o mesmo pedido."
              onConfirm={() => void rodar(() => tentar.mutateAsync(geracao), "A geração voltou para a fila.")}
            />
          )}
          {podeCancelar(geracao.status) && (
            <Confirmar
              label="Cancelar geração"
              icon={XCircle}
              busy={cancelar.isPending}
              disabled={ocupado}
              title="Cancelar esta geração?"
              description={
                geracao.status === "rodando"
                  ? "O motor para no próximo passo. Nada vai para o item."
                  : "Nada vai para o item. Para gerar de novo, faça um pedido novo."
              }
              onConfirm={() => void rodar(() => cancelar.mutateAsync(geracao), "Geração cancelada.")}
            />
          )}
        </div>
      )}

      {erro !== null && <ApiErrorAlert error={erro} onReload={() => { setErro(null); onRenovarLinks(); }} />}
    </div>
  );
}

function ImagemOpcao({ imagem, alt, onErro }: { imagem: ImagemCandidato; alt: string; onErro: () => void }) {
  return (
    <figure className="space-y-1">
      <a href={imagem.link.url} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg border bg-muted">
        <img
          src={imagem.url}
          alt={alt}
          width={imagem.width}
          height={imagem.height}
          className="h-auto w-full object-contain"
          onError={onErro}
        />
      </a>
      <figcaption className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="tabular-nums">
          {imagem.width} × {imagem.height}
        </span>
        <a href={imagem.link.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
          <ExternalLink className="size-3" aria-hidden="true" />
          Original
        </a>
      </figcaption>
    </figure>
  );
}

const fmtSeg = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const fmtPct = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 0 });

function AudioOpcao({ candidato, onRenovar }: { candidato: Candidato; onRenovar: () => void }) {
  const m = metricasAudio(candidato.metricas);
  return (
    <div className="space-y-2">
      {candidato.audio && <PlayerAudio audio={candidato.audio} rotulo={`Áudio da opção ${candidato.numero}`} onRenovar={onRenovar} />}
      {candidato.testeAudio && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Áudio de teste</p>
          <PlayerAudio audio={candidato.testeAudio} rotulo={`Áudio de teste da opção ${candidato.numero}`} onRenovar={onRenovar} />
        </div>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm" data-testid={`metricas-opcao-${candidato.numero}`}>
        {m.segundos !== null && (
          <>
            <dt className="text-muted-foreground">Duração</dt>
            <dd className="tabular-nums">{fmtSeg.format(m.segundos)} s</dd>
          </>
        )}
        {m.similaridade !== null && (
          <>
            <dt className="text-muted-foreground">Similaridade</dt>
            <dd className="tabular-nums">{fmtPct.format(m.similaridade)}</dd>
          </>
        )}
        {m.transcricao !== null && (
          <>
            <dt className="text-muted-foreground">Transcrição</dt>
            <dd className="italic">“{m.transcricao}”</dd>
          </>
        )}
      </dl>
    </div>
  );
}

function Confirmar({
  label,
  icon: Icon,
  busy,
  disabled,
  title,
  description,
  onConfirm,
  variant = "outline",
}: {
  label: string;
  icon: LucideIcon;
  busy?: boolean;
  disabled?: boolean;
  title: string;
  description: ReactNode;
  onConfirm: () => Promise<void> | void;
  variant?: "default" | "outline";
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button type="button" variant={variant} disabled={busy || disabled} aria-busy={busy}>
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Icon aria-hidden="true" />}
          {label}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Voltar</AlertDialogCancel>
          <AlertDialogAction onClick={() => void onConfirm()}>{label}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
