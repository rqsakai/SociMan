/*
 * Tabela alternativa de um card (spec 019, FR-005; R1 cuidado 4): a versão acessível do gráfico,
 * com <caption> e cabeçalhos de coluna. As linhas são os mesmos valores brutos do CSV; cada coluna
 * pode formatar a exibição (`formatar`), o CSV sai sem formatação.
 */
import type { ReactNode } from "react";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { ValorCsv } from "./csv";

const numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

function exibir(v: ValorCsv): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return numero.format(v);
  if (typeof v === "boolean") return v ? "sim" : "não";
  return v;
}

export interface ColunaTabela {
  titulo: string;
  numerica?: boolean;
  /** some no celular (FR-008: miniatura, título curto e views ficam sempre) */
  secundaria?: boolean;
  formatar?: (v: ValorCsv, linha: ValorCsv[]) => ReactNode;
}

export interface DadosTabela {
  colunas: ColunaTabela[];
  linhas: ValorCsv[][];
}

export function TabelaAlternativa({ titulo, dados }: { titulo: string; dados: DadosTabela }) {
  return (
    <Table>
      <TableCaption className="sr-only">{titulo}</TableCaption>
      <TableHeader>
        <TableRow>
          {dados.colunas.map((c) => (
            <TableHead key={c.titulo} scope="col" className={cn(c.numerica && "text-right", c.secundaria && "hidden sm:table-cell")}>
              {c.titulo}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {dados.linhas.map((linha, i) => (
          <TableRow key={i}>
            {dados.colunas.map((c, j) => (
              <TableCell key={c.titulo} className={cn(c.numerica && "text-right tabular-nums", c.secundaria && "hidden sm:table-cell")}>
                {c.formatar ? c.formatar(linha[j], linha) : exibir(linha[j])}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
