/*
 * /app/calendario (spec 006, US5; T071; R14). Componente próprio, sem biblioteca: grade CSS.
 *
 * - Visões "Semana" (7 colunas × 24 h, padrão) e "Mês" (7 × 6), no fuso da agência.
 * - Filtros de perfil e plataforma; cada postagem com a cor do perfil e o ícone da plataforma.
 * - Arrastar (HTML5 nativo, desktop): soltar uma postagem remarca com encaixe de 15 min, com
 *   atualização otimista, "Desfazer" no aviso e volta ao lugar no 409.
 * - Coluna "Sem data" (spec 014, R11): primeiro os destinos aprovados sem data, depois os conteúdos
 *   prontos sem agendamento; arrastar um para a grade (ou tocar nele) abre o AgendarDialog comum
 *   com o horário já preenchido (o membro, diante de um não aprovado, vê "Pedir aprovação").
 * - Toque (celular/PWA): o arrastar nativo não funciona; tocar numa postagem abre "Remarcar".
 * - spec 014: cartões com o modo e o estado efetivo ("A postar" e "Atrasado" em destaque), filtro de
 *   conta, e remarcar por `lote/reagendar`; perto de outro post da conta, o aviso do intervalo
 *   mínimo oferece "Manter mesmo assim".
 * Nada é publicado: na hora, o sino avisa "Hora de postar".
 * - spec 015: chips com os estados do envio automático (enviando, pausado, vencido, aguardando
 *   vaga, falhou, rascunho criado); envio automático só o dono remarca; "Remarcar" mostra o motivo.
 */
import { ApiError, type Platform } from "@sociman/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CalendarClock, ChevronLeft, ChevronRight, ExternalLink, Film, Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { PageHeading } from "@/components/PageHeading";
import { PlatformIcon } from "@/components/PlatformIcon";
import { usePageMeta } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { AgendarDialog } from "@/components/conteudos/AgendarDialog";
import { EstadoBadge } from "@/components/conteudos/EstadoBadge";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { estadoEfetivoLabel, propostaDe, useConteudo, useEhDono } from "@/lib/conteudos";
import { ehAutomatico, faseLabel } from "@/lib/publicacao";
import { contaPlatformText, errorText, perfilKey, platformLabel } from "@/lib/perfis";
import { calendarioKey, modoLabel, type CalendarioItem, type CalendarioSemData } from "@/lib/postagem";
import {
  addDays,
  formatDateTime,
  formatTime,
  fromLocal,
  fromLocalInput,
  localDateKey,
  localParts,
  parseDateKey,
  toIsoWithOffset,
  toLocalInput,
  weekdayOf,
} from "@/lib/tz";
import { perfilColor, textOn, usePerfisAtivos } from "@/lib/usePerfis";
import { cn } from "@/lib/utils";

const HOUR_PX = 48;
const SLOT_MIN = 15;
const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const monthFormat = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric", timeZone: "UTC" });
const dayFormat = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", timeZone: "UTC" });

type View = "semana" | "mes";
type DragPayload = { kind: "postagem"; id: string } | { kind: "semData"; key: string };

// Chave de um item "sem data" (o mesmo conteúdo pode aparecer por mais de uma conta).
const semDataKey = (s: CalendarioSemData) => `${s.conteudoId}:${s.contaId ?? ""}`;

const weekStart = (key: string) => addDays(key, -((weekdayOf(key) + 6) % 7));
const utcDate = (key: string) => {
  const { year, month, day } = parseDateKey(key);
  return new Date(Date.UTC(year, month - 1, day));
};

function range(view: View, anchor: string): { de: string; ate: string; days: string[] } {
  if (view === "semana") {
    const de = weekStart(anchor);
    const days = Array.from({ length: 7 }, (_, i) => addDays(de, i));
    return { de, ate: days[6]!, days };
  }
  const { year, month } = parseDateKey(anchor);
  const first = `${year}-${String(month).padStart(2, "0")}-01`;
  const de = weekStart(first);
  const days = Array.from({ length: 42 }, (_, i) => addDays(de, i));
  return { de, ate: days[41]!, days };
}

