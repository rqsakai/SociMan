/*
 * Cobertura do histórico do Studio (spec 020, US5; FR-022): uma barra em CSS por seção (Visão geral,
 * Seguidores) na mesma escala de dias, com as faixas importadas (Studio), a coleta da 016 (do 1º dia
 * coberto até hoje) e os buracos. Sem ECharts (a página fica fora da rota lazy do analytics). A
 * tabela abaixo é o caminho acessível: as mesmas faixas em texto.
 * Spec 022 (FR-028): as fotos de gênero e territórios como marcos (a data), as faixas e os buracos da
 * atividade e dos espectadores, e "veio sem dados em <data>" para as seções que chegaram vazias.
 */
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { dataBr, periodoBr, publicoDaCobertura, rotuloSecao, secaoLabel, type CoberturaStudio, type Faixa } from "@/lib/studio";
import { formatDateTime } from "@/lib/tz";
import { addDays, parseDateKey } from "@/lib/tz";

// dias de `de` a `ate`, inclusive
function diasEntre(de: string, ate: string): number {
  const a = parseDateKey(de);
  const b = parseDateKey(ate);
  return Math.round((Date.UTC(b.year, b.month - 1, b.day) - Date.UTC(a.year, a.month - 1, a.day)) / 86_400_000) + 1;
}

const TIPOS = {
  studio: { rotulo: "Importado do Studio", classe: "bg-primary" },
  coleta: { rotulo: "Coletado (API)", classe: "bg-success" },
  buraco: { rotulo: "Buraco (sem dado)", classe: "bg-destructive/70" },
  foto: { rotulo: "Foto de público", classe: "bg-foreground" },
} as const;
type Tipo = keyof typeof TIPOS;

// `inteira`: a barra das seções de público (sem coleta da API) usa a altura toda
function Segmento({ faixa, tipo, inicio, total, inteira = false }: { faixa: Faixa; tipo: Tipo; inicio: string; total: number; inteira?: boolean }) {
  const esquerda = (diasEntre(inicio, faixa.de) - 1) / total;
  const largura = diasEntre(faixa.de, faixa.ate) / total;
  return (
    <span
      className={`absolute inset-y-0 ${TIPOS[tipo].classe} ${tipo === "coleta" ? "top-1/2" : tipo === "studio" && !inteira ? "bottom-1/2" : ""}`}
      style={{ left: `${esquerda * 100}%`, width: `max(${largura * 100}%, 2px)` }}
      title={`${TIPOS[tipo].rotulo}: ${periodoBr(faixa)}`}
    />
  );
}

