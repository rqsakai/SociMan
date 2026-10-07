import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, History, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  emAndamento,
  fmtDataHora,
  formatGeracaoValue,
  geracaoFieldLabel,
  geracaoParada,
  geracoesKey,
  statusGeracaoLabel,
  statusGeracaoTone,
  useGeracao,
  useGeracaoVersoes,
  useGeracoesDoAlvo,
  type GeracaoAlvo,
  type GeracaoResumo,
} from "../../lib/geracoes";
import { VersionHistory } from "../VersionHistory";
import { AndamentoGeracao } from "./AndamentoGeracao";
import { OpcoesGeracao } from "./OpcoesGeracao";

// Gerações de um alvo (spec 021, T044): estado em pt-BR, erro, "Veio N de M", a limpeza das opções
// não escolhidas e o histórico. As abertas (na fila, gerando, em revisão, falhou) já mostram o
// andamento e as opções; as decididas abrem com "Ver opções".
export function ListaGeracoes({
  perfilId,
  alvoTipo,
  alvoId,
  alvoVersion,
  disabled,
  vazio = "Nenhuma geração ainda.",
}: {
  perfilId: string;
  alvoTipo: GeracaoAlvo;
  alvoId: string;
  alvoVersion?: number;
  disabled?: boolean;
  vazio?: string;
}) {
  const lista = useGeracoesDoAlvo(perfilId, alvoTipo, alvoId);
  const itens = lista.data?.pages.flatMap((p) => p.itens) ?? [];

  if (lista.isPending) {
    return (
      <p aria-live="polite" className="text-sm text-muted-foreground">
        Carregando…
      </p>
    );
  }
  if (lista.isError) return <ApiErrorAlert error={lista.error} onReload={() => void lista.refetch()} />;

  return (
    <div className="space-y-3">
      {itens.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="lista-geracoes">
          {vazio}
        </p>
      ) : (
        <ul aria-label="Gerações" data-testid="lista-geracoes" className="space-y-3">
          {itens.map((g) => (
            <ItemGeracao key={g.id} resumo={g} alvoVersion={alvoVersion} disabled={disabled} />
          ))}
        </ul>
      )}
      {lista.hasNextPage && (
        <Button type="button" variant="outline" size="sm" disabled={lista.isFetchingNextPage} onClick={() => void lista.fetchNextPage()}>
          {lista.isFetchingNextPage && <Loader2 className="animate-spin" aria-hidden="true" />}
          Ver mais gerações
        </Button>
      )}
    </div>
  );
}

const aberta = (g: GeracaoResumo) => !geracaoParada(g.status) || g.status === "revisao" || g.status === "falhou";

function ItemGeracao({ resumo, alvoVersion, disabled }: { resumo: GeracaoResumo; alvoVersion?: number; disabled?: boolean }) {
  const qc = useQueryClient();
  const [expandida, setExpandida] = useState(false);
  const mostrarDetalhe = aberta(resumo) || expandida;
  const detalhe = useGeracao(resumo.id, { enabled: mostrarDetalhe });
  const g = detalhe.data ?? resumo;

  // O detalhe (polling de 2 s) viu outro estado: a lista também precisa saber (ordem, "abertas").
  const statusDetalhe = detalhe.data?.status;
  useEffect(() => {
    if (statusDetalhe && statusDetalhe !== resumo.status) void qc.invalidateQueries({ queryKey: geracoesKey(resumo.perfilId) });
  }, [statusDetalhe, resumo.status, resumo.perfilId, qc]);

  const veioMenos = g.status === "revisao" && g.nCandidatos < g.nOpcoes;
  return (
    <li className="space-y-3 rounded-xl border p-4" data-testid="geracao-item" data-geracao-id={g.id} data-status={g.status}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 gap-3">
          {g.miniaturaEscolhido && !mostrarDetalhe && (
            <img src={g.miniaturaEscolhido} alt="Opção escolhida" className="size-14 shrink-0 rounded-md border object-cover" />
          )}
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={cn(statusGeracaoTone[g.status])} data-testid="estado-geracao">
                {statusGeracaoLabel[g.status]}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {fmtDataHora(g.createdAt)}
                {g.createdBy ? ` · ${g.createdBy.name}` : ""}
              </span>
              {veioMenos && (
                <span className="text-xs font-medium text-warning-foreground" data-testid="veio-n-de-m">
                  Veio {g.nCandidatos} de {g.nOpcoes}
                </span>
              )}
            </div>
            <p className="line-clamp-2 text-sm">{g.instrucao}</p>
            {g.referencias.length > 0 && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span>Referência:</span>
                {g.referencias.map((r) => (
                  <img key={r.id} src={r.urls.thumb} alt="" className="size-8 rounded border object-cover" />
                ))}
              </div>
            )}
            {g.status === "falhou" && g.erro && !mostrarDetalhe && <p className="text-sm text-destructive">{g.erro.message}</p>}
            {g.limpaEm && (
              <p className="text-xs text-muted-foreground" data-testid="limpeza-geracao">
                Opções não escolhidas removidas em {fmtDataHora(g.limpaEm)}
              </p>
            )}
            {g.deGeracaoId && <p className="text-xs text-muted-foreground">Pedida com "Gerar outras".</p>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {!aberta(resumo) && (
            <Button type="button" variant="ghost" size="sm" aria-expanded={expandida} onClick={() => setExpandida((v) => !v)}>
              {expandida ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
              {expandida ? "Esconder opções" : "Ver opções"}
            </Button>
          )}
          <HistoricoGeracao id={g.id} />
        </div>
      </div>

      {mostrarDetalhe && (
        <>
          {emAndamento(g.status) && <AndamentoGeracao geracao={g} />}
          {detalhe.isError && <ApiErrorAlert error={detalhe.error} onReload={() => void detalhe.refetch()} />}
          {detalhe.data ? (
            <OpcoesGeracao geracao={detalhe.data} alvoVersion={alvoVersion} disabled={disabled} onRenovarLinks={() => void detalhe.refetch()} />
          ) : (
            detalhe.isPending && (
              <p aria-live="polite" className="text-sm text-muted-foreground">
                Carregando opções…
              </p>
            )
          )}
        </>
      )}
    </li>
  );
}

function HistoricoGeracao({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const versoes = useGeracaoVersoes(id, open);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="ghost" size="sm">
          <History aria-hidden="true" />
          Histórico
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Histórico da geração</DialogTitle>
          <DialogDescription>Da versão mais recente para a mais antiga.</DialogDescription>
        </DialogHeader>
        <div className="max-h-[65vh] overflow-y-auto">
          {versoes.isPending && (
            <p aria-live="polite" className="text-sm text-muted-foreground">
              Carregando…
            </p>
          )}
          {versoes.isError && <ApiErrorAlert error={versoes.error} />}
          {versoes.data && <VersionHistory versions={versoes.data.items} labels={geracaoFieldLabel} formatValue={formatGeracaoValue} />}
        </div>
      </DialogContent>
    </Dialog>
  );
}
