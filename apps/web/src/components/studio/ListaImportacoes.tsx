/*
 * Importações do Studio da conta (spec 020, US4; FR-022): data, autor, seções, período, dias e
 * estado, as mais recentes primeiro (as desfeitas também). "Desfazer" é só do dono, com AlertDialog:
 * os dias saem do analytics e da exportação, mas continuam guardados; reverter é importar de novo.
 */
import { Undo2 } from "lucide-react";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumero } from "@/lib/metricas";
import { dataBr, secaoLabel, type ImportacaoStudio } from "@/lib/studio";
import { formatDateTime } from "@/lib/tz";

function Estado({ i }: { i: ImportacaoStudio }) {
  if (i.estado === "ativa") return <Badge>ativa</Badge>;
  return (
    <>
      <Badge variant="secondary">desfeita</Badge>
      {i.desfeitaEm && (
        <span className="mt-0.5 block text-xs text-muted-foreground">
          por {i.desfeitaPor?.name ?? "—"} em {formatDateTime(i.desfeitaEm)}
        </span>
      )}
    </>
  );
}

const diasGravados = (i: ImportacaoStudio) => Math.max(0, ...Object.values(i.contagens).map((c) => c.gravados));

export function ListaImportacoes({
  importacoes,
  podeDesfazer,
  desfazendo,
  onDesfazer,
}: {
  importacoes: ImportacaoStudio[];
  podeDesfazer: boolean;
  desfazendo: string | null;
  onDesfazer: (imp: ImportacaoStudio) => Promise<void>;
}) {
  if (importacoes.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground" role="status">
        Nenhuma importação nesta conta.
      </p>
    );
  }
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <Table>
        <TableCaption className="sr-only">Importações do Studio</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col" className="hidden sm:table-cell">
              Importada em
            </TableHead>
            <TableHead scope="col">Período</TableHead>
            <TableHead scope="col" className="hidden sm:table-cell">
              Seções
            </TableHead>
            <TableHead scope="col" className="hidden text-right sm:table-cell">
              Dias
            </TableHead>
            <TableHead scope="col" className="hidden sm:table-cell">
              Estado
            </TableHead>
            {podeDesfazer && <TableHead scope="col" className="sr-only">Ações</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {importacoes.map((i) => (
            <TableRow key={i.id} data-importacao={i.estado}>
              <TableCell className="hidden sm:table-cell">
                <span className="block tabular-nums">{formatDateTime(i.criadaEm)}</span>
                <span className="block text-xs text-muted-foreground">por {i.criadaPor.name}</span>
              </TableCell>
              <TableCell className="tabular-nums">
                {dataBr(i.periodoDe)} a {dataBr(i.periodoAte)}
                <span className="block text-xs whitespace-normal text-muted-foreground sm:hidden">
                  {i.secoes.map((s) => secaoLabel[s]).join(" e ")} · importada em {formatDateTime(i.criadaEm)} por {i.criadaPor.name}
                </span>
                <span className="mt-1 block whitespace-normal sm:hidden">
                  <Estado i={i} />
                </span>
              </TableCell>
              <TableCell className="hidden sm:table-cell">{i.secoes.map((s) => secaoLabel[s]).join(" e ")}</TableCell>
              <TableCell className="hidden text-right tabular-nums sm:table-cell">{formatNumero(diasGravados(i))}</TableCell>
              <TableCell className="hidden whitespace-normal sm:table-cell">
                <Estado i={i} />
              </TableCell>
              {podeDesfazer && (
                <TableCell className="text-right">
                  {i.estado === "ativa" && (
                    <ConfirmButton
                      size="sm"
                      variant="ghost"
                      label="Desfazer"
                      icon={Undo2}
                      busy={desfazendo === i.id}
                      disabled={desfazendo !== null}
                      title="Desfazer esta importação?"
                      description={`Os dias de ${dataBr(i.periodoDe)} a ${dataBr(i.periodoAte)} saem do analytics e da exportação, mas continuam guardados. Para voltar, importe o arquivo de novo.`}
                      onConfirm={() => onDesfazer(i)}
                    />
                  )}
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