export function CoberturaBarras({ cobertura }: { cobertura: CoberturaStudio }) {
  const { coleta, secoes, hoje } = cobertura;
  const publico = publicoDaCobertura(cobertura);
  const ontem = addDays(hoje, -1);
  const faixaColeta: Faixa | null = coleta ? { de: coleta.primeiroDia, ate: hoje } : null;
  const semFaixas = { faixas: [], buracos: [] };
  const diarias = publico
    ? ([
        ["atividade", { ...semFaixas, ...publico.atividade }],
        ["espectadores", { ...semFaixas, ...publico.espectadores }],
      ] as const)
    : [];
  const fotos = publico?.fotos ?? [];
  const inicios = [
    ...secoes.flatMap((s) => [...s.faixas, ...s.buracos].map((f) => f.de)),
    ...diarias.flatMap(([, d]) => [...d.faixas, ...d.buracos].map((f) => f.de)),
    ...fotos.map((f) => f.dataFoto),
    ...(coleta ? [coleta.primeiroDia] : []),
  ];
  const semPublico = fotos.length === 0 && diarias.every(([, d]) => d.faixas.length === 0 && d.buracos.length === 0);
  const semNada = secoes.every((s) => s.faixas.length === 0 && s.buracos.length === 0) && semPublico;
  const inicio = inicios.length ? inicios.reduce((a, b) => (a < b ? a : b)) : ontem;
  const total = Math.max(1, diasEntre(inicio, hoje));

  const linhas: [string, Tipo, string][] = [];
  for (const s of secoes) {
    for (const f of s.faixas) linhas.push([secaoLabel[s.secao], "studio", periodoBr(f)]);
    for (const f of s.sobreposicao) linhas.push([secaoLabel[s.secao], "coleta", `${periodoBr(f)} (também no Studio; vale a API)`]);
    for (const f of s.buracos) linhas.push([secaoLabel[s.secao], "buraco", periodoBr(f)]);
  }
  for (const f of fotos) linhas.push([rotuloSecao(f.tipo), "foto", dataBr(f.dataFoto)]);
  for (const [secao, d] of diarias) {
    for (const f of d.faixas) linhas.push([rotuloSecao(secao), "studio", periodoBr(f)]);
    for (const f of d.buracos) linhas.push([rotuloSecao(secao), "buraco", periodoBr(f)]);
  }
  const vazias = publico?.vazias ?? [];
  const posicao = (dia: string) => `${((diasEntre(inicio, dia) - 0.5) / total) * 100}%`;

  return (
    <div className="space-y-4" data-cobertura>
      <p className="text-sm text-muted-foreground">
        {coleta
          ? `Coleta pela API desde ${dataBr(coleta.primeiroDia)}; dias inteiros cobertos a partir de ${dataBr(coleta.primeiroDiaCoberto)}. Antes disso vale o Studio.`
          : "Esta conta ainda não tem coleta pela API: só o Studio informa os dias."}
      </p>
      {semNada ? (
        <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground" role="status">
          Nenhum dia importado do Studio ainda.
        </p>
      ) : (
        <div className="space-y-3" aria-hidden="true">
          {secoes.map((s) => (
            <div key={s.secao} className="grid grid-cols-[6.5rem_1fr] items-center gap-2 text-sm">
              <span className="truncate">{secaoLabel[s.secao]}</span>
              <div className="relative h-5 overflow-hidden rounded bg-muted">
                {s.faixas.map((f) => (
                  <Segmento key={`s${f.de}`} faixa={f} tipo="studio" inicio={inicio} total={total} />
                ))}
                {faixaColeta && <Segmento faixa={faixaColeta} tipo="coleta" inicio={inicio} total={total} />}
                {s.buracos.map((f) => (
                  <Segmento key={`b${f.de}`} faixa={f} tipo="buraco" inicio={inicio} total={total} />
                ))}
              </div>
            </div>
          ))}
          {diarias.map(([secao, d]) => (
            <div key={secao} className="grid grid-cols-[6.5rem_1fr] items-center gap-2 text-sm" data-cobertura-secao={secao}>
              <span className="truncate">{rotuloSecao(secao)}</span>
              <div className="relative h-5 overflow-hidden rounded bg-muted">
                {d.faixas.map((f) => (
                  <Segmento key={`s${f.de}`} faixa={f} tipo="studio" inicio={inicio} total={total} inteira />
                ))}
                {d.buracos.map((f) => (
                  <Segmento key={`b${f.de}`} faixa={f} tipo="buraco" inicio={inicio} total={total} />
                ))}
              </div>
            </div>
          ))}
          {fotos.length > 0 && (
            <div className="grid grid-cols-[6.5rem_1fr] items-center gap-2 text-sm" data-cobertura-secao="fotos">
              <span className="truncate">Fotos de público</span>
              <div className="relative h-5 rounded bg-muted">
                {fotos.map((f) => (
                  <span
                    key={`${f.tipo}${f.dataFoto}${f.importacaoId}`}
                    className={`absolute inset-y-0 w-0.5 -translate-x-1/2 ${TIPOS.foto.classe}`}
                    style={{ left: posicao(f.dataFoto) }}
                    title={`${rotuloSecao(f.tipo)}: foto de ${dataBr(f.dataFoto)}`}
                  />
                ))}
              </div>
            </div>
          )}
          <div className="grid grid-cols-[6.5rem_1fr] gap-2 text-xs text-muted-foreground">
            <span />
            <span className="flex justify-between tabular-nums">
              <span>{dataBr(inicio)}</span>
              <span>{dataBr(hoje)}</span>
            </span>
          </div>
        </div>
      )}
      {vazias.length > 0 && (
        <ul className="space-y-0.5 text-sm text-muted-foreground" aria-label="Seções que vieram sem dados" data-cobertura-vazias>
          {vazias.map((v) => (
            <li key={v.secao}>
              {rotuloSecao(v.secao)}: veio sem dados em {formatDateTime(v.em)} (a TikTok libera os dados de público com cerca de 100 seguidores).
            </li>
          ))}
        </ul>
      )}
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Legenda da cobertura">
        {(Object.keys(TIPOS) as Tipo[]).filter((t) => t !== "foto" || fotos.length > 0).map((t) => (
          <li key={t} className="flex items-center gap-1.5">
            <span aria-hidden="true" className={`inline-block h-2.5 w-4 rounded-sm ${TIPOS[t].classe}`} />
            {TIPOS[t].rotulo}
          </li>
        ))}
      </ul>
      {linhas.length > 0 && (
        <Table>
          <TableCaption className="sr-only">Cobertura por seção</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Seção</TableHead>
              <TableHead scope="col">Fonte</TableHead>
              <TableHead scope="col">Período</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {linhas.map(([secao, tipo, periodo], i) => (
              <TableRow key={i} data-faixa={tipo}>
                <TableCell>{secao}</TableCell>
                <TableCell className="whitespace-normal">{TIPOS[tipo].rotulo}</TableCell>
                <TableCell className="whitespace-normal tabular-nums">{periodo}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
