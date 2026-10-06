/*
 * Andamento e resultado de uma importação da agência (spec 013, US2; FR-011). Enquanto está
 * `processando`, a página consulta a cada 2 s (ver `useImportacaoAgencia`) e aqui aparecem a etapa,
 * os itens feitos e os MB gravados; no fim, o estado, as contagens e o erro (quando `falhou`).
 */
import { CircleAlert, CircleCheck, Loader2, Undo2 } from "lucide-react";
import { ProgressBar } from "@/components/marca/CorteStatusBadge";
import { Badge } from "@/components/ui/badge";
import { estadoLabel, etapaLabel, formatMB, type EstadoImportacao, type ImportacaoResumo } from "@/lib/importacao";
import { formatDateTime } from "@/lib/tz";

const estadoTone: Record<EstadoImportacao, string> = {
  processando: "bg-info text-info-foreground",
  concluida: "bg-success text-success-foreground",
  falhou: "bg-destructive text-destructive-foreground",
  desfeita: "bg-secondary text-secondary-foreground",
};

export function EstadoBadge({ estado }: { estado: EstadoImportacao }) {
  return (
    <Badge className={estadoTone[estado]} data-estado={estado}>
      {estadoLabel[estado]}
    </Badge>
  );
}

const CONTAGENS: [keyof ImportacaoResumo["contagens"], string][] = [
  ["criado", "criados"],
  ["atualizado", "atualizados"],
  ["mantido", "mantidos"],
  ["igual", "iguais"],
  ["fora", "fora"],
  ["naoGravado", "não gravados"],
];

export function ContagensImportacao({ imp }: { imp: ImportacaoResumo }) {
  return (
    <dl className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
      {CONTAGENS.map(([chave, rotulo]) => (
        <div key={chave} data-contagem={chave}>
          <dt className="inline text-muted-foreground">{rotulo}: </dt>
          <dd className="inline font-medium tabular-nums">{imp.contagens[chave] ?? 0}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Andamento({ imp }: { imp: ImportacaoResumo }) {
  const p = imp.progresso ?? {};
  const total = p.total ?? 0;
  const feitos = p.feitos ?? 0;
  return (
    <div className="space-y-3" data-andamento={imp.estado} aria-live="polite">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        {imp.estado === "processando" ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : imp.estado === "falhou" ? (
          <CircleAlert className="size-4 text-destructive" aria-hidden="true" />
        ) : imp.estado === "desfeita" ? (
          <Undo2 className="size-4" aria-hidden="true" />
        ) : (
          <CircleCheck className="size-4 text-success" aria-hidden="true" />
        )}
        <EstadoBadge estado={imp.estado} />
        <span className="text-muted-foreground">
          por {imp.criadaPor?.name ?? "—"} em {formatDateTime(imp.criadaEm)}
          {imp.concluidaEm && ` · terminou em ${formatDateTime(imp.concluidaEm)}`}
        </span>
      </p>
      {imp.estado === "processando" && (
        <div className="space-y-1">
          <ProgressBar value={total > 0 ? feitos / total : 0} label="Andamento da importação" />
          <p className="text-xs text-muted-foreground">
            {p.etapa ? etapaLabel[p.etapa] : "Começando"}
            {total > 0 && ` · ${feitos} de ${total}`}
            {p.bytes ? ` · ${formatMB(p.bytes)}` : ""}. Você pode sair desta tela: a gravação continua.
          </p>
        </div>
      )}
      {imp.estado === "falhou" && imp.erro && (
        <p className="text-sm text-destructive" role="alert">
          {imp.erro} Nada foi gravado no cadastro.
        </p>
      )}
      {imp.estado === "desfeita" && imp.desfeitaEm && (
        <p className="text-sm text-muted-foreground">
          Desfeita por {imp.desfeitaPor?.name ?? "—"} em {formatDateTime(imp.desfeitaEm)}.
        </p>
      )}
      {imp.estado !== "processando" && <ContagensImportacao imp={imp} />}
    </div>
  );
}
