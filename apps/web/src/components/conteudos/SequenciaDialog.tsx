/*
 * "Agendar em sequência" (spec 014, US4; R7): vários conteúdos, uma conta, a primeira data, os
 * horários de cada dia (chips HH:MM, 1 a 6), o modo e "Gerar textos com IA para os que não têm".
 *
 * 1. "Ver prévia": a API calcula sem gravar (tabela dia × item, intervalo mínimo da conta, horários
 *    pulados por conflito ou passado e os inelegíveis com o motivo).
 * 2. "Confirmar": manda a prévia mostrada como `esperado`; se alguém agendou no meio, a API responde
 *    409 `previa_desatualizada` com a prévia nova, que aparece aqui para conferir de novo.
 * 3. Textos: o SPA gera com a IA da 008 (até 3 chamadas ao mesmo tempo) para os destinos sem título
 *    e salva cada um com `PATCH /api/destinos/{id}` e o `ia`; os que falharem ficam "sem textos".
 */
import type { Destino, LoteResultado, Modo, Previa } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, Eye, Loader2, Plus, TriangleAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ProgressBar } from "@/components/marca/CorteStatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { invalidarConteudos, useEhDono } from "@/lib/conteudos";
import { padroesKey } from "@/lib/envios";
import { novoSessaoId } from "@/lib/ia";
import { contaPlatformText, perfilKey } from "@/lib/perfis";
import { DESCRICAO_MAX, HASHTAGS_MAX, previaNova, TITULO_MAX, usaLegenda } from "@/lib/postagem";
import { addDays, formatDateTime, formatLongDate, formatTime, localDateKey } from "@/lib/tz";
import { ModoSelect } from "./ModoSelect";

export interface ItemSequencia {
  id: string;
  titulo: string;
  perfilId: string;
}

const HORARIO_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
const MAX_HORARIOS = 6;
const PARALELO = 3;

type Fase = "config" | "previa" | "textos" | "fim";

