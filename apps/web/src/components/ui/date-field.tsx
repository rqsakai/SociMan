/*
 * Campos de data digitáveis (spec 024, R12): o `input type=date` do navegador mostra o formato da
 * máquina (mm/dd/yyyy em inglês); aqui é sempre dd/mm/aaaa, e o valor para fora é ISO.
 *
 * <Field label="De">{({ id }) => <DateField id={id} value={de} onChange={(iso) => set({ de: iso || null })} />}</Field>
 * <DateTimeField aria-label="Agendar para" value={quando} onChange={setQuando} min="2026-10-07T00:00" />
 *
 * - DateField: texto `dd/mm/aaaa` ↔ `YYYY-MM-DD`; DateTimeField: `dd/mm/aaaa hh:mm` ↔ `YYYY-MM-DDTHH:mm`;
 * - só os dígitos contam (a máscara põe "/", " " e ":"), então colar ou digitar com separador dá no mesmo;
 * - `onChange` recebe o ISO quando o texto forma uma data real (31/02 não; dentro de `min`/`max`) e
 *   "" enquanto incompleto ou inválido. O texto digitado não some quando o `value` volta "";
 * - texto completo e inválido → `aria-invalid` e `setCustomValidity` (o form não envia);
 * - "Abrir calendário" chama `showPicker()` num `input type=date` (ou `datetime-local`) escondido; sem
 *   `showPicker` no navegador, o botão não aparece e o campo fica só digitável;
 * - o `id` (do `Field`), `aria-label`, `aria-describedby`, `name`, `required` e `disabled` vão para o
 *   campo de texto, então o `getByLabel` dos e2e continua achando o campo.
 */
import { CalendarDays } from "lucide-react";
import { useEffect, useRef, useState, type ComponentProps } from "react";
import { cn } from "@/lib/utils";
import { Input } from "./input";

type Modo = "data" | "dataHora";

type Props = Omit<ComponentProps<"input">, "ref" | "type" | "value" | "defaultValue" | "onChange" | "min" | "max"> & {
  value: string;
  onChange: (iso: string) => void;
  min?: string;
  max?: string;
};

const MASCARA: Record<Modo, { digitos: number; placeholder: string; tipoNativo: "date" | "datetime-local" }> = {
  data: { digitos: 8, placeholder: "dd/mm/aaaa", tipoNativo: "date" },
  dataHora: { digitos: 12, placeholder: "dd/mm/aaaa hh:mm", tipoNativo: "datetime-local" },
};

// separador antes do dígito de índice i (ddmmaaaahhmm)
const SEPARADOR: Record<number, string> = { 2: "/", 4: "/", 8: " ", 10: ":" };

function mascarar(texto: string, modo: Modo): string {
  const digitos = texto.replace(/\D/g, "").slice(0, MASCARA[modo].digitos);
  let out = "";
  for (let i = 0; i < digitos.length; i++) out += (SEPARADOR[i] ?? "") + digitos[i];
  return out;
}

// texto mascarado → ISO, ou null se incompleto; "invalida" se completo e não for data real
function paraIso(texto: string, modo: Modo): string | null | "invalida" {
  const d = texto.replace(/\D/g, "");
  if (d.length < MASCARA[modo].digitos) return null;
  const dia = Number(d.slice(0, 2));
  const mes = Number(d.slice(2, 4));
  const ano = Number(d.slice(4, 8));
  const data = new Date(Date.UTC(ano, mes - 1, dia));
  const real = ano >= 1000 && data.getUTCFullYear() === ano && data.getUTCMonth() === mes - 1 && data.getUTCDate() === dia;
  if (!real) return "invalida";
  const iso = `${d.slice(4, 8)}-${d.slice(2, 4)}-${d.slice(0, 2)}`;
  if (modo === "data") return iso;
  const hora = Number(d.slice(8, 10));
  const minuto = Number(d.slice(10, 12));
  if (hora > 23 || minuto > 59) return "invalida";
  return `${iso}T${d.slice(8, 10)}:${d.slice(10, 12)}`;
}

