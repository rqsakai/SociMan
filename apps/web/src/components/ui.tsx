import { CircleAlert, CircleCheck, Info, Loader2, type LucideIcon } from "lucide-react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { useId } from "react";

// Componentes base minimalistas do starter. Estilo vem dos tokens de tema
// (src/index.css) via classes Tailwind — NUNCA style inline (CSP estrita usa
// style-src 'self'). Apps herdeiros substituem à vontade.

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost";
  loading?: boolean;
};

export function Button({ variant = "primary", loading, disabled, children, className = "", ...rest }: ButtonProps) {
  const base =
    "inline-flex w-full items-center justify-center gap-2 rounded-field px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-60";
  const styles =
    variant === "primary"
      ? "bg-primary text-primary-foreground hover:bg-primary/90"
      : "bg-transparent text-text hover:bg-border/40";
  return (
    <button className={`${base} ${styles} ${className}`} disabled={disabled || loading} aria-busy={loading} {...rest}>
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  icon?: LucideIcon;
};

export function Input({ icon: Icon, className = "", ...props }: InputProps) {
  const base =
    "w-full rounded-field border border-border bg-surface py-2 pr-3 text-sm outline-none placeholder:text-muted focus:border-primary focus:ring-2 focus:ring-primary/25 aria-invalid:border-danger";
  if (!Icon) {
    return <input {...props} className={`${base} pl-3 ${className}`} />;
  }
  return (
    <div className="relative">
      <Icon
        className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
        aria-hidden="true"
      />
      <input {...props} className={`${base} pl-9 ${className}`} />
    </div>
  );
}

export function Select({ className = "", ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`w-full rounded-field border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/25 aria-invalid:border-danger ${className}`}
    />
  );
}

export function Textarea({ className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`w-full rounded-field border border-border bg-surface px-3 py-2 text-sm outline-none placeholder:text-muted focus:border-primary focus:ring-2 focus:ring-primary/25 aria-invalid:border-danger ${className}`}
    />
  );
}

interface FieldProps {
  label: string;
  error?: string;
  children: (ids: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
}

// Campo acessível: label ligada por htmlFor, erro anunciado via role=alert e
// associado ao input com aria-describedby.
export function Field({ label, error, children }: FieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children({ id, describedBy: error ? errorId : undefined, invalid: Boolean(error) })}
      {error && (
        <p id={errorId} role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

const alertConfig = {
  error: { icon: CircleAlert, classes: "border-danger/40 bg-danger/10 text-danger" },
  success: { icon: CircleCheck, classes: "border-success/40 bg-success/10 text-text" },
  info: { icon: Info, classes: "border-border bg-bg text-text" },
} as const;

export function Alert({ tone, children }: { tone: keyof typeof alertConfig; children: ReactNode }) {
  const { icon: Icon, classes } = alertConfig[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`flex items-start gap-2 rounded-field border px-3 py-2 text-sm ${classes}`}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}
