import { ShieldAlert } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { DireitoBadge } from "../canais/DireitoBadge";
import type { Direito } from "@/lib/canais";

export const AVISO_DIREITO = "O direito autoral deste vídeo é de sua responsabilidade";

export interface AvisoItem {
  id: string;
  titulo: string;
  direito: Direito | "avulso";
}

// Aviso de direito antes de gerar cortes de vídeo de canal "Sem acordo" ou avulso (FR-009, princípio II):
// não bloqueia; quem confirma (dono ou membro) fica no histórico da geração. AlertDialog com
// role "alertdialog".
export function AvisoDireito({
  open,
  onOpenChange,
  items,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: AvisoItem[];
  onConfirm: () => void;
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <ShieldAlert className="size-5 text-warning-foreground" aria-hidden="true" />
            {AVISO_DIREITO}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {items.length === 1 ? "Este vídeo é" : `Estes ${items.length} vídeos são`} de canal sem acordo registrado ou
            avulso. O SociMan não bloqueia a geração: ao confirmar, o seu nome, a data e o status de direito ficam no histórico.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <ul className="max-h-48 space-y-2 overflow-y-auto text-sm">
          {items.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate">{i.titulo}</span>
              <DireitoBadge direito={i.direito} />
            </li>
          ))}
        </ul>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Confirmo e quero gerar</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
