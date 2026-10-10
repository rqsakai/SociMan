import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Copy, CornerLeftUp, CornerRightDown, Loader2, Plus, Save, Trash2, Undo2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { useRascunho } from "@/components/produtos/useRascunho";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { perfilNomeDe, TETO_TEXTO, useCenasOpcoes, usePerfisTodos } from "@/lib/estudio";
import { LIM, roteiroKey, type Roteiro } from "@/lib/roteiros";
import { Andamentos, BotaoAprovar, type EtapaProps } from "./comum";

// Um bloco = uma posição do roteiro: a cena e as frases dela, em ordem. As frases do roteiro são a
// concatenação dos blocos, então "toda frase em exatamente uma cena, em ordem" vale por construção.
interface Bloco {
  cenaId: string;
  cenaNome: string;
  reaproveitada: boolean;
  tomadaId: string | null;
  frases: string[];
}

function blocosDe(r: Roteiro): Bloco[] {
  return r.posicoes.map((p) => ({
    cenaId: p.cena.id,
    cenaNome: p.cena.nome,
    reaproveitada: p.reaproveitada,
    tomadaId: p.tomada?.id ?? null,
    frases: p.frases.map((i) => r.frases[i] ?? ""),
  }));
}

// Etapa Texto (spec 011, US1, T022): as frases de venda por cena, editáveis; trocar, reordenar,
// reaproveitar (da biblioteca da agência) ou duplicar a cena; mover a frase de uma cena para a vizinha;
// salvar (o PATCH recusa com o motivo se a regra quebrar) e aprovar.
export function Texto({ roteiro, rodar, travado }: EtapaProps) {
  const queryClient = useQueryClient();
  const r = useRascunho(blocosDe(roteiro), roteiro.version);
  const blocos = r.valor;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [duplicando, setDuplicando] = useState<number | null>(null);
  const [nova, setNova] = useState("");
  const perfis = usePerfisTodos();
  const cenas = useCenasOpcoes(roteiro.perfilId);
  const totalFrases = blocos.reduce((n, b) => n + b.frases.length, 0);
  const depoisDoTexto = !["rascunho", "planejando", "aguardando_texto"].includes(roteiro.status) && !(roteiro.status === "falhou" && roteiro.etapaFalhou === "plano");

  const setBlocos = (b: Bloco[]) => r.setValor(b);
  const mudarBloco = (i: number, patch: Partial<Bloco>) => setBlocos(blocos.map((b, k) => (k === i ? { ...b, ...patch } : b)));
  const mudarFrase = (i: number, j: number, texto: string) => mudarBloco(i, { frases: blocos[i]!.frases.map((f, k) => (k === j ? texto : f)) });

  function moverBloco(i: number, d: -1 | 1) {
    const j = i + d;
    if (j < 0 || j >= blocos.length) return;
    const c = [...blocos];
    [c[i], c[j]] = [c[j]!, c[i]!];
    setBlocos(c);
  }
  // A primeira frase vai para o fim da cena anterior; a última, para o começo da seguinte.
  function fraseParaAnterior(i: number) {
    if (i === 0 || blocos[i]!.frases.length < 2) return;
    const c = blocos.map((b) => ({ ...b, frases: [...b.frases] }));
    c[i - 1]!.frases.push(c[i]!.frases.shift()!);
    setBlocos(c);
  }
  function fraseParaSeguinte(i: number) {
    if (i === blocos.length - 1 || blocos[i]!.frases.length < 2) return;
    const c = blocos.map((b) => ({ ...b, frases: [...b.frases] }));
    c[i + 1]!.frases.unshift(c[i]!.frases.pop()!);
    setBlocos(c);
  }
  function trocarCena(i: number, cenaId: string) {
    const c = cenas.itens?.find((x) => x.id === cenaId);
    if (c) mudarBloco(i, { cenaId: c.id, cenaNome: c.nome, reaproveitada: true, tomadaId: null });
  }
  function adicionarCena() {
    const c = cenas.itens?.find((x) => x.id === nova);
    if (!c) return;
    setBlocos([...blocos, { cenaId: c.id, cenaNome: c.nome, reaproveitada: true, tomadaId: null, frases: [""] }]);
    setNova("");
  }
  async function duplicar(i: number) {
    setDuplicando(i);
    setError(null);
    try {
      const copia = await api.cenas.duplicar(blocos[i]!.cenaId);
      mudarBloco(i, { cenaId: copia.id, cenaNome: copia.nome, reaproveitada: false, tomadaId: null });
      void queryClient.invalidateQueries({ queryKey: ["cenas"] });
    } catch (err) {
      setError(err);
    } finally {
      setDuplicando(null);
    }
  }

  async function salvar() {
    setError(null);
    setBusy(true);
    let indice = 0;
    const frases = blocos.flatMap((b) => b.frases.map((f) => f.trim()));
    const posicoes = blocos.map((b) => ({ cenaId: b.cenaId, frases: b.frases.map(() => indice++), tomadaId: b.tomadaId }));
    try {
      const novo = await api.roteiros.editar(roteiro.id, { version: r.versao, frases, posicoes });
      queryClient.setQueryData(roteiroKey(roteiro.id), novo);
      r.reiniciar(blocosDe(novo), novo.version);
      await rodar(async () => novo, depoisDoTexto ? "Texto salvo. O roteiro refaz a narração e o que depende dela." : "Texto salvo.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (roteiro.status === "planejando" || (roteiro.status === "rascunho" && roteiro.posicoes.length === 0)) {
    return (
      <div className="space-y-3" data-testid="etapa-texto">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {roteiro.status === "planejando"
            ? "A IA está escrevendo as frases de venda e propondo as cenas, reaproveitando as da biblioteca quando servem."
            : 'Ainda sem plano. Use "Planejar com IA" no topo para a IA escrever as frases e propor as cenas.'}
        </p>
        <Andamentos geracoes={roteiro.geracoesAbertas} filtro={(g) => g.passo === "roteiro.plano"} />
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="etapa-texto">
      {/* com edição não salva, o "Aprovar" some: salve antes */}
      <BotaoAprovar roteiro={roteiro} rodar={rodar} travado={travado || r.sujo} portao="texto" />
      {depoisDoTexto && !travado && (
        <p className="text-sm text-muted-foreground">Mudar o texto ou as cenas agora refaz a narração e o que depende dela. Nada já gerado é apagado.</p>
      )}
      <ol className="space-y-3" aria-label="Cenas e frases">
        {blocos.map((b, i) => (
          <li key={`${b.cenaId}-${i}`} className="space-y-3 rounded-xl border p-3" data-testid={`texto-cena-${i + 1}`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">Cena {i + 1}</span>
              <Link to={`/app/cenas/${b.cenaId}`} className="min-w-0 truncate text-sm underline-offset-2 hover:underline">
                {b.cenaNome}
              </Link>
              <Badge variant={b.reaproveitada ? "secondary" : "outline"} data-testid="cena-origem">
                {b.reaproveitada ? "reaproveitada" : "nova"}
              </Badge>
              {!travado && (
                <span className="ml-auto flex flex-wrap gap-1">
                  <Button type="button" variant="ghost" size="icon-sm" aria-label={`Subir a cena ${i + 1}`} disabled={i === 0} onClick={() => moverBloco(i, -1)}>
                    <ArrowUp aria-hidden="true" />
                  </Button>
                  <Button type="button" variant="ghost" size="icon-sm" aria-label={`Descer a cena ${i + 1}`} disabled={i === blocos.length - 1} onClick={() => moverBloco(i, 1)}>
                    <ArrowDown aria-hidden="true" />
                  </Button>
                  <Button type="button" variant="ghost" size="sm" disabled={duplicando !== null} aria-busy={duplicando === i} onClick={() => void duplicar(i)}>
                    {duplicando === i ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Copy aria-hidden="true" />}
                    Duplicar cena
                  </Button>
                  <Button type="button" variant="ghost" size="icon-sm" aria-label={`Tirar a cena ${i + 1}`} disabled={blocos.length <= 1} onClick={() => setBlocos(blocos.filter((_, k) => k !== i))}>
                    <Trash2 aria-hidden="true" />
                  </Button>
                </span>
              )}
            </div>
            {!travado && (
              <Field label={`Trocar a cena ${i + 1}`} className="sm:max-w-md">
                {({ id }) => (
                  <NativeSelect id={id} value="" onChange={(e) => trocarCena(i, e.target.value)}>
                    <option value="">Escolher outra cena da biblioteca…</option>
                    {(cenas.itens ?? []).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.nome} · {perfilNomeDe(c, perfis.data)}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
            )}
            <ol className="space-y-2">
              {b.frases.map((f, j) => (
                <li key={j} className="flex items-center gap-2">
                  <Input
                    aria-label={`Cena ${i + 1}, frase ${j + 1}`}
                    value={f}
                    maxLength={LIM.frase}
                    disabled={travado}
                    onChange={(e) => mudarFrase(i, j, e.target.value)}
                  />
                  {!travado && j === 0 && i > 0 && b.frases.length > 1 && (
                    <Button type="button" variant="ghost" size="icon-sm" aria-label={`Mover a frase para a cena ${i}`} onClick={() => fraseParaAnterior(i)}>
                      <CornerLeftUp aria-hidden="true" />
                    </Button>
                  )}
                  {!travado && j === b.frases.length - 1 && i < blocos.length - 1 && b.frases.length > 1 && (
                    <Button type="button" variant="ghost" size="icon-sm" aria-label={`Mover a frase para a cena ${i + 2}`} onClick={() => fraseParaSeguinte(i)}>
                      <CornerRightDown aria-hidden="true" />
                    </Button>
                  )}
                  {!travado && b.frases.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Tirar a frase ${j + 1} da cena ${i + 1}`}
                      onClick={() => mudarBloco(i, { frases: b.frases.filter((_, k) => k !== j) })}
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  )}
                </li>
              ))}
            </ol>
            {!travado && totalFrases < LIM.frases && (
              <Button type="button" variant="outline" size="sm" onClick={() => mudarBloco(i, { frases: [...b.frases, ""] })}>
                <Plus aria-hidden="true" />
                Incluir frase
              </Button>
            )}
          </li>
        ))}
      </ol>

      {!travado && blocos.length < roteiro.maxCenas && (
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Reaproveitar cena" className="min-w-56 flex-1" hint={cenas.truncado ? TETO_TEXTO : "As do perfil do vídeo primeiro, depois os modelos sem perfil."}>
            {({ id, describedBy }) => (
              <NativeSelect id={id} value={nova} aria-describedby={describedBy} onChange={(e) => setNova(e.target.value)}>
                <option value="">Escolha uma cena…</option>
                {(cenas.itens ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nome} · {perfilNomeDe(c, perfis.data)}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Button type="button" variant="outline" disabled={!nova} onClick={adicionarCena}>
            <Plus aria-hidden="true" />
            Adicionar cena
          </Button>
        </div>
      )}

      {r.mudouFora && <p role="status" className="text-sm text-warning-foreground">O roteiro mudou em outro lugar. Salvar vai pedir para recarregar.</p>}
      {error !== null && (
        <ApiErrorAlert
          error={error}
          onReload={() => {
            setError(null);
            r.reiniciar(blocosDe(roteiro), roteiro.version);
          }}
        />
      )}
      {!travado && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={busy || !r.sujo} aria-busy={busy} onClick={() => void salvar()}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Save aria-hidden="true" />}
            Salvar texto
          </Button>
          {r.sujo && (
            <Button type="button" variant="ghost" disabled={busy} onClick={() => r.reiniciar(blocosDe(roteiro), roteiro.version)}>
              <Undo2 aria-hidden="true" />
              Descartar alterações
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
