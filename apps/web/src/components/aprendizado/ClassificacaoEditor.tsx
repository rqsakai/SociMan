/*
 * Editor da classificação de um post (spec 023, US1; FR-003, FR-005, FR-006): tema principal (ou
 * "Sem tema"), até 2 secundários e o estilo do gancho, com <select> nativo (os e2e usam
 * selectOption). Salvar grava `origem = dono`, e a IA nunca mais sobrescreve essa linha.
 */
import { Loader2, Save } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { api } from "@/lib/api";
import { ESTILOS_GANCHO, estiloGanchoLabel, type AprendizadoClassificacao, type AprendizadoTema, type EstiloGancho } from "@/lib/aprendizado";

export function ClassificacaoEditor({
  classificacao,
  temas,
  onSalvo,
  onCancelar,
}: {
  classificacao: AprendizadoClassificacao;
  temas: AprendizadoTema[];
  onSalvo: () => Promise<void> | void;
  onCancelar: () => void;
}) {
  const [temaId, setTemaId] = useState(classificacao.temaId ?? "");
  const [sec1, setSec1] = useState(classificacao.secundarios[0] ?? "");
  const [sec2, setSec2] = useState(classificacao.secundarios[1] ?? "");
  const [estilo, setEstilo] = useState<EstiloGancho | "">((classificacao.estiloGancho as EstiloGancho | null) ?? "");
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<unknown>(null);
  const titulo = classificacao.post?.tituloCurto || "post sem legenda";

  const secundarios = [sec1, sec2].filter((s, i, arr) => s && s !== temaId && arr.indexOf(s) === i);

  async function salvar() {
    setBusy(true);
    setErro(null);
    try {
      await api.aprendizado.classificacoes.put(classificacao.videoId, {
        version: classificacao.version,
        temaId: temaId || null,
        secundarios,
        estiloGancho: estilo || null,
      });
      toast.success("Classificação corrigida. A IA não muda mais este post.");
      await onSalvo();
    } catch (err) {
      setErro(err);
    } finally {
      setBusy(false);
    }
  }

  const opcoesTema = (vazio: string) => (
    <>
      <option value="">{vazio}</option>
      {temas.map((t) => (
        <option key={t.id} value={t.id}>
          {t.nome}
        </option>
      ))}
    </>
  );

  return (
    <div role="group" aria-label={`Corrigir a classificação de ${titulo}`} className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Tema principal">
          {({ id }) => (
            <NativeSelect id={id} value={temaId} onChange={(e) => setTemaId(e.target.value)}>
              {opcoesTema("Sem tema")}
            </NativeSelect>
          )}
        </Field>
        <Field label="Estilo do gancho">
          {({ id }) => (
            <NativeSelect id={id} value={estilo} onChange={(e) => setEstilo(e.target.value as EstiloGancho | "")}>
              <option value="">Sem gancho</option>
              {ESTILOS_GANCHO.map((s) => (
                <option key={s} value={s}>
                  {estiloGanchoLabel[s]}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Secundário 1">
          {({ id }) => (
            <NativeSelect id={id} value={sec1} onChange={(e) => setSec1(e.target.value)}>
              {opcoesTema("Nenhum")}
            </NativeSelect>
          )}
        </Field>
        <Field label="Secundário 2">
          {({ id }) => (
            <NativeSelect id={id} value={sec2} onChange={(e) => setSec2(e.target.value)}>
              {opcoesTema("Nenhum")}
            </NativeSelect>
          )}
        </Field>
      </div>
      {erro !== null && <ApiErrorAlert error={erro} onReload={() => void onSalvo()} />}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" disabled={busy} aria-busy={busy} onClick={() => void salvar()}>
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
          Salvar correção
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancelar}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}