export function SequenciaDialog({
  open,
  onOpenChange,
  itens,
  onDone,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  itens: ItemSequencia[];
  onDone?: () => void;
}) {
  const queryClient = useQueryClient();
  const perfis = [...new Set(itens.map((i) => i.perfilId))];
  const perfilId = perfis.length === 1 ? perfis[0]! : "";
  const perfil = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: open && Boolean(perfilId) });
  const padroes = useQuery({ queryKey: padroesKey(perfilId), queryFn: () => api.padroesCorte.get(perfilId), enabled: open && Boolean(perfilId) });
  const contas = (perfil.data?.contas ?? []).filter((c) => !c.archived);

  const dono = useEhDono();
  const [contaId, setContaId] = useState("");
  const [inicio, setInicio] = useState("");
  const [horarios, setHorarios] = useState<string[]>(["19:00"]);
  const [novoHorario, setNovoHorario] = useState("12:00");
  const [modo, setModo] = useState<Modo>("lembrete");
  const [gerarTextos, setGerarTextos] = useState(true);
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [desatualizada, setDesatualizada] = useState(false);
  const [fase, setFase] = useState<Fase>("config");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [resultado, setResultado] = useState<LoteResultado | null>(null);
  const [textos, setTextos] = useState<{ total: number; feitos: number; semTextos: string[] }>({ total: 0, feitos: 0, semTextos: [] });

  useEffect(() => {
    if (!open) return;
    setInicio(addDays(localDateKey(new Date()), 1));
    setHorarios(["19:00"]);
    setModo("lembrete");
    setPrevia(null);
    setDesatualizada(false);
    setFase("config");
    setError(null);
    setResultado(null);
    setTextos({ total: 0, feitos: 0, semTextos: [] });
  }, [open]);
  useEffect(() => {
    if (!open || contas.length === 0) return;
    const padrao = padroes.data?.padroes.contaPadraoId;
    setContaId(padrao && contas.some((c) => c.id === padrao) ? padrao : contas[0]!.id);
  }, [open, perfil.data, padroes.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const titulo = (id: string) => itens.find((i) => i.id === id)?.titulo || "Sem título";
  const conta = contas.find((c) => c.id === contaId);
  // spec 015 (T101): na TikTok, conteúdo sem legenda só entra se a IA for escrever os textos depois.
  const body = { contaId, conteudoIds: itens.map((i) => i.id), inicio, horarios, modo, gerarTextos };

  function addHorario() {
    if (!HORARIO_RE.test(novoHorario) || horarios.includes(novoHorario) || horarios.length >= MAX_HORARIOS) return;
    setHorarios((h) => [...h, novoHorario].sort());
    setPrevia(null);
  }

  async function verPrevia() {
    setError(null);
    setBusy(true);
    try {
      setPrevia(await api.agendamentos.sequenciaPrevia(body));
      setDesatualizada(false);
      setFase("previa");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function confirmar() {
    if (!previa) return;
    setError(null);
    setBusy(true);
    try {
      const r = await api.agendamentos.sequencia({ ...body, esperado: previa.slots });
      setResultado(r);
      await invalidarConteudos(queryClient);
      toast.success(`${r.ok.length} agendado(s) em sequência.`);
      // Na TikTok o que falta é a legenda (não há título, T102).
      const semTitulo = r.ok.filter((d) => (usaLegenda(d.conta.platform) ? !d.descricao.trim() : !d.titulo.trim()));
      if (gerarTextos && semTitulo.length > 0) {
        setFase("textos");
        await gerar(semTitulo);
      }
      setFase("fim");
      onDone?.();
    } catch (err) {
      const nova = previaNova(err);
      if (nova) {
        setPrevia(nova);
        setDesatualizada(true);
      } else setError(err);
    } finally {
      setBusy(false);
    }
  }

  // Textos pela IA para os destinos sem título, no máximo 3 ao mesmo tempo.
  async function gerar(destinos: Destino[]) {
    setTextos({ total: destinos.length, feitos: 0, semTextos: [] });
    const fila = [...destinos];
    const umPorVez = async () => {
      for (let d = fila.shift(); d; d = fila.shift()) {
        const ok = await gerarUm(d);
        setTextos((t) => ({ ...t, feitos: t.feitos + 1, semTextos: ok ? t.semTextos : [...t.semTextos, d.conteudoId] }));
      }
    };
    await Promise.all(Array.from({ length: Math.min(PARALELO, destinos.length) }, umPorVez));
    await invalidarConteudos(queryClient);
  }

  async function gerarUm(d: Destino): Promise<boolean> {
    try {
      const { chamada } = await api.ia.gerar({
        tipoCampo: "postagem.textos",
        perfilId,
        alvo: { entityType: "postagem", entityId: d.id },
        valorAtual: { titulo: "", descricao: "", hashtags: [] },
        instrucao: "",
        sessaoId: novoSessaoId(),
        anteriores: [],
      });
      const p = chamada.proposta;
      if (!p?.titulo || chamada.excede) return false;
      await api.destinos.update(d.id, {
        version: d.version,
        titulo: p.titulo.slice(0, TITULO_MAX),
        descricao: (p.descricao ?? "").slice(0, DESCRICAO_MAX),
        hashtags: (p.hashtags ?? []).slice(0, HASHTAGS_MAX),
        ia: [{ tipoCampo: "postagem.textos", chamadaId: chamada.id }],
      });
      return true;
    } catch {
      return false;
    }
  }

  const bloqueado = fase === "textos" || busy;

  return (
    <Dialog open={open} onOpenChange={(o) => !bloqueado && onOpenChange(o)}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Agendar em sequência</DialogTitle>
          <DialogDescription>
            {itens.length} conteúdo(s), na ordem da seleção. Horários a menos do intervalo mínimo da conta de outro post são pulados.
          </DialogDescription>
        </DialogHeader>

        {perfis.length > 1 ? (
          <Alert variant="destructive">
            <TriangleAlert aria-hidden="true" />
            <AlertTitle>Conteúdos de perfis diferentes</AlertTitle>
            <AlertDescription>A sequência vai para uma conta só: selecione conteúdos de um perfil.</AlertDescription>
          </Alert>
        ) : fase === "config" || fase === "previa" ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Conta de destino">
                {({ id }) => (
                  <NativeSelect
                    id={id}
                    value={contaId}
                    onChange={(e) => {
                      setContaId(e.target.value);
                      setPrevia(null);
                      setFase("config");
                    }}
                  >
                    {contas.length === 0 && <option value="">{perfil.isPending ? "Carregando…" : "Nenhuma conta ativa"}</option>}
                    {contas.map((c) => (
                      <option key={c.id} value={c.id}>
                        {contaPlatformText(c)} @{c.handle}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
              <Field label="Primeira data">
                {({ id }) => (
                  <Input
                    id={id}
                    type="date"
                    value={inicio}
                    min={localDateKey(new Date())}
                    onChange={(e) => {
                      setInicio(e.target.value);
                      setPrevia(null);
                      setFase("config");
                    }}
                  />
                )}
              </Field>
            </div>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Horários de cada dia (horário de Brasília; Enter adiciona)</legend>
              <ul aria-label="Horários escolhidos" className="flex flex-wrap gap-1.5">
                {horarios.map((h) => (
                  <li key={h}>
                    <Badge variant="secondary" className="gap-1 pr-1 tabular-nums">
                      {h}
                      {horarios.length > 1 && (
                        <button
                          type="button"
                          aria-label={`Tirar ${h}`}
                          className="rounded-full hover:bg-black/10"
                          onClick={() => {
                            setHorarios((cur) => cur.filter((x) => x !== h));
                            setPrevia(null);
                            setFase("config");
                          }}
                        >
                          <X className="size-3" aria-hidden="true" />
                        </button>
                      )}
                    </Badge>
                  </li>
                ))}
              </ul>
              {horarios.length < MAX_HORARIOS && (
                <div className="flex items-center gap-2">
                  <Input
                    type="time"
                    aria-label="Horários"
                    value={novoHorario}
                    onChange={(e) => setNovoHorario(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addHorario();
                      }
                    }}
                    className="w-32"
                  />
                  <Button type="button" variant="outline" size="sm" disabled={!HORARIO_RE.test(novoHorario) || horarios.includes(novoHorario)} onClick={addHorario}>
                    <Plus aria-hidden="true" />
                    Adicionar horário
                  </Button>
                </div>
              )}
            </fieldset>
            <ModoSelect
              contaId={contaId || null}
              value={modo}
              onChange={setModo}
              dono={dono}
              // spec 015: em lote só lembrete e criar rascunho; publicar exige a tela da TikTok por vídeo
              bloqueados={{ publicar: "Publicar exige a tela da TikTok para cada vídeo." }}
            />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4 accent-primary" checked={gerarTextos} onChange={(e) => setGerarTextos(e.target.checked)} />
              Gerar textos com IA para os que não têm
            </label>

            {previa && (
              <section aria-label="Prévia" className="space-y-3 rounded-lg border p-3">
                {desatualizada && (
                  <Alert>
                    <TriangleAlert aria-hidden="true" />
                    <AlertTitle>A prévia mudou</AlertTitle>
                    <AlertDescription>Alguém agendou nesta conta enquanto você conferia. Esta é a prévia nova; confira e confirme de novo.</AlertDescription>
                  </Alert>
                )}
                <p className="text-sm">
                  Intervalo mínimo de {conta ? `@${conta.handle}` : "da conta"}: <strong>{previa.intervaloMin} min</strong>.
                </p>
                {previa.slots.length > 0 ? (
                  <Table aria-label="Prévia da sequência">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs uppercase">Dia</TableHead>
                        <TableHead className="text-xs uppercase">Hora</TableHead>
                        <TableHead className="text-xs uppercase">Conteúdo</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {previa.slots.map((s) => (
                        <TableRow key={s.conteudoId}>
                          <TableCell className="capitalize">{formatLongDate(s.plannedAt)}</TableCell>
                          <TableCell className="tabular-nums">{formatTime(s.plannedAt)}</TableCell>
                          <TableCell className="max-w-64 truncate">{titulo(s.conteudoId)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-sm text-muted-foreground">Nenhum conteúdo elegível para agendar.</p>
                )}
                {previa.pulados.length > 0 && (
                  <div>
                    <p className="text-sm font-medium">Horários pulados</p>
                    <ul className="list-disc pl-5 text-sm text-muted-foreground">
                      {previa.pulados.map((p) => (
                        <li key={p.plannedAt}>
                          {formatDateTime(p.plannedAt)}: {p.motivo === "passado" ? "já passou" : "perto de outro post da conta"}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {previa.inelegiveis.length > 0 && (
                  <div>
                    <p className="text-sm font-medium">Fora da sequência</p>
                    <ul className="list-disc pl-5 text-sm text-muted-foreground">
                      {previa.inelegiveis.map((i) => (
                        <li key={i.conteudoId}>
                          {titulo(i.conteudoId)}: {i.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            )}
            {error !== null && <ApiErrorAlert error={error} />}
          </div>
        ) : (
          <div className="space-y-3" aria-live="polite">
            {resultado && (
              <p className="text-sm">
                <strong>{resultado.ok.length}</strong> agendado(s)
                {resultado.falhas.length > 0 ? `, ${resultado.falhas.length} com falha` : ""}.
              </p>
            )}
            {resultado && resultado.falhas.length > 0 && (
              <ul className="list-disc pl-5 text-sm text-destructive">
                {resultado.falhas.map((f, i) => (
                  <li key={`${f.conteudoId ?? f.destinoId}-${i}`}>
                    {f.conteudoId ? titulo(f.conteudoId) : "Item"}: {f.message}
                  </li>
                ))}
              </ul>
            )}
            {textos.total > 0 && (
              <div className="space-y-1">
                <ProgressBar value={textos.feitos / textos.total} label="Textos gerados pela IA" />
                <p className="text-xs text-muted-foreground">
                  Textos: {textos.feitos} de {textos.total}
                  {fase === "textos" ? " (gerando…)" : ""}
                </p>
              </div>
            )}
            {textos.semTextos.length > 0 && (
              <div>
                <p className="text-sm font-medium">Ficaram sem textos (prepare no detalhe):</p>
                <ul className="flex flex-wrap gap-1.5">
                  {textos.semTextos.map((id) => (
                    <li key={id}>
                      <Badge variant="outline">sem textos · {titulo(id)}</Badge>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          {fase === "config" || fase === "previa" ? (
            <>
              <Button type="button" variant="ghost" disabled={busy} onClick={() => onOpenChange(false)}>
                Cancelar
              </Button>
              <Button type="button" variant="outline" disabled={busy || !contaId || !inicio || perfis.length !== 1} aria-busy={busy && !previa} onClick={() => void verPrevia()}>
                {busy && !previa ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Eye aria-hidden="true" />}
                {previa ? "Atualizar prévia" : "Ver prévia"}
              </Button>
              <Button type="button" disabled={busy || !previa || previa.slots.length === 0} aria-busy={busy && Boolean(previa)} onClick={() => void confirmar()}>
                {busy && previa ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CalendarRange aria-hidden="true" />}
                Confirmar
              </Button>
            </>
          ) : (
            <Button type="button" disabled={fase === "textos"} onClick={() => onOpenChange(false)}>
              {fase === "textos" ? "Gerando textos…" : "Fechar"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

