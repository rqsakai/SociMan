/*
 * Rodapé discreto do painel (spec 005, US1). Sem props.
 * Texto pequeno à esquerda e o build atual (data-build do <html>) à direita.
 */
export function Footer() {
  const build = document.documentElement.dataset.build;
  return (
    <footer className="flex flex-wrap items-center justify-between gap-2 px-4 py-6 text-xs text-muted-foreground sm:px-6">
      <p>SociMan · gestão das contas de mídia social da agência. Nenhuma publicação sai daqui.</p>
      {build && <p className="font-mono">build {build.slice(0, 16)}</p>}
    </footer>
  );
}
