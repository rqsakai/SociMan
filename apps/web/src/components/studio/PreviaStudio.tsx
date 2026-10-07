/*
 * Pré-visualização da importação (spec 020, US1/US2; FR-010): o período com a origem do ano, por
 * seção as contagens, os totais, as colunas e a amostra (primeiros e últimos dias, com a situação),
 * os avisos, a caixa "confirmo que é de @conta" (CSV solto) e "Confirmar importação" / "Cancelar".
 * Seção com o mesmo arquivo de uma importação ativa: "já importado em … por …", sem gravar nada;
 * com todas assim, não há botão de confirmar.
 * Spec 022: os blocos de público (gênero e territórios em tabela com a data da foto e a origem;
 * atividade com o pico; espectadores com os totais, o "sem dado" e a amostra) e as seções que vieram só
 * com o cabeçalho ("ainda sem dados de público", FR-006).
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
  dataFotoOrigemLabel,
  MENSAGEM_VAZIA,
  publicoDaPrevia,
  rotuloSecao,
  secaoLabel,
  situacaoLabel,
  totaisLabel,
  type ContagensPublico,
  type Previa,
  type PreviaSecao,
  type SecaoDiaria,
  type SecaoPublicoPrevia,
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
  const diaria = s.secao as SecaoDiaria;
  const colunas = colunasAmostra[diaria] ?? [];
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
        {(totaisLabel[diaria] ?? []).map(([chave, rotulo]) => (
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

const pct1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const formatPct = (v: number | null | undefined) => (v === null || v === undefined ? "sem dado" : `${pct1.format(v)}%`);
const qtd = (v: number | string[] | undefined) => (Array.isArray(v) ? v.length : (v ?? 0));
const fotoSituacao = { novo: "nova", igual: "igual à já importada", divergente: "diferente da já importada (vale a anterior)" } as const;

function ContagensPub({ c, foto }: { c: ContagensPublico; foto: boolean }) {
  const itens: [string, number][] = [
    [foto ? "rótulos a gravar" : "linhas a gravar", c.gravados],
    ["iguais ao já importado", c.iguais],
    ["diferentes do já importado", c.divergentes],
    ...(c.faltando !== undefined ? ([["faltando no arquivo", qtd(c.faltando)]] as [string, number][]) : []),
    ...(c.ignorados !== undefined ? ([["ignorados (hoje)", qtd(c.ignorados)]] as [string, number][]) : []),
    ["sem dado", c.semDado ?? 0],
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

function SecaoPublico({ s }: { s: SecaoPublicoPrevia }) {
  const rotulo = rotuloSecao(s.secao);
  return (
    <section className="space-y-3 rounded-lg border p-3 sm:p-4" data-secao={s.secao} data-vazia={s.vazia || undefined} aria-label={`Seção ${rotulo}`}>
      <h3 className="flex flex-wrap items-center gap-2 font-semibold">
        {rotulo}
        {s.vazia && <Badge variant="outline">sem dados</Badge>}
        {s.jaImportada && <Badge variant="secondary">já importado</Badge>}
      </h3>
      {s.vazia ? (
        <p className="text-sm text-muted-foreground" data-sem-dados-publico>
          {s.mensagem || MENSAGEM_VAZIA}
        </p>
      ) : (
        <>
          {s.jaImportada ? (
            <p className="text-sm text-muted-foreground" data-ja-importada>
              Este arquivo já foi importado em {formatDateTime(s.jaImportada.em)} por {s.jaImportada.por}. Nada desta seção será gravado.
            </p>
          ) : (
            s.contagens && <ContagensPub c={s.contagens} foto={s.secao === "genero" || s.secao === "territorios"} />
          )}
          {s.dataFoto && (
            <p className="text-sm" data-data-foto={s.dataFoto}>
              Foto de <span className="font-medium tabular-nums">{dataBr(s.dataFoto)}</span>
              {s.dataFotoOrigem && <span className="text-muted-foreground"> ({dataFotoOrigemLabel[s.dataFotoOrigem]})</span>}
              {s.situacao && s.situacao !== "novo" && <span className="text-muted-foreground">: {fotoSituacao[s.situacao]}</span>}
            </p>
          )}
          {s.periodo && (
            <p className="text-sm">
              <span className="font-medium tabular-nums">
                {dataBr(s.periodo.de)} a {dataBr(s.periodo.ate)}
              </span>{" "}
              <span className="text-muted-foreground">({anoOrigemLabel[s.periodo.anoOrigem]})</span>
            </p>
          )}
          {s.pico && (
            <p className="text-sm" data-pico>
              Pico: <span className="font-medium tabular-nums">{formatNumero(s.pico.ativos)}</span> seguidores ativos em {dataBr(s.pico.dia)}, às{" "}
              {String(s.pico.hora).padStart(2, "0")}h <span className="text-muted-foreground">(horas conforme a TikTok)</span>
            </p>
          )}
          {s.totais && (
            <dl className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
              {(
                [
                  ["Novos (soma)", formatNumero(s.totais.novos)],
                  ["Espectadores por dia (média)", s.totais.mediaTotal === null ? "—" : pct1.format(s.totais.mediaTotal)],
                  ["Recorrentes por dia (média)", s.totais.mediaRecorrentes === null ? "—" : pct1.format(s.totais.mediaRecorrentes)],
                ] as const
              ).map(([r, v]) => (
                <div key={r}>
                  <dt className="inline text-muted-foreground">{r}: </dt>
                  <dd className="inline font-medium tabular-nums">{v}</dd>
                </div>
              ))}
            </dl>
          )}
          {s.itens && s.itens.length > 0 && (
            <Table>
              <TableCaption className="sr-only">Distribuição de {rotulo}</TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">{s.secao === "genero" ? "Gênero" : "Território"}</TableHead>
                  <TableHead scope="col" className="text-right">
                    %
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {s.itens.map((i) => (
                  <TableRow key={i.rotulo}>
                    <TableCell>{i.rotuloExibicao}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatPct(i.pct)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {s.amostra && s.amostra.length > 0 && (
            <div className="-mx-1 overflow-x-auto px-1">
              <Table>
                <TableCaption className="sr-only">Amostra de {rotulo}</TableCaption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Dia</TableHead>
                    <TableHead scope="col" className="text-right">
                      Total
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Novos
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Recorr.
                    </TableHead>
                    <TableHead scope="col">Situação</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {s.amostra.map((l) => (
                    <TableRow key={l.dia} data-situacao={l.situacao}>
                      <TableCell className="tabular-nums">{dataBr(l.dia)}</TableCell>
                      {[l.total, l.novos, l.recorrentes].map((v, k) => (
                        <TableCell key={k} className={cn("text-right tabular-nums", v === null && "text-muted-foreground")}>
                          {v === null ? "sem dado" : formatNumero(v)}
                        </TableCell>
                      ))}
                      <TableCell className={cn("min-w-28 text-xs whitespace-normal", l.situacao !== "novo" && "text-muted-foreground")}>{situacaoLabel[l.situacao]}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
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
  const publico = publicoDaPrevia(previa);

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
          Arquivos: {previa.arquivos.map((a) => `${a.nome} (${rotuloSecao(a.secao)})`).join("; ")}.
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
      {publico.map((s) => (
        <SecaoPublico key={s.secao} s={s} />
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
