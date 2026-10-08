// Fuso da agência (spec 006, R10): a API recebe e devolve ISO com offset, e o SPA mostra e lê datas
// em America/Sao_Paulo, qualquer que seja o fuso do aparelho. O offset sai do Intl (sem offset fixo:
// se o horário de verão voltar, a conta continua certa).
export const APP_TZ = "America/Sao_Paulo";

const partsFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: APP_TZ,
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  weekday: "short",
});

export interface LocalParts {
  year: number;
  month: number; // 1..12
  day: number;
  hour: number;
  minute: number;
  second: number;
  weekday: number; // 0 = domingo
}

const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function localParts(date: Date | string): LocalParts {
  const d = typeof date === "string" ? new Date(date) : date;
  const map: Record<string, string> = {};
  for (const p of partsFormat.formatToParts(d)) map[p.type] = p.value;
  return {
    year: Number(map.year),
    month: Number(map.month),
    day: Number(map.day),
    hour: Number(map.hour),
    minute: Number(map.minute),
    second: Number(map.second),
    weekday: weekdays.indexOf(map.weekday ?? "Sun"),
  };
}

// Minutos a somar ao horário local para chegar ao UTC naquele instante (São Paulo hoje: +180).
function offsetMinutes(utcMs: number): number {
  const p = localParts(new Date(utcMs));
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  return Math.round((utcMs - asUtc) / 60_000);
}

// Data e hora locais (no fuso da agência) → instante. Duas passadas acertam a virada de offset.
export function fromLocal(year: number, month: number, day: number, hour = 0, minute = 0): Date {
  const guess = Date.UTC(year, month - 1, day, hour, minute);
  let ms = guess + offsetMinutes(guess) * 60_000;
  ms = guess + offsetMinutes(ms) * 60_000;
  return new Date(ms);
}

const pad = (n: number) => String(n).padStart(2, "0");

// "2026-09-30" (dia local).
export function localDateKey(date: Date | string): string {
  const p = localParts(date);
  return `${p.year}-${pad(p.month)}-${pad(p.day)}`;
}

// "2026-09-30" → { year, month, day }.
export function parseDateKey(key: string): { year: number; month: number; day: number } {
  const [y, m, d] = key.split("-").map(Number);
  return { year: y ?? 1970, month: m ?? 1, day: d ?? 1 };
}

// Soma dias a uma chave de dia local (sem passar por horário, então sem problema de offset).
export function addDays(key: string, days: number): string {
  const { year, month, day } = parseDateKey(key);
  const d = new Date(Date.UTC(year, month - 1, day + days));
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

// Dia da semana (0 = domingo) de uma chave de dia.
export function weekdayOf(key: string): number {
  const { year, month, day } = parseDateKey(key);
  return new Date(Date.UTC(year, month - 1, day)).getUTCDay();
}

// Valor para <input type="datetime-local"> ("2026-09-30T19:00") no fuso da agência.
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const p = localParts(iso);
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`;
}

// "2026-09-30T19:00" (horário da agência) → ISO com offset ("2026-09-30T19:00:00-03:00").
export function fromLocalInput(value: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (!m) return null;
  const [, y, mo, d, h, mi] = m.map(Number) as [number, number, number, number, number, number];
  return toIsoWithOffset(fromLocal(y, mo, d, h, mi));
}

// Instante → ISO com o offset da agência.
export function toIsoWithOffset(date: Date): string {
  const p = localParts(date);
  const off = -offsetMinutes(date.getTime());
  const sign = off >= 0 ? "+" : "-";
  const abs = Math.abs(off);
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}:${pad(p.second)}${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

const dateTimeFormat = new Intl.DateTimeFormat("pt-BR", { timeZone: APP_TZ, dateStyle: "short", timeStyle: "short" });
const timeFormat = new Intl.DateTimeFormat("pt-BR", { timeZone: APP_TZ, hour: "2-digit", minute: "2-digit" });
const longDateFormat = new Intl.DateTimeFormat("pt-BR", { timeZone: APP_TZ, weekday: "long", day: "numeric", month: "long" });

export const formatDateTime = (iso: string) => dateTimeFormat.format(new Date(iso));
export const formatTime = (iso: string) => timeFormat.format(new Date(iso));
export const formatLongDate = (iso: string) => longDateFormat.format(new Date(iso));

// Só a data (spec 024, FR-036): dd/mm/aaaa no fuso da agência.
const dateFormat = new Intl.DateTimeFormat("pt-BR", { timeZone: APP_TZ, day: "2-digit", month: "2-digit", year: "numeric" });
const dayMonthFormat = new Intl.DateTimeFormat("pt-BR", { timeZone: APP_TZ, day: "2-digit", month: "2-digit" });
const monthYearFormat = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC", month: "long", year: "numeric" });
export const formatDate = (iso: string | number | Date) => dateFormat.format(new Date(iso));
export const formatDayMonth = (iso: string | number | Date) => dayMonthFormat.format(new Date(iso));
// Chaves de dia (YYYY-MM-DD, sem fuso): "07/10/2026", "07/10" e "outubro de 2026".
export const formatDateKey = (key: string) => key.split("-").reverse().join("/");
export const formatDayMonthKey = (key: string) => key.slice(5).split("-").reverse().join("/");
export const formatMonthYearKey = (key: string) => monthYearFormat.format(new Date(`${key.slice(0, 7)}-01T12:00:00Z`));

// "há 5 min", "há 2 h", "há 3 dias" (sino e listas).
export function formatAgo(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "agora";
  const min = Math.round(s / 60);
  if (min < 60) return `há ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `há ${h} h`;
  const d = Math.round(h / 24);
  return d === 1 ? "há 1 dia" : `há ${d} dias`;
}
