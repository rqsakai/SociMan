/*
 * Filtros da lista de Conteúdos (spec 014, US1; R10; FilterBar desde a spec 024, T052). Tudo mora
 * na URL (voltar, recarregar e compartilhar o link mantêm a lista) e mudar qualquer filtro volta à
 * página 1. Entra no `toolbar` da tabela, dentro do cartão.
 * - principais: Buscar, Perfil e Estado (por conta, ou "sem conta");
 * - Mais filtros: Conta (as do perfil escolhido), Rede, Origem, Ordem, Arquivados e os períodos
 *   agendado e de criação.
 * Os <select> são nativos (os e2e usam selectOption).
 */
import type { Platform } from "@sociman/contract";
import { useQuery } from "@tanstack/react-query";
import { FilterBar, type FiltroAtivo } from "@/components/data-table";
import { DateField } from "@/components/ui/date-field";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import { atalhos, estadoEfetivoLabel, filtroParams, origemLabel, useFiltroConteudos, type EstadoEfetivo, type Origem } from "@/lib/conteudos";
import { contaPlatformText, perfilKey, platformLabel } from "@/lib/perfis";
import { usePerfisAtivos } from "@/lib/usePerfis";

// "2026-10-07" → "07/10/2026"
const dataBr = (iso: string) => iso.split("-").reverse().join("/");

function periodoTexto(de: string, ate: string): string {
  if (de && ate) return `${dataBr(de)} a ${dataBr(ate)}`;
  return de ? `desde ${dataBr(de)}` : `até ${dataBr(ate)}`;
}