function deIso(iso: string, modo: Modo): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(iso);
  if (!m) return "";
  const [, ano, mes, dia, hora, minuto] = m;
  return modo === "dataHora" && hora ? `${dia}/${mes}/${ano} ${hora}:${minuto}` : `${dia}/${mes}/${ano}`;
}

const temShowPicker = typeof HTMLInputElement !== "undefined" && "showPicker" in HTMLInputElement.prototype;

function CampoData({ modo, value, onChange, min, max, className, disabled, ...rest }: Props & { modo: Modo }) {
  const { placeholder, tipoNativo } = MASCARA[modo];
  const [texto, setTexto] = useState(() => deIso(value, modo));
  const emitido = useRef(value);
  const textoRef = useRef<HTMLInputElement>(null);
  const nativoRef = useRef<HTMLInputElement>(null);

  // valor novo de fora (voltar, limpar): substitui o texto; o "" que nós mesmos mandamos, não
  useEffect(() => {
    if (value === emitido.current) return;
    emitido.current = value;
    setTexto(deIso(value, modo));
  }, [value, modo]);

  const iso = paraIso(texto, modo);
  const foraDoLimite = typeof iso === "string" && iso !== "invalida" && ((min && iso < min) || (max && iso > max));
  const invalida = iso === "invalida" || Boolean(foraDoLimite);

  useEffect(() => {
    textoRef.current?.setCustomValidity(
      iso === "invalida" ? "Data inválida." : foraDoLimite ? "Data fora do intervalo permitido." : "",
    );
  }, [iso, foraDoLimite]);

  function emitir(proximo: string) {
    if (proximo === emitido.current) return;
    emitido.current = proximo;
    onChange(proximo);
  }

  function aoDigitar(bruto: string) {
    const mascarado = mascarar(bruto, modo);
    setTexto(mascarado);
    const r = paraIso(mascarado, modo);
    const ok = typeof r === "string" && r !== "invalida" && !(min && r < min) && !(max && r > max);
    emitir(ok ? r : "");
  }

  function abrirCalendario() {
    const nativo = nativoRef.current;
    if (!nativo) return;
    nativo.value = typeof iso === "string" && iso !== "invalida" ? iso : "";
    try {
      nativo.showPicker();
    } catch {
      textoRef.current?.focus(); // sem permissão (ex.: fora de um gesto): fica a digitação
    }
  }

  return (
    <div className={cn("relative w-full", className)}>
      <Input
        {...rest}
        ref={textoRef}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        placeholder={placeholder}
        maxLength={placeholder.length}
        value={texto}
        disabled={disabled}
        aria-invalid={invalida || rest["aria-invalid"] || undefined}
        onChange={(e) => aoDigitar(e.target.value)}
        className={cn(temShowPicker && "pr-10", "tabular-nums")}
      />
      {temShowPicker && (
        <>
          <button
            type="button"
            onClick={abrirCalendario}
            disabled={disabled}
            aria-label="Abrir calendário"
            className="absolute top-1/2 right-1 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-hidden disabled:pointer-events-none disabled:opacity-50"
          >
            <CalendarDays className="size-4" aria-hidden="true" />
          </button>
          {/* só para o seletor do navegador: fora da ordem do Tab e do leitor de tela */}
          <input
            ref={nativoRef}
            type={tipoNativo}
            tabIndex={-1}
            aria-hidden="true"
            min={min}
            max={max}
            className="pointer-events-none absolute right-0 bottom-0 size-px opacity-0"
            onChange={(e) => {
              const v = e.target.value.slice(0, modo === "data" ? 10 : 16); // sem segundos
              setTexto(deIso(v, modo));
              emitir(v);
            }}
          />
        </>
      )}
    </div>
  );
}

export function DateField(props: Props) {
  return <CampoData modo="data" {...props} />;
}

export function DateTimeField(props: Props) {
  return <CampoData modo="dataHora" {...props} />;
}
