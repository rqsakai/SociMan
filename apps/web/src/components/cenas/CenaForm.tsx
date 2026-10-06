/*
 * Formulário da cena (spec 010, FR-001/FR-002). Controlado pela página (valores + onChange), para o
 * "Aplicar" da IA e a proposta do agente preencherem campos sem perder o resto.
 *
 * - avatar com look ou pose (arquivo `referencia`/`pose` do avatar; vazio = imagem principal);
 * - cenário com a imagem do ingrediente; plano, movimento e detalhe de câmera;
 * - ação (obrigatória, em inglês), fala (pt-BR), texto na tela (guia de edição, fora do prompt);
 * - iluminação e estilo, áudio e negative (vazios = padrão do perfil);
 * - duração 4/6/8 s e modo do Flow (quadros inicial e final só no modo "Frames to Video");
 * - produto: nome curto e foto opcional da biblioteca (asset tipo imagem).
 *
 * `bloquearPrompt` (cena usada) deixa só nome, tags e notas editáveis. `iaCampo` decora os 4 campos
 * de texto com o "Melhorar com IA" (spec 008).
 */
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { LibraryImageDialog } from "@/components/assets/LibraryImageDialog";
import { Button } from "@/components/ui/button";
import { Field, NativeSelect } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { activeFiles, assetKey, parseTags, roleLabel } from "@/lib/assets";
import {
  contarPalavras,
  DURACOES,
  falaMaxPalavras,
  LIM,
  modoCenaLabel,
  movimentoLabel,
  planoLabel,
  type CenaAssetRef,
  type CenaCampos,
  type CenaModo,
  type CenaMovimento,
  type CenaPlano,
  type Duracao,
} from "@/lib/cenas";

export type CampoIa = "acao" | "camera" | "estilo" | "audio";

export interface CenaFormRefs {
  avatar?: CenaAssetRef | null;
  cenario?: CenaAssetRef | null;
  produtoImagem?: CenaAssetRef | null;
}

const vazio = (v: string) => (v === "" ? null : v);