// Instante do encaixe: dia local + minutos desde 00:00 (múltiplo de 15).
function slotIso(day: string, minutes: number): string {
  const { year, month, day: d } = parseDateKey(day);
  return toIsoWithOffset(fromLocal(year, month, d, Math.floor(minutes / 60), minutes % 60));
}

export default function Calendario() {
  usePageMeta({ title: "Calendário" });
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const perfis = usePerfisAtivos();
  const view: View = params.get("visao") === "mes" ? "mes" : "semana";
  const today = localDateKey(new Date());
  const anchor = params.get("data") ?? today;
  const perfilId = params.get("perfil") ?? "";
  const plataforma = params.get("plataforma") ?? "";
  const contaId = params.get("conta") ?? "";
  const perfilSel = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: Boolean(perfilId) });
  const set = (patch: Record<string, string>) =>
    setParams(
      (cur) => {
        const next = new URLSearchParams(cur);
        for (const [k, v] of Object.entries(patch)) {
          if (v) next.set(k, v);
          else next.delete(k);
        }
        return next;
      },
      { replace: true },
    );

  const { de, ate, days } = useMemo(() => range(view, anchor), [view, anchor]);
  const filters = useMemo(
    () => ({
      de,
      ate,
      ...(perfilId ? { perfilId } : {}),
      ...(plataforma ? { plataforma: plataforma as Platform } : {}),
      ...(contaId ? { contaId } : {}),
    }),
    [de, ate, perfilId, plataforma, contaId],
  );
  const cal = useQuery({ queryKey: calendarioKey(filters), queryFn: () => api.calendario(filters) });

  // Remarcações otimistas (id → novo plannedAt) até a volta do servidor.
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const items = useMemo(
    () => (cal.data?.items ?? []).filter((p) => !p.archived).map((p) => (overrides[p.id] ? { ...p, plannedAt: overrides[p.id]! } : p)),
    [cal.data, overrides],
  );
  const semData = cal.data?.semData ?? [];
  // Legenda: os perfis que aparecem na tela, com a cor de cada um e o texto em contraste.
  const legenda = useMemo(() => {
    const map = new Map<string, { id: string; name: string; cor: string }>();
    for (const p of items) map.set(p.perfil.id, { id: p.perfil.id, name: p.perfil.name, cor: perfilColor(p.perfil.id, p.perfil.cor) });
    for (const s of semData) {
      if (!map.has(s.perfilId)) {
        const name = perfis.data?.find((x) => x.id === s.perfilId)?.name ?? "Perfil";
        map.set(s.perfilId, { id: s.perfilId, name, cor: perfilColor(s.perfilId, s.perfilCor) });
      }
    }
    return [...map.values()].sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
  }, [items, semData, perfis.data]);
  const byDay = useMemo(() => {
    const map = new Map<string, CalendarioItem[]>();
    for (const p of items) {
      if (!p.plannedAt) continue;
      const k = localDateKey(p.plannedAt);
      map.set(k, [...(map.get(k) ?? []), p]);
    }
    for (const list of map.values()) list.sort((a, b) => a.plannedAt!.localeCompare(b.plannedAt!));
    return map;
  }, [items]);

  const [remarcar, setRemarcar] = useState<CalendarioItem | null>(null);
  const [agendar, setAgendar] = useState<{ item: CalendarioSemData; plannedAt: string | null } | null>(null);
  const drag = useRef<DragPayload | null>(null);
  const [dropHint, setDropHint] = useState<string | null>(null);

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["calendario"] });
  }

  // Remarcar = `lote/reagendar` com um item (R11). Perto de outro post da conta, a API devolve a
  // falha `intervalo_conflito`: o aviso oferece "Manter mesmo assim" (Q3).
  async function mover(p: CalendarioItem, plannedAt: string, opts: { undo?: boolean; ignorarIntervalo?: boolean } = {}) {
    if (p.estado !== "agendado") return toast.info(`${estadoEfetivoLabel[p.estadoEfetivo]}: não dá para remarcar.`);
    if (new Date(plannedAt).getTime() < Date.now() - 60_000) return toast.error("Escolha um horário no futuro.");
    const before = p.plannedAt;
    setOverrides((o) => ({ ...o, [p.id]: plannedAt }));
    try {
      const r = await api.agendamentos.loteReagendar({
        itens: [{ destinoId: p.id, version: p.version, plannedAt }],
        ...(opts.ignorarIntervalo ? { ignorarIntervalo: true } : {}),
      });
      const falha = r.falhas[0];
      const novo = r.ok[0];
      if (falha) {
        if (falha.code === "intervalo_conflito") {
          toast.warning(falha.message, {
            duration: 10_000,
            action: { label: "Manter mesmo assim", onClick: () => void mover(p, plannedAt, { ...opts, ignorarIntervalo: true }) },
          });
        } else toast.error(falha.code === "version_conflict" ? "Este agendamento mudou em outra tela; recarreguei o calendário." : falha.message);
      } else if (!opts.undo && before && novo) {
        toast.success(`Remarcado para ${formatDateTime(plannedAt)}.`, {
          action: { label: "Desfazer", onClick: () => void mover({ ...p, version: novo.version, plannedAt }, before, { undo: true, ignorarIntervalo: true }) },
        });
      } else toast.success(`Agendado para ${formatDateTime(plannedAt)}.`);
    } catch (err) {
      toast.error(err instanceof ApiError && err.code === "version_conflict" ? "Este agendamento mudou em outra tela; recarreguei o calendário." : errorText(err));
    } finally {
      await invalidate();
      setOverrides((o) => {
        const { [p.id]: _, ...rest } = o;
        return rest;
      });
    }
  }

  function onDragStart(e: DragEvent, payload: DragPayload) {
    drag.current = payload;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", payload.kind === "postagem" ? payload.id : payload.key);
  }

  function drop(plannedAt: string) {
    const payload = drag.current;
    drag.current = null;
    setDropHint(null);
    if (!payload) return;
    if (payload.kind === "postagem") {
      const p = items.find((x) => x.id === payload.id);
      if (p && p.plannedAt !== plannedAt) void mover(p, plannedAt);
    } else {
      const item = semData.find((s) => semDataKey(s) === payload.key);
      if (item) setAgendar({ item, plannedAt });
    }
  }

  const label =
    view === "semana"
      ? `${dayFormat.format(utcDate(de))} a ${dayFormat.format(utcDate(ate))}`
      : monthFormat.format(utcDate(`${anchor.slice(0, 7)}-01`));
  const step = (dir: 1 | -1) => {
    if (view === "semana") return set({ data: addDays(anchor, 7 * dir) });
    const { year, month } = parseDateKey(anchor);
    const d = new Date(Date.UTC(year, month - 1 + dir, 1));
    set({ data: `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-01` });
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeading title="Calendário" description="Conteúdos agendados por dia, perfil, conta e plataforma. Arraste para remarcar (no celular, toque)." />

      <div className="flex flex-wrap items-end gap-3">
        <Field label="Perfil" className="w-full sm:w-56">
          {({ id }) => (
            <NativeSelect id={id} value={perfilId} onChange={(e) => set({ perfil: e.target.value, conta: "" })}>
              <option value="">Todos os perfis</option>
              {perfis.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Conta" className="w-full sm:w-52">
          {({ id }) => (
            <NativeSelect id={id} value={contaId} disabled={!perfilId} onChange={(e) => set({ conta: e.target.value })}>
              <option value="">{perfilId ? "Todas as contas" : "Escolha um perfil"}</option>
              {perfilSel.data?.contas
                .filter((c) => !c.archived)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {contaPlatformText(c)} @{c.handle}
                  </option>
                ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Plataforma" className="w-full sm:w-44">
          {({ id }) => (
            <NativeSelect id={id} value={plataforma} onChange={(e) => set({ plataforma: e.target.value })}>
              <option value="">Todas</option>
              {(Object.keys(platformLabel) as Platform[]).map((p) => (
                <option key={p} value={p}>
                  {platformLabel[p]}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <div className="flex items-center gap-1 rounded-lg bg-muted p-1" role="group" aria-label="Visão">
          {(["semana", "mes"] as const).map((v) => (
            <Button key={v} type="button" size="sm" variant={view === v ? "default" : "ghost"} aria-pressed={view === v} onClick={() => set({ visao: v === "semana" ? "" : v })}>
              {v === "semana" ? "Semana" : "Mês"}
            </Button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <Button type="button" variant="outline" size="icon" aria-label={view === "semana" ? "Semana anterior" : "Mês anterior"} onClick={() => step(-1)}>
            <ChevronLeft aria-hidden="true" />
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => set({ data: "" })}>
            Hoje
          </Button>
          <Button type="button" variant="outline" size="icon" aria-label={view === "semana" ? "Próxima semana" : "Próximo mês"} onClick={() => step(1)}>
            <ChevronRight aria-hidden="true" />
          </Button>
          <p className="ml-2 min-w-40 text-sm font-semibold capitalize" aria-live="polite">
            {label}
          </p>
        </div>
      </div>

      {legenda.length > 0 && (
        <ul aria-label="Cores dos perfis" className="flex flex-wrap gap-2">
          {legenda.map((l) => (
            <li key={l.id} className="rounded-full px-2.5 py-0.5 text-xs font-semibold" style={{ backgroundColor: l.cor, color: textOn(l.cor) }}>
              {l.name}
            </li>
          ))}
        </ul>
      )}

      {cal.isError && <ApiErrorAlert error={cal.error} />}

      <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <aside aria-label="Sem data" className="h-fit rounded-xl bg-card p-3 shadow-card">
          <h2 className="mb-1 text-sm font-bold">Sem data</h2>
          <p className="mb-3 text-xs text-muted-foreground">Aprovados primeiro. Arraste para um horário ou toque para agendar.</p>
          {cal.isPending && <Loader2 className="size-4 animate-spin text-muted-foreground" aria-label="Carregando" />}
          {cal.isSuccess && semData.length === 0 && <p className="text-xs text-muted-foreground">Nenhum conteúdo pronto sem data.</p>}
          <ul className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
            {semData.map((s) => (
              <li key={semDataKey(s)} className="shrink-0 lg:shrink">
                <button
                  type="button"
                  draggable
                  onDragStart={(e) => onDragStart(e, { kind: "semData", key: semDataKey(s) })}
                  onDragEnd={() => setDropHint(null)}
                  onClick={() => setAgendar({ item: s, plannedAt: null })}
                  className="flex w-52 cursor-grab items-center gap-2 rounded-lg border bg-background p-1.5 text-left text-xs hover:border-primary active:cursor-grabbing lg:w-full"
                  style={{ borderLeft: `4px solid ${perfilColor(s.perfilId, s.perfilCor)}` }}
                  aria-label={`Agendar: ${s.titulo || "conteúdo sem título"}${s.aprovado ? " (aprovado)" : ""}`}
                >
                  {s.posterUrl ? (
                    <img src={s.posterUrl} alt="" className="h-12 w-7 shrink-0 rounded bg-muted object-cover" />
                  ) : (
                    <Film className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  )}
                  <span className="min-w-0">
                    <span className="line-clamp-2 font-medium">{s.titulo || "Sem título"}</span>
                    <span className="block truncate text-muted-foreground">{perfis.data?.find((p) => p.id === s.perfilId)?.name}</span>
                    {s.aprovado && <Badge className="mt-0.5 bg-primary/15 text-[0.6rem] text-primary">Aprovado</Badge>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {view === "semana" ? (
          <WeekGrid
            days={days}
            today={today}
            byDay={byDay}
            dropHint={dropHint}
            setDropHint={setDropHint}
            onDrop={drop}
            onDragStart={onDragStart}
            onOpen={setRemarcar}
          />
        ) : (
          <MonthGrid
            days={days}
            month={anchor.slice(0, 7)}
            today={today}
            byDay={byDay}
            dropHint={dropHint}
            setDropHint={setDropHint}
            onDrop={(day) => {
              const payload = drag.current;
              const p = payload?.kind === "postagem" ? items.find((x) => x.id === payload.id) : null;
              const t = p?.plannedAt ? localParts(p.plannedAt) : { hour: 19, minute: 0 };
              drop(slotIso(day, t.hour * 60 + t.minute));
            }}
            onDragStart={onDragStart}
            onOpen={setRemarcar}
          />
        )}
      </div>

      <RemarcarDialog item={remarcar} onClose={() => setRemarcar(null)} onSave={async (p, iso) => {
          await mover(p, iso);
        }} />
      {agendar && <AgendarDoCalendario state={agendar} onClose={() => setAgendar(null)} onDone={invalidate} />}
    </div>
  );
}

interface GridProps {
  days: string[];
  today: string;
  byDay: Map<string, CalendarioItem[]>;
  dropHint: string | null;
  setDropHint: (k: string | null) => void;
  onDragStart: (e: DragEvent, payload: DragPayload) => void;
  onOpen: (p: CalendarioItem) => void;
}

// Estados que aparecem escritos no chip (os de atenção e os do envio automático, spec 015).
const DESTAQUE: CalendarioItem["estadoEfetivo"][] = ["a_postar", "atrasado", "atencao", "enviando", "pausado", "vencido", "aguardando_vaga", "falhou", "rascunho_criado"];

function Chip({ p, onDragStart, onOpen, compact }: { p: CalendarioItem; onDragStart: GridProps["onDragStart"]; onOpen: GridProps["onOpen"]; compact?: boolean }) {
  const dono = useEhDono();
  // spec 015: envio automático só o dono remarca (a API recusa o membro)
  const movel = p.estado === "agendado" && (dono || !ehAutomatico(p.modo));
  const destaque = DESTAQUE.includes(p.estadoEfetivo);
  return (
    <button
      type="button"
      draggable={movel}
      onDragStart={(e) => onDragStart(e, { kind: "postagem", id: p.id })}
      onClick={() => onOpen(p)}
      className={cn(
        "flex w-full min-w-0 flex-wrap items-center gap-x-1 rounded-md bg-card px-1.5 py-1 text-left text-[0.7rem] leading-tight shadow-sm ring-1 ring-border hover:ring-primary",
        movel && "cursor-grab active:cursor-grabbing",
        !movel && "opacity-60",
        p.estadoEfetivo === "a_postar" && "ring-2 ring-primary",
        (p.estadoEfetivo === "atrasado" || p.estadoEfetivo === "atencao" || p.estadoEfetivo === "falhou" || p.estadoEfetivo === "vencido") && "ring-2 ring-destructive",
        (p.estadoEfetivo === "enviando" || p.estadoEfetivo === "aguardando_vaga" || p.estadoEfetivo === "pausado") && "ring-2 ring-info",
      )}
      style={{ borderLeft: `4px solid ${perfilColor(p.perfil.id, p.perfil.cor)}` }}
      aria-label={`${formatTime(p.plannedAt!)} ${p.titulo || p.conteudo.titulo || "Sem título"} (${p.perfil.name}, ${platformLabel[p.conta.platform]}, ${estadoEfetivoLabel[p.estadoEfetivo]}, ${modoLabel[p.modo]})`}
    >
      <PlatformIcon platform={p.conta.platform} className="size-3" />
      {p.modo === "lembrete" && <Bell className="size-3 text-muted-foreground" aria-hidden="true" />}
      <span className="font-semibold tabular-nums">{formatTime(p.plannedAt!)}</span>
      {destaque && (
        <span className={p.estadoEfetivo === "rascunho_criado" || p.estadoEfetivo === "enviando" ? "font-semibold text-info" : "font-semibold text-destructive"}>
          {estadoEfetivoLabel[p.estadoEfetivo]}
        </span>
      )}
      {!compact && <span className="min-w-0 basis-full truncate">{p.titulo || p.conteudo.titulo || "Sem título"}</span>}
    </button>
  );
}

function WeekGrid({ days, today, byDay, dropHint, setDropHint, onDrop, onDragStart, onOpen }: GridProps & { onDrop: (iso: string) => void }) {
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = 7 * HOUR_PX;
  }, []);

  function slotFrom(e: DragEvent<HTMLDivElement>): number {
    const rect = e.currentTarget.getBoundingClientRect();
    const minutes = ((e.clientY - rect.top) / HOUR_PX) * 60;
    return Math.max(0, Math.min(24 * 60 - SLOT_MIN, Math.floor(minutes / SLOT_MIN) * SLOT_MIN));
  }

  return (
    <div className="min-w-0 overflow-x-auto rounded-xl bg-card shadow-card">
      <div className="min-w-[44rem]">
        <div className="grid grid-cols-[3rem_repeat(7,minmax(0,1fr))] border-b">
          <span />
          {days.map((d, i) => (
            <div key={d} className={cn("px-1 py-2 text-center text-xs font-semibold", d === today && "text-primary")}>
              {WEEKDAYS[i]} {dayFormat.format(utcDate(d))}
            </div>
          ))}
        </div>
        <div ref={scroller} className="max-h-[36rem] overflow-y-auto">
          <div className="grid grid-cols-[3rem_repeat(7,minmax(0,1fr))]" style={{ height: 24 * HOUR_PX }}>
            <div className="relative">
              {Array.from({ length: 24 }, (_, h) => (
                <span key={h} className="absolute right-1 -translate-y-1/2 text-[0.65rem] text-muted-foreground tabular-nums" style={{ top: h * HOUR_PX }}>
                  {h > 0 ? `${String(h).padStart(2, "0")}:00` : ""}
                </span>
              ))}
            </div>
            {days.map((d) => (
              <div
                key={d}
                role="group"
                aria-label={`Dia ${dayFormat.format(utcDate(d))}`}
                data-day={d}
                className={cn(
                  "relative border-l bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_47px,var(--color-border)_47px,var(--color-border)_48px)]",
                  d === today && "bg-primary/5",
                )}
                onDragOver={(e) => {
                  e.preventDefault();
                  const m = slotFrom(e);
                  setDropHint(`${d}:${m}`);
                }}
                onDragLeave={() => setDropHint(null)}
                onDrop={(e) => {
                  e.preventDefault();
                  onDrop(slotIso(d, slotFrom(e)));
                }}
              >
                {dropHint?.startsWith(`${d}:`) && (
                  <div
                    className="pointer-events-none absolute inset-x-0.5 rounded bg-primary/20 text-[0.65rem] font-semibold text-primary"
                    style={{ top: (Number(dropHint.split(":")[1]) / 60) * HOUR_PX, height: HOUR_PX / 2 }}
                  >
                    {`${String(Math.floor(Number(dropHint.split(":")[1]) / 60)).padStart(2, "0")}:${String(Number(dropHint.split(":")[1]) % 60).padStart(2, "0")}`}
                  </div>
                )}
                {(byDay.get(d) ?? []).map((p, i, list) => {
                  const t = localParts(p.plannedAt!);
                  const sameSlot = list.filter((x, j) => j < i && Math.abs(localParts(x.plannedAt!).hour * 60 + localParts(x.plannedAt!).minute - (t.hour * 60 + t.minute)) < 30).length;
                  return (
                    <div key={p.id} className="absolute right-0.5" style={{ top: ((t.hour * 60 + t.minute) / 60) * HOUR_PX, left: 2 + sameSlot * 10 }}>
                      <Chip p={p} onDragStart={onDragStart} onOpen={onOpen} />
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function MonthGrid({ days, month, today, byDay, dropHint, setDropHint, onDrop, onDragStart, onOpen }: GridProps & { month: string; onDrop: (day: string) => void }) {
  return (
    <div className="min-w-0 overflow-x-auto rounded-xl bg-card shadow-card">
      <div className="grid min-w-[40rem] grid-cols-7">
        {WEEKDAYS.map((w) => (
          <div key={w} className="border-b px-2 py-2 text-center text-xs font-semibold">
            {w}
          </div>
        ))}
        {days.map((d) => {
          const list = byDay.get(d) ?? [];
          return (
            <div
              key={d}
              role="group"
              aria-label={`Dia ${dayFormat.format(utcDate(d))}`}
              className={cn(
                "min-h-28 space-y-1 border-b border-l p-1",
                !d.startsWith(month) && "bg-muted/40 text-muted-foreground",
                dropHint === d && "bg-primary/10",
              )}
              onDragOver={(e) => {
                e.preventDefault();
                setDropHint(d);
              }}
              onDragLeave={() => setDropHint(null)}
              onDrop={(e) => {
                e.preventDefault();
                onDrop(d);
              }}
            >
              <p className={cn("text-xs font-semibold", d === today && "inline-flex size-5 items-center justify-center rounded-full bg-primary text-primary-foreground")}>
                {Number(d.slice(8))}
              </p>
              {list.slice(0, 4).map((p) => (
                <Chip key={p.id} p={p} onDragStart={onDragStart} onOpen={onOpen} />
              ))}
              {list.length > 4 && <p className="text-[0.65rem] text-muted-foreground">+{list.length - 4}</p>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RemarcarDialog({ item, onClose, onSave }: { item: CalendarioItem | null; onClose: () => void; onSave: (p: CalendarioItem, iso: string) => Promise<void> }) {
  const [value, setValue] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setValue(toLocalInput(item?.plannedAt));
    setErr(null);
  }, [item]);
  if (!item) return null;
  const postado = item.estado !== "agendado";
  const t = item.ultimaTentativa;

  async function save() {
    const iso = fromLocalInput(value);
    if (!iso) return setErr("Escolha a data e a hora");
    if (new Date(iso).getTime() < Date.now() - 60_000) return setErr("Escolha um horário no futuro");
    setBusy(true);
    await onSave(item!, iso);
    setBusy(false);
    onClose();
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{postado ? "Agendamento" : "Remarcar"}</DialogTitle>
          <DialogDescription>
            {item.titulo || item.conteudo.titulo || "Sem título"} · {item.perfil.name} · {contaPlatformText(item.conta)} @{item.conta.handle} · {modoLabel[item.modo]}
          </DialogDescription>
        </DialogHeader>
        <div className="flex justify-center">
          <EstadoBadge estado={item.estadoEfetivo} motivo={item.motivoAtencao} />
        </div>
        {/* spec 015: onde o envio automático está e o motivo da falha */}
        {item.estado === "enviando" && t && (
          <p className="text-center text-sm text-muted-foreground">
            {faseLabel[t.fase]}
            {t.totalPartes > 0 ? `: parte ${t.partesEnviadas} de ${t.totalPartes}` : ""}
          </p>
        )}
        {item.estado === "falhou" && (item.falhaMotivo ?? t?.motivo) && <p className="text-center text-sm text-destructive">{item.falhaMotivo ?? t?.motivo}</p>}
        {item.conteudo.posterUrl && <img src={item.conteudo.posterUrl} alt="" className="mx-auto h-40 rounded-md bg-muted object-cover" />}
        {!postado && (
          <Field label="Data e hora (horário de Brasília)" error={err ?? undefined}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} type="datetime-local" step={900} value={value} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setValue(e.target.value)} />
            )}
          </Field>
        )}
        <DialogFooter className="flex-wrap gap-2">
          <Button variant="ghost" asChild>
            <Link to={`/app/conteudos/${item.conteudo.id}?conta=${item.conta.id}`}>
              <ExternalLink aria-hidden="true" />
              Abrir conteúdo
            </Link>
          </Button>
          {!postado && (
            <Button type="button" disabled={busy} aria-busy={busy} onClick={() => void save()}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CalendarClock aria-hidden="true" />}
              Remarcar
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Soltar (ou tocar) um item "sem data": o AgendarDialog comum, com os destinos do conteúdo (para o
// dono ver "Aprovar e agendar" e o membro, diante de um não aprovado, "Pedir aprovação").
function AgendarDoCalendario({
  state,
  onClose,
  onDone,
}: {
  state: { item: CalendarioSemData; plannedAt: string | null };
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const conteudo = useConteudo(state.item.conteudoId);
  const c = conteudo.data?.conteudo;
  const erro = conteudo.isError ? conteudo.error : null;
  useEffect(() => {
    if (!erro) return;
    toast.error(errorText(erro));
    onClose();
  }, [erro]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!c) return null;
  return (
    <AgendarDialog
      open
      onOpenChange={(open) => !open && onClose()}
      conteudo={{ id: c.id, perfilId: c.perfil.id, titulo: c.titulo, situacao: c.situacao, proposta: propostaDe(c) }}
      destinos={c.destinos}
      contaId={state.item.contaId}
      plannedAt={state.plannedAt}
      onDone={onDone}
    />
  );
}
