/*
 * Pré-visualização da importação (spec 020, US1/US2; FR-010): o período com a origem do ano, por
 * seção as contagens, os totais, as colunas e a amostra (primeiros e últimos dias, com a situação),
 * os avisos, a caixa "confirmo que é de @conta" (CSV solto) e "Confirmar importação" / "Cancelar".
 * Seção com o mesmo arquivo de uma importação ativa: "já importado em … por …", sem gravar nada;
 * com todas assim, não há botão de confirmar.
 */
import { CircleAlert, Info, Loader2 } from "lucide-react";
import { useId, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumero } from "@/lib/metricas";
import {
  anoOrigemLabel,
  colunasAmostra,
  dataBr,
  secaoLabel,
  situacaoLabel,
  totaisLabel,
  type Previa,
  type PreviaSecao,
} from "@/lib/studio";
import { formatDateTime } from "@/lib/tz";
import { cn } from "@/lib/utils";
import { ErroStudio } from "./EnvioArquivos";

function Contagens({ s }: { s: PreviaSecao }) {
  const c = s.contagens;
  const itens: [string, number][] = [
    ["dias a gravar", c.gravados],
    ["coletados (vale a API)", c.coletados],
    ["iguais ao já importado", c.iguais],
    ["diferentes do já importado", c.divergentes],
    ["faltando no arquivo", c.faltando.length],
    ["ignorados (hoje)", c.ignorados.length],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
      {itens.map(([rotulo, n]) => (
        <div key={rotulo} className="flex items-baseline justify-between gap-2 sm:block">
          <dt className="text-muted-foreground">{rotulo}</dt>
          <dd className="font-semibold tabular-nums">{formatNumero(n)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Secao({ s }: { s: PreviaSecao }) {
  const colunas = colunasAmostra[s.secao];
  return (
    <section className="space-y-3 rounded-lg border p-3 sm:p-4" data-secao={s.secao} aria-label={`Seção ${secaoLabel[s.secao]}`}>
      <h3 className="flex flex-wrap items-center gap-2 font-semibold">
        {secaoLabel[s.secao]}
        {s.jaImportada && <Badge variant="secondary">já importado</Badge>}
      </h3>
      {s.jaImportada ? (
        <p className="text-sm text-muted-foreground" data-ja-importada>
          Este arquivo já foi importado em {formatDateTime(s.jaImportada.em)} por {s.jaImportada.por}. Nada desta seção será gravado.
        </p>
      ) : (
        <Contagens s={s} />
      )}
      <dl className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {totaisLabel[s.secao].map(([chave, rotulo]) => (
          <div key={chave}>
            <dt className="inline text-muted-foreground">{rotulo}: </dt>
            <dd className="inline font-medium tabular-nums">{formatNumero((s.totais as Record<string, number | null | undefined>)[chave])}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-muted-foreground">
        Colunas lidas: {s.colunas.reconhecidas.join(", ") || "—"}
        {s.colunas.ausentes.length > 0 && `. Ausentes: ${s.colunas.ausentes.join(", ")}`}
        {s.colunas.ignoradas.length > 0 && `. Ignoradas: ${s.colunas.ignoradas.join(", ")}`}.
      </p>
      {s.amostra.length > 0 && (
        <div className="-mx-1 overflow-x-auto px-1">
          <Table>
            <TableCaption className="sr-only">Amostra de {secaoLabel[s.secao]}</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Dia</TableHead>
                {colunas.map(([chave, rotulo]) => (
                  <TableHead key={chave} scope="col" className="text-right">
                    {rotulo}
                  </TableHead>
                ))}
                <TableHead scope="col">Situação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {s.amostra.map((l) => (
                <TableRow key={l.dia} data-situacao={l.situacao}>
                  <TableCell className="tabular-nums">{dataBr(l.dia)}</TableCell>
                  {colunas.map(([chave]) => (
                    <TableCell key={chave} className="text-right tabular-nums">
                      {formatNumero((l as Record<string, unknown>)[chave] as number | null | undefined)}
                    </TableCell>
                  ))}
                  <TableCell className={cn("min-w-28 text-xs whitespace-normal", l.situacao !== "novo" && "text-muted-foreground")}>{situacaoLabel[l.situacao]}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}

export function PreviaStudio({
  previa,
  confirmando,
  erro,
  onConfirmar,
  onCancelar,
}: {
  previa: Previa;
  confirmando: boolean;
  erro: unknown;
  onConfirmar: (confirmoConta: boolean) => void;
  onCancelar: () => void;
}) {
  const idCaixa = useId();
  const [confirmoConta, setConfirmoConta] = useState(false);
  const liberado = previa.podeConfirmar && (!previa.exigeConfirmacaoConta || confirmoConta);
  const ignorados = previa.arquivos.flatMap((a) => a.ignorados.map((n) => `${n} (${a.nome})`));

  return (
    <div className="space-y-4" data-previa>
      <div className="space-y-1">
        <p className="text-sm">
          <span className="font-semibold">
            {dataBr(previa.periodo.de)} a {dataBr(previa.periodo.ate)}
          </span>{" "}
          <span className="text-muted-foreground">({anoOrigemLabel[previa.periodo.anoOrigem]})</span>
        </p>
        <p className="text-xs text-muted-foreground">
          Arquivos: {previa.arquivos.map((a) => `${a.nome} (${secaoLabel[a.secao]})`).join("; ")}.
          {ignorados.length > 0 && ` Ignorados, sem abrir: ${ignorados.join("; ")}.`} Nada foi gravado ainda.
        </p>
      </div>

      {previa.avisos.length > 0 && (
        <Alert data-avisos>
          <Info aria-hidden="true" />
          <AlertTitle>Avisos</AlertTitle>
          <AlertDescription>
            <ul className="list-disc space-y-0.5 pl-5">
              {previa.avisos.map((a) => (
                <li key={a.codigo} data-aviso={a.codigo}>
                  {a.mensagem}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {previa.secoes.map((s) => (
        <Secao key={s.secao} s={s} />
      ))}

      {!previa.podeConfirmar ? (
        <p className="flex items-center gap-2 text-sm font-medium" role="status" data-ja-importado>
          <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
          Estes arquivos já foram importados; não há nada novo para gravar.
        </p>
      ) : (
        previa.exigeConfirmacaoConta && (
          <div className="flex items-start gap-2 rounded-lg border border-warning/50 bg-warning/5 p-3">
            <Checkbox id={idCaixa} checked={confirmoConta} onCheckedChange={(v) => setConfirmoConta(v === true)} className="mt-0.5" />
            <Label htmlFor={idCaixa} className="text-sm leading-snug font-normal">
              Confirmo que este arquivo é de @{previa.conta.handle} (um CSV solto não traz o @ da conta).
            </Label>
          </div>
        )
      )}

      {erro ? <ErroStudio error={erro} /> : null}

      <div className="flex flex-wrap gap-2">
        {previa.podeConfirmar && (
          <Button type="button" disabled={!liberado || confirmando} aria-busy={confirmando} onClick={() => onConfirmar(confirmoConta)}>
            {confirmando && <Loader2 className="animate-spin" aria-hidden="true" />}
            Confirmar importação
          </Button>
        )}
        <Button type="button" variant="outline" onClick={onCancelar} disabled={confirmando}>
          {previa.podeConfirmar ? "Cancelar" : "Fechar"}
        </Button>
      </div>
    </div>
  );
}