export function CenaForm({
  perfilId,
  valores,
  onChange,
  refs,
  padroes,
  bloquearPrompt = false,
  disabled = false,
  iaCampo,
}: {
  perfilId: string;
  valores: CenaCampos;
  onChange: (patch: Partial<CenaCampos>) => void;
  refs?: CenaFormRefs;
  padroes?: { estilo: string; negative: string };
  bloquearPrompt?: boolean;
  disabled?: boolean;
  iaCampo?: (campo: CampoIa, render: (botao: ReactNode) => ReactNode) => ReactNode;
}) {
  const v = valores;
  const travado = disabled || bloquearPrompt;
  const decorar = (campo: CampoIa, render: (botao: ReactNode) => ReactNode) => (iaCampo ? iaCampo(campo, render) : render(null));

  const avatares = useQuery({
    queryKey: ["assets", perfilId, "cena-opcoes", "avatar"],
    queryFn: () => api.assets.list(perfilId, { tipo: ["avatar"], archived: "false", limit: 100 }),
  });
  const cenarios = useQuery({
    queryKey: ["assets", perfilId, "cena-opcoes", "cenario"],
    queryFn: () => api.assets.list(perfilId, { tipo: ["cenario"], archived: "false", limit: 100 }),
  });
  const avatar = useQuery({ queryKey: assetKey(v.avatarId ?? ""), queryFn: () => api.assets.get(v.avatarId!), enabled: Boolean(v.avatarId) });
  const cenario = useQuery({ queryKey: assetKey(v.cenarioId ?? ""), queryFn: () => api.assets.get(v.cenarioId!), enabled: Boolean(v.cenarioId) });

  // Opções: os ativos da biblioteca, mais o referenciado (que pode estar arquivado).
  const opcoes = (itens: { id: string; name: string }[] | undefined, atual: CenaAssetRef | null | undefined) => {
    const lista = (itens ?? []).map((a) => ({ id: a.id, nome: a.name, arquivada: false }));
    if (atual && !lista.some((a) => a.id === atual.id)) lista.unshift(atual);
    return lista;
  };
  const avatarOpcoes = opcoes(avatares.data?.items, refs?.avatar);
  const cenarioOpcoes = opcoes(cenarios.data?.items, refs?.cenario);
  const avatarArquivos = avatar.data ? [...activeFiles(avatar.data.asset, "referencia"), ...activeFiles(avatar.data.asset, "pose")] : [];
  const cenarioArquivos = cenario.data ? activeFiles(cenario.data.asset, "referencia") : [];

  // Foto do produto: nome e miniatura do que foi escolhido nesta sessão (a cena salva só traz o nome).
  const [foto, setFoto] = useState<{ id: string; nome: string; thumb: string | null } | null>(
    v.produtoImagemId ? { id: v.produtoImagemId, nome: refs?.produtoImagem?.nome ?? "Foto escolhida", thumb: null } : null,
  );
  useEffect(() => {
    if (!v.produtoImagemId) setFoto(null);
  }, [v.produtoImagemId]);

  const [tagsTexto, setTagsTexto] = useState(v.tags.join(", "));
  useEffect(() => {
    if (parseTags(tagsTexto).join(",") !== v.tags.join(",")) setTagsTexto(v.tags.join(", "));
    // só quando as tags mudam de fora (proposta, recarga)
  }, [v.tags.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const palavras = contarPalavras(v.fala);
  const maxPalavras = falaMaxPalavras(v.duracaoS);

  return (
    <div className="space-y-6">
      <fieldset className="space-y-4" disabled={disabled}>
        <legend className="sr-only">Identificação</legend>
        <Field label="Nome da cena" hint={`${v.nome.length}/${LIM.nome}`}>
          {({ id, describedBy }) => (
            <Input id={id} value={v.nome} maxLength={LIM.nome} required aria-describedby={describedBy} onChange={(e) => onChange({ nome: e.target.value })} />
          )}
        </Field>
      </fieldset>

      <fieldset className="space-y-4" disabled={travado}>
        <legend className="text-sm font-semibold">Quem e onde</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Avatar" hint="Opcional: sem avatar, o prompt começa pela ação.">
            {({ id, describedBy }) => (
              <NativeSelect
                id={id}
                aria-describedby={describedBy}
                value={v.avatarId ?? ""}
                onChange={(e) => onChange({ avatarId: vazio(e.target.value), avatarArquivoId: null })}
              >
                <option value="">Sem avatar</option>
                {avatarOpcoes.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nome}
                    {a.arquivada ? " (arquivado)" : ""}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Look ou pose">
            {({ id }) => (
              <NativeSelect id={id} value={v.avatarArquivoId ?? ""} disabled={!v.avatarId} onChange={(e) => onChange({ avatarArquivoId: vazio(e.target.value) })}>
                <option value="">Imagem principal</option>
                {avatarArquivos.map((f) => (
                  <option key={f.id} value={f.id}>
                    {roleLabel[f.role]}: {f.label || f.look || f.uso || "sem nome"}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Cenário" hint="Opcional: o prompt do ambiente entra como está no asset.">
            {({ id, describedBy }) => (
              <NativeSelect
                id={id}
                aria-describedby={describedBy}
                value={v.cenarioId ?? ""}
                onChange={(e) => onChange({ cenarioId: vazio(e.target.value), cenarioArquivoId: null })}
              >
                <option value="">Sem cenário</option>
                {cenarioOpcoes.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nome}
                    {a.arquivada ? " (arquivado)" : ""}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Imagem do cenário">
            {({ id }) => (
              <NativeSelect id={id} value={v.cenarioArquivoId ?? ""} disabled={!v.cenarioId} onChange={(e) => onChange({ cenarioArquivoId: vazio(e.target.value) })}>
                <option value="">Imagem principal</option>
                {cenarioArquivos.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.label || f.look || "Imagem"}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </div>
      </fieldset>

      <fieldset className="space-y-4" disabled={travado}>
        <legend className="text-sm font-semibold">O que acontece</legend>
        {decorar("acao", (botao) => (
          <Field label="Ação" action={botao} hint={`Em inglês: é o que vai ao prompt. ${v.acao.length}/${LIM.acao}`}>
            {({ id, describedBy }) => (
              <Textarea
                id={id}
                rows={3}
                required
                maxLength={LIM.acao}
                aria-describedby={describedBy}
                placeholder="lifts the lid and steam comes out"
                value={v.acao}
                onChange={(e) => onChange({ acao: e.target.value })}
              />
            )}
          </Field>
        ))}
        <Field
          label="Fala para a câmera"
          hint={
            <span className={palavras > maxPalavras ? "font-medium text-warning-foreground" : undefined}>
              Em português, sem aspas. {palavras}/{maxPalavras} palavras para {v.duracaoS} s.
            </span>
          }
        >
          {({ id, describedBy }) => (
            <Input id={id} maxLength={LIM.fala} aria-describedby={describedBy} value={v.fala ?? ""} onChange={(e) => onChange({ fala: vazio(e.target.value) })} />
          )}
        </Field>
        <Field label="Texto na tela" hint="Guia de edição para você pôr depois; não entra no prompt (o negative bloqueia texto no vídeo).">
          {({ id, describedBy }) => (
            <Input
              id={id}
              maxLength={LIM.textoTela}
              aria-describedby={describedBy}
              value={v.textoTela ?? ""}
              onChange={(e) => onChange({ textoTela: vazio(e.target.value) })}
            />
          )}
        </Field>
      </fieldset>

      <fieldset className="space-y-4" disabled={travado}>
        <legend className="text-sm font-semibold">Câmera, luz e som</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Plano">
            {({ id }) => (
              <NativeSelect id={id} value={v.plano ?? ""} onChange={(e) => onChange({ plano: vazio(e.target.value) as CenaPlano | null })}>
                <option value="">Não definido</option>
                {(Object.keys(planoLabel) as CenaPlano[]).map((p) => (
                  <option key={p} value={p}>
                    {planoLabel[p]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Movimento">
            {({ id }) => (
              <NativeSelect id={id} value={v.movimento ?? ""} onChange={(e) => onChange({ movimento: vazio(e.target.value) as CenaMovimento | null })}>
                <option value="">Não definido</option>
                {(Object.keys(movimentoLabel) as CenaMovimento[]).map((m) => (
                  <option key={m} value={m}>
                    {movimentoLabel[m]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </div>
        {decorar("camera", (botao) => (
          <Field label="Detalhe de câmera" action={botao} hint="Opcional, em inglês (ex.: eye level, shallow depth of field).">
            {({ id, describedBy }) => (
              <Input id={id} maxLength={LIM.camera} aria-describedby={describedBy} value={v.camera ?? ""} onChange={(e) => onChange({ camera: vazio(e.target.value) })} />
            )}
          </Field>
        ))}
        {decorar("estilo", (botao) => (
          <Field label="Iluminação e estilo" action={botao} hint="Vazio: o padrão das cenas do perfil.">
            {({ id, describedBy }) => (
              <Textarea
                id={id}
                rows={2}
                maxLength={LIM.estilo}
                aria-describedby={describedBy}
                placeholder={padroes?.estilo}
                value={v.estilo ?? ""}
                onChange={(e) => onChange({ estilo: vazio(e.target.value) })}
              />
            )}
          </Field>
        ))}
        {decorar("audio", (botao) => (
          <Field label="Áudio e ambiente" action={botao} hint="Em inglês; a fala é o campo acima.">
            {({ id, describedBy }) => (
              <Input id={id} maxLength={LIM.audio} aria-describedby={describedBy} value={v.audio ?? ""} onChange={(e) => onChange({ audio: vazio(e.target.value) })} />
            )}
          </Field>
        ))}
      </fieldset>

      <fieldset className="space-y-4" disabled={travado}>
        <legend className="text-sm font-semibold">Flow</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Modo do Flow">
            {({ id }) => (
              <NativeSelect id={id} value={v.modo} onChange={(e) => onChange({ modo: e.target.value as CenaModo })}>
                {(Object.keys(modoCenaLabel) as CenaModo[]).map((m) => (
                  <option key={m} value={m}>
                    {modoCenaLabel[m]}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field label="Duração" hint={v.modo === "ingredientes" && v.duracaoS !== 8 ? "Com ingredientes, o Flow gera 8 s." : undefined}>
            {({ id, describedBy }) => (
              <NativeSelect id={id} aria-describedby={describedBy} value={String(v.duracaoS)} onChange={(e) => onChange({ duracaoS: Number(e.target.value) as Duracao })}>
                {DURACOES.map((d) => (
                  <option key={d} value={d}>
                    {d} s
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
        </div>
        {v.modo === "quadros" && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Quadro inicial" hint="Obrigatório para marcar como pronta.">
              {({ id, describedBy }) => (
                <Textarea id={id} rows={2} maxLength={LIM.quadro} aria-describedby={describedBy} value={v.quadroInicial ?? ""} onChange={(e) => onChange({ quadroInicial: vazio(e.target.value) })} />
              )}
            </Field>
            <Field label="Quadro final" hint="Obrigatório para marcar como pronta.">
              {({ id, describedBy }) => (
                <Textarea id={id} rows={2} maxLength={LIM.quadro} aria-describedby={describedBy} value={v.quadroFinal ?? ""} onChange={(e) => onChange({ quadroFinal: vazio(e.target.value) })} />
              )}
            </Field>
          </div>
        )}
        <Field label="Negative prompt" hint="Vazio: o padrão das cenas do perfil.">
          {({ id, describedBy }) => (
            <Textarea
              id={id}
              rows={2}
              maxLength={LIM.negative}
              aria-describedby={describedBy}
              placeholder={padroes?.negative}
              value={v.negative ?? ""}
              onChange={(e) => onChange({ negative: vazio(e.target.value) })}
            />
          )}
        </Field>
      </fieldset>

      <fieldset className="space-y-4" disabled={travado}>
        <legend className="text-sm font-semibold">Produto em cena</legend>
        <Field label="Produto" hint="Nome curto (o catálogo de produtos vem depois).">
          {({ id, describedBy }) => (
            <Input
              id={id}
              maxLength={LIM.produtoNome}
              aria-describedby={describedBy}
              value={v.produtoNome ?? ""}
              onChange={(e) => onChange({ produtoNome: vazio(e.target.value) })}
            />
          )}
        </Field>
        <div className="flex flex-wrap items-center gap-3" role="group" aria-label="Foto do produto">
          {foto ? (
            <span className="flex min-w-0 items-center gap-2 text-sm">
              {foto.thumb && <img src={foto.thumb} alt="" className="size-10 rounded border object-cover" />}
              <span className="truncate" data-testid="produto-foto">
                Foto: {foto.nome}
              </span>
              {!travado && (
                <Button type="button" size="sm" variant="ghost" aria-label="Tirar a foto do produto" onClick={() => onChange({ produtoImagemId: null })}>
                  <X aria-hidden="true" />
                </Button>
              )}
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">Sem foto do produto.</span>
          )}
          {!travado && (
            <LibraryImageDialog
              perfilId={perfilId}
              tipos={["imagem"]}
              value={null}
              onPick={(image, item) => {
                setFoto({ id: item.assetId, nome: item.label ? `${item.assetName}: ${item.label}` : item.assetName, thumb: image.urls.thumb });
                onChange({ produtoImagemId: item.assetId, produtoNome: v.produtoNome ?? item.assetName.slice(0, LIM.produtoNome) });
              }}
            />
          )}
        </div>
      </fieldset>

      <fieldset className="space-y-4" disabled={disabled}>
        <legend className="text-sm font-semibold">Organização</legend>
        <Field label="Tags" hint="Separadas por vírgula.">
          {({ id, describedBy }) => (
            <Input
              id={id}
              aria-describedby={describedBy}
              value={tagsTexto}
              onChange={(e) => {
                setTagsTexto(e.target.value);
                onChange({ tags: parseTags(e.target.value).slice(0, LIM.tags) });
              }}
            />
          )}
        </Field>
        <Field label="Notas" hint={`${v.notas.length}/${LIM.notas}`}>
          {({ id, describedBy }) => (
            <Textarea id={id} rows={3} maxLength={LIM.notas} aria-describedby={describedBy} value={v.notas} onChange={(e) => onChange({ notas: e.target.value })} />
          )}
        </Field>
      </fieldset>
    </div>
  );
}
