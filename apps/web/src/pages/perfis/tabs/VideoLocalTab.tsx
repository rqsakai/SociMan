/*
 * Aba "Vídeo local" do perfil (spec 011, US6/US8, T048/T053; FR-051): o padrão de portões e de modo que
 * todo roteiro novo do perfil herda (sem linha = o padrão do código, todos ligados e "revisar") e o
 * dicionário de pronúncia da voz (como se escreve → como se fala; só vale na narração, o texto e a
 * legenda continuam com a grafia certa). Dono e membro editam; a escrita repetida (sem diferenciar
 * maiúsculas) é recusada.
 */
import type { Perfil } from "@sociman/contract";
import { useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Check, Loader2, Pencil, Plus, Save, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { Portoes, type ModoRoteiro, type PortoesValor } from "@/components/roteiro/Portoes";
import { HeaderCard, Page } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { LIM, roteiroPadroesKey, usePronuncias, useRoteiroPadroes, type Pronuncia } from "@/lib/roteiros";

export function VideoLocalTab({ perfil }: { perfil: Perfil }) {
  return (
    <Page>
      <PadroesCard perfil={perfil} />
      <PronunciasCard perfil={perfil} />
    </Page>
  );
}

function PadroesCard({ perfil }: { perfil: Perfil }) {
  const queryClient = useQueryClient();
  const padroes = useRoteiroPadroes(perfil.id);
  const [rascunho, setRascunho] = useState<{ modo: ModoRoteiro; portoes: PortoesValor } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const p = padroes.data;
  const valor = rascunho ?? (p ? { modo: p.modo, portoes: p.portoes } : null);

  async function salvar() {
    if (!p || !valor) return;
    setBusy(true);
    setError(null);
    try {
      await api.roteiros.padroesSalvar(perfil.id, { version: p.version, ...valor });
      setRascunho(null);
      toast.success("Padrão dos vídeos salvo. Vale para os roteiros novos.");
      await queryClient.invalidateQueries({ queryKey: roteiroPadroesKey(perfil.id) });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <HeaderCard title="Portões padrão" description="Todo vídeo novo deste perfil começa com estes portões e este modo. Os vídeos que já existem não mudam.">
      <div className="space-y-4" data-testid="padroes-roteiro">
        {padroes.isError && <ApiErrorAlert error={padroes.error} />}
        {p && p.version === 0 && <p className="text-sm text-muted-foreground">Ainda sem padrão salvo: vale o do SociMan (todos os portões ligados, modo revisar).</p>}
        {valor && <Portoes modo={valor.modo} portoes={valor.portoes} disabled={perfil.archived || busy} onChange={setRascunho} />}
        {error !== null && <ApiErrorAlert error={error} onReload={() => void queryClient.invalidateQueries({ queryKey: roteiroPadroesKey(perfil.id) }).then(() => setError(null))} />}
        {!perfil.archived && (
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" disabled={busy || rascunho === null} aria-busy={busy} onClick={() => void salvar()}>
              {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
              Salvar padrão
            </Button>
            {rascunho && (
              <Button type="button" variant="ghost" disabled={busy} onClick={() => setRascunho(null)}>
                Descartar
              </Button>
            )}
          </div>
        )}
      </div>
    </HeaderCard>
  );
}

function PronunciasCard({ perfil }: { perfil: Perfil }) {
  const queryClient = useQueryClient();
  const [arquivadas, setArquivadas] = useState(false);
  const lista = usePronuncias(perfil.id, arquivadas);
  const [escrita, setEscrita] = useState("");
  const [falada, setFalada] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [editando, setEditando] = useState<{ id: string; escrita: string; falada: string } | null>(null);
  const travado = perfil.archived;
  const recarregar = () => queryClient.invalidateQueries({ queryKey: ["pronuncias", perfil.id] });

  async function rodar(chave: string, fn: () => Promise<unknown>, ok: string) {
    setBusy(chave);
    setError(null);
    try {
      await fn();
      toast.success(ok);
      await recarregar();
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function incluir(e: FormEvent) {
    e.preventDefault();
    if (!escrita.trim() || !falada.trim()) return;
    if (await rodar("nova", () => api.pronuncias.criar(perfil.id, { escrita: escrita.trim(), falada: falada.trim() }), "Pronúncia incluída.")) {
      setEscrita("");
      setFalada("");
    }
  }

  const itens: Pronuncia[] = lista.data?.items ?? [];
  return (
    <Card className="shadow-card" aria-labelledby="pronuncias-titulo" data-testid="pronuncias">
      <CardHeader>
        <CardTitle>
          <h2 id="pronuncias-titulo">Dicionário de pronúncia</h2>
        </CardTitle>
        <CardDescription>
          Como se escreve → como a voz deve falar (o agudo abre a vogal; o circunflexo fecha). Ex.: levinho → lévinho. Mudar uma pronúncia
          deixa desatualizada a narração que usa a palavra.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={arquivadas} onCheckedChange={setArquivadas} aria-label="Ver arquivadas" />
          Ver arquivadas
        </label>
        {lista.isError && <ApiErrorAlert error={lista.error} />}
        {lista.data && itens.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma pronúncia{arquivadas ? " arquivada" : ""} ainda.</p>}
        {itens.length > 0 && (
          <table className="w-full text-sm" aria-label="Pronúncias">
            <thead className="text-left text-xs text-muted-foreground uppercase">
              <tr>
                <th className="py-1.5 pr-2 font-semibold">Escrita</th>
                <th className="py-1.5 pr-2 font-semibold">Falada</th>
                <th className="py-1.5" />
              </tr>
            </thead>
            <tbody>
              {itens.map((p) => {
                const ed = editando?.id === p.id ? editando : null;
                return (
                  <tr key={p.id} className="border-t align-middle" data-testid={`pronuncia-${p.escrita}`}>
                    <td className="py-1.5 pr-2">
                      {ed ? (
                        <Input aria-label={`Escrita de ${p.escrita}`} value={ed.escrita} maxLength={LIM.palavra} onChange={(e) => setEditando({ ...ed, escrita: e.target.value })} />
                      ) : (
                        p.escrita
                      )}
                    </td>
                    <td className="py-1.5 pr-2">
                      {ed ? (
                        <Input aria-label={`Falada de ${p.escrita}`} value={ed.falada} maxLength={LIM.palavra} onChange={(e) => setEditando({ ...ed, falada: e.target.value })} />
                      ) : (
                        p.falada
                      )}
                    </td>
                    <td className="py-1.5 text-right whitespace-nowrap">
                      {!travado &&
                        (ed ? (
                          <>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon-sm"
                              aria-label={`Salvar ${p.escrita}`}
                              disabled={busy !== null}
                              onClick={async () => {
                                if (await rodar(p.id, () => api.pronuncias.editar(p.id, { version: p.version, escrita: ed.escrita.trim(), falada: ed.falada.trim() }), "Pronúncia salva.")) setEditando(null);
                              }}
                            >
                              {busy === p.id ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Check aria-hidden="true" />}
                            </Button>
                            <Button type="button" variant="ghost" size="icon-sm" aria-label="Cancelar a edição" onClick={() => setEditando(null)}>
                              <X aria-hidden="true" />
                            </Button>
                          </>
                        ) : p.archived ? (
                          <Button type="button" variant="ghost" size="sm" disabled={busy !== null} onClick={() => void rodar(p.id, () => api.pronuncias.restaurar(p.id, p.version), "Pronúncia restaurada.")}>
                            <ArchiveRestore aria-hidden="true" />
                            Restaurar
                          </Button>
                        ) : (
                          <>
                            <Button type="button" variant="ghost" size="icon-sm" aria-label={`Editar ${p.escrita}`} onClick={() => setEditando({ id: p.id, escrita: p.escrita, falada: p.falada })}>
                              <Pencil aria-hidden="true" />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon-sm"
                              aria-label={`Arquivar ${p.escrita}`}
                              disabled={busy !== null}
                              onClick={() => void rodar(p.id, () => api.pronuncias.arquivar(p.id, p.version), "Pronúncia arquivada.")}
                            >
                              <Archive aria-hidden="true" />
                            </Button>
                          </>
                        ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {error !== null && <ApiErrorAlert error={error} onReload={() => void recarregar().then(() => setError(null))} />}
        {!travado && !arquivadas && (
          <form onSubmit={(e) => void incluir(e)} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end" noValidate data-testid="pronuncia-nova">
            <Field label="Como se escreve">
              {({ id }) => <Input id={id} value={escrita} maxLength={LIM.palavra} onChange={(e) => setEscrita(e.target.value)} />}
            </Field>
            <Field label="Como se fala">
              {({ id }) => <Input id={id} value={falada} maxLength={LIM.palavra} onChange={(e) => setFalada(e.target.value)} />}
            </Field>
            <Button type="submit" variant="outline" disabled={busy !== null || !escrita.trim() || !falada.trim()} aria-busy={busy === "nova"}>
              {busy === "nova" ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Plus aria-hidden="true" />}
              Incluir pronúncia
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
