/*
 * Raiz de toda página do painel (spec 024, R2): o espaço entre os blocos é da página (gap-6),
 * nunca de margem dos cartões. Nada de space-y-* ou grid na raiz; grades ficam dentro do Page.
 *
 * Props: as de um <div> (className extra, aria-live etc.).
 */
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Page({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="page" className={cn("flex min-w-0 flex-col gap-6", className)} {...props} />;
}