export function FiltrosConteudos() {
  const [params, set] = useFiltroConteudos();
  const perfis = usePerfisAtivos();
  const perfilId = params.get("perfil") ?? "";
  const perfil = useQuery({ queryKey: perfilKey(perfilId), queryFn: () => api.perfis.get(perfilId), enabled: Boolean(perfilId) });
  const contas = perfil.data?.contas.filter((c) => !c.archived) ?? [];

  const v = (k: string) => params.get(k) ?? "";
  const limpar = (...ks: string[]) => () => set(Object.fromEntries(ks.map((k) => [k, null])));

  const ativos: FiltroAtivo[] = [];
  if (v("q")) ativos.push({ chave: "q", rotulo: "Busca", valor: v("q"), limpar: limpar("q") });
  if (perfilId) {
    const nome = perfis.data?.find((p) => p.id === perfilId)?.name ?? "…";
    ativos.push({ chave: "perfil", rotulo: "Perfil", valor: nome, limpar: limpar("perfil", "conta") });
  }
  if (v("estado")) {
    const e = v("estado");
    const valor = e === "sem_conta" ? "Sem conta" : (estadoEfetivoLabel[e as EstadoEfetivo] ?? e);
    ativos.push({ chave: "estado", rotulo: "Estado", valor, limpar: limpar("estado") });
  }
  if (v("atalho")) {
    const valor = atalhos.find((a) => a.id === v("atalho"))?.label ?? v("atalho");
    ativos.push({ chave: "atalho", rotulo: "Atalho", valor, limpar: limpar("atalho") });
  }
  if (v("conta")) {
    const c = contas.find((x) => x.id === v("conta"));
    ativos.push({ chave: "conta", rotulo: "Conta", valor: c ? `@${c.handle}` : "…", limpar: limpar("conta"), mais: true });
  }
  if (v("plataforma")) {
    const valor = platformLabel[v("plataforma") as Platform] ?? v("plataforma");
    ativos.push({ chave: "plataforma", rotulo: "Rede", valor, limpar: limpar("plataforma"), mais: true });
  }
  if (v("origem")) {
    const valor = origemLabel[v("origem") as Origem] ?? v("origem");
    ativos.push({ chave: "origem", rotulo: "Origem", valor, limpar: limpar("origem"), mais: true });
  }
  if (v("ordem") === "agenda") {
    ativos.push({ chave: "ordem", rotulo: "Ordem", valor: "Próximos na agenda", limpar: limpar("ordem"), mais: true });
  }
  if (v("arquivados") === "1") {
    ativos.push({ chave: "arquivados", rotulo: "Arquivados", valor: "Sim", limpar: limpar("arquivados"), mais: true });
  }
  for (const [rotulo, de, ate] of [["Agendado", "agendadoDe", "agendadoAte"], ["Criado", "criadoDe", "criadoAte"]] as const) {
    if (v(de) || v(ate)) {
      ativos.push({ chave: de, rotulo, valor: periodoTexto(v(de), v(ate)), limpar: limpar(de, ate), mais: true });
    }
  }

  return (
    <FilterBar
      busca={{
        valor: v("q"),
        onChange: (q) => set({ q: q || null }, { replace: true }),
        placeholder: "Buscar nos títulos, ganchos…",
      }}
      principais={
        <>
          <Field label="Perfil" className="w-full sm:w-52">
            {({ id }) => (
              <NativeSelect id={id} value={perfilId} onChange={(e) => set({ perfil: e.target.value || null, conta: null })}>
                <option value="">Todos os perfis</option>
                {perfis.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Estado" className="w-full sm:w-44">
            {({ id }) => (
              <NativeSelect id={id} value={v("estado")} onChange={(e) => set({ estado: e.target.value || null })}>
                <option value="">Todos</option>
                <option value="sem_conta">Sem conta</option>
                {(Object.keys(estadoEfetivoLabel) as EstadoEfetivo[]).map((s) => (
                  <option key={s} value={s}>
                    {estadoEfetivoLabel[s]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </>
      }
      mais={
        <>
          <Field label="Conta">
            {({ id }) => (
              <NativeSelect id={id} value={v("conta")} disabled={!perfilId} onChange={(e) => set({ conta: e.target.value || null })}>
                <option value="">{perfilId ? "Todas as contas" : "Escolha um perfil"}</option>
                {contas.map((c) => (
                  <option key={c.id} value={c.id}>
                    {contaPlatformText(c)} @{c.handle}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Rede">
            {({ id }) => (
              <NativeSelect id={id} value={v("plataforma")} onChange={(e) => set({ plataforma: e.target.value || null })}>
                <option value="">Todas</option>
                {(Object.keys(platformLabel) as Platform[]).map((p) => (
                  <option key={p} value={p}>
                    {platformLabel[p]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Origem">
            {({ id }) => (
              <NativeSelect id={id} value={v("origem")} onChange={(e) => set({ origem: e.target.value || null })}>
                <option value="">Todas</option>
                {(Object.keys(origemLabel) as Origem[]).map((o) => (
                  <option key={o} value={o}>
                    {origemLabel[o]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Ordem">
            {({ id }) => (
              <NativeSelect id={id} value={v("ordem")} onChange={(e) => set({ ordem: e.target.value || null })}>
                <option value="">Mais recentes</option>
                <option value="agenda">Próximos na agenda</option>
              </NativeSelect>
            )}
          </Field>
          <label className="flex h-9 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={v("arquivados") === "1"}
              onChange={(e) => set({ arquivados: e.target.checked ? "1" : null })}
            />
            Arquivados
          </label>
          <Periodo label="Agendado" de="agendadoDe" ate="agendadoAte" params={params} set={set} />
          <Periodo label="Criado" de="criadoDe" ate="criadoAte" params={params} set={set} />
        </>
      }
      ativos={ativos}
      onLimpar={() => set(Object.fromEntries(filtroParams.map((k) => [k, null])))}
    />
  );
}

function Periodo({
  label,
  de,
  ate,
  params,
  set,
}: {
  label: string;
  de: string;
  ate: string;
  params: URLSearchParams;
  set: (patch: Record<string, string | null>) => void;
}) {
  const vDe = params.get(de) ?? "";
  const vAte = params.get(ate) ?? "";
  const invertido = Boolean(vDe && vAte && vDe > vAte);
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">{label}</legend>
      <div className="flex items-center gap-1.5">
        <DateField aria-label={`${label} de`} value={vDe} onChange={(iso) => set({ [de]: iso || null })} className="w-40" />
        <span className="text-sm text-muted-foreground">a</span>
        <DateField
          aria-label={`${label} até`}
          value={vAte}
          aria-invalid={invertido}
          onChange={(iso) => set({ [ate]: iso || null })}
          className="w-40"
        />
      </div>
      {invertido && (
        <p role="alert" className="text-xs text-destructive">
          A data inicial é depois da final.
        </p>
      )}
    </fieldset>
  );
}
