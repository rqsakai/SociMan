// Caixa exigida antes de devolver à fila um envio que pode ter chegado à rede (spec 015,
// Clarifications Q4): "Tentar de novo", "Reagendar" e "Agendar de novo" depois de uma falha incerta.
export function ConfirmoNaoChegou({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-start gap-2 rounded-lg border border-warning bg-warning/10 p-3 text-sm">
      <input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>
        <span className="font-medium">Conferi no app e o rascunho não chegou</span>
        <span className="block text-muted-foreground">
          A TikTok pode ter recebido o vídeo da última vez. Confira a caixa de entrada no app antes de enviar de novo, para não duplicar.
        </span>
      </span>
    </label>
  );
}
