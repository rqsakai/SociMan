/*
 * Importações da agência (spec 013, US7; FR-012a): data, autor, estado e contagens, as mais
 * recentes primeiro. Cada linha abre o detalhe (itens, resultado e "Desfazer" para o dono).
 */
import { Link } from "react-router-dom";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { importacaoPath, type ImportacaoResumo } from "@/lib/importacao";
import { formatDateTime } from "@/lib/tz";
import { EstadoBadge } from "./Andamento";

export function ListaImportacoes({ importacoes }: { importacoes: ImportacaoResumo[] }) {
  if (importacoes.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground" role="status">
        Nenhuma importação ainda.
      </p>
    );
  }
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <Table>
        <TableCaption className="sr-only">Importações da agência</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Importação</TableHead>
            <TableHead scope="col">Estado</TableHead>
            <TableHead scope="col" className="hidden text-right sm:table-cell">
              Criados
            </TableHead>
            <TableHead scope="col" className="hidden text-right sm:table-cell">
              Atualizados
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {importacoes.map((i) => (
            <TableRow key={i.id} data-importacao={i.estado}>
              <TableCell className="whitespace-normal">
                <Link to={importacaoPath(i.id)} className="font-medium text-primary underline-offset-2 hover:underline">
                  {formatDateTime(i.criadaEm)}
                </Link>
                <span className="block text-xs text-muted-foreground">por {i.criadaPor?.name ?? "—"}</span>
              </TableCell>
              <TableCell>
                <EstadoBadge estado={i.estado} />
              </TableCell>
              <TableCell className="hidden text-right tabular-nums sm:table-cell">{i.contagens.criado ?? 0}</TableCell>
              <TableCell className="hidden text-right tabular-nums sm:table-cell">{i.contagens.atualizado ?? 0}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
