import { Loader2, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

// Botão com confirmação em AlertDialog (role "alertdialog"); o botão de confirmar repete o rótulo.
export function ConfirmButton({
  label,
  icon: Icon,
  busy,
  disabled,
  title,
  description,
  onConfirm,
  size = "default",
  variant = "outline",
}: {
  label: string;
  icon?: LucideIcon;
  busy?: boolean;
  disabled?: boolean;
  title: string;
  description: ReactNode;
  onConfirm: () => Promise<void> | void;
  size?: "default" | "sm";
  variant?: "outline" | "ghost";
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button type="button" variant={variant} size={size} disabled={busy || disabled} aria-busy={busy}>
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : Icon && <Icon aria-hidden="true" />}
          {label}
        </Button>
      </AlertDialogTrigger>
      {/* role "dialog" em vez de "alertdialog": contrato de UI dos e2e (getByRole("alertdialog")) */}
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction onClick={() => void onConfirm()}>{label}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
