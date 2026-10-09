import type { ConsentimentoRequest, ImageRef } from "@sociman/contract";
import { Loader2, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { LibraryImageDialog } from "@/components/assets/LibraryImageDialog";
import { PlayerAudio } from "@/components/geracao/PlayerAudio";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DateField } from "@/components/ui/date-field";
import { Field, NativeSelect } from "@/components/ui/field";
import { FileField } from "@/components/ui/file-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/authStore";
import { geracoesApi } from "@/lib/geracoes";
import type { ConsentimentoPessoa, PreviaRevogacao } from "@/lib/padrao";
import { formatDate, formatDateTime } from "@/lib/tz";
import { AUDIO_ACCEPT } from "@/lib/vozes";
import { RevogarDialog } from "./RevogarDialog";

type Prova = "nenhuma" | "imagem" | "audio";

// "Origem e consentimento" (spec 025, US3, T036; FR-033/033a): o registro do consentimento da pessoa
// real (nome, data, observação e a prova opcional, por imagem da biblioteca ou por áudio), com o
// aviso de menores e famosos; o estado "Revogado"; e "Revogar consentimento", só para o dono. Serve
// ao avatar e à voz de gravação (a voz não tem prévia da revogação).
export function ConsentimentoCard({
  perfilId,
  consentimento,
  revogado,
  bloqueado,
  descricao,
  oQue,
  onRegistrar,
  carregarPrevia,
  onRevogar,
  children,
}: {
  perfilId: string | null;
  consentimento: ConsentimentoPessoa | null | undefined;
  revogado: boolean;
  // não aceita registro (ex.: avatar com origem upload ou sintético)
  bloqueado?: string | null;
  descricao: string;
  // "a foto" | "a gravação"
  oQue: string;
  onRegistrar: (body: Omit<ConsentimentoRequest, "version">) => Promise<void>;
  carregarPrevia?: () => Promise<PreviaRevogacao>;
  onRevogar: () => Promise<void>;
  children?: ReactNode;
}) {
  const isOwner = useAuth((s) => s.user?.role === "dono");
  const [editando, setEditando] = useState(false);
  const registrado = Boolean(consentimento?.registradoEm);

  return (
    <Card className="shadow-card" aria-labelledby="consentimento-titulo" data-testid="consentimento-card">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <h2 id="consentimento-titulo">Origem e consentimento</h2>
          {revogado ? (
            <Badge className="bg-dark text-dark-foreground" data-testid="consentimento-revogado">
              Revogado
            </Badge>
          ) : registrado ? (
            <Badge className="bg-success text-success-foreground" data-testid="consentimento-registrado">
              <ShieldCheck aria-hidden="true" />
              Consentimento registrado
            </Badge>
          ) : null}
        </CardTitle>
        <CardDescription>{descricao}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {children}
        {revogado && (
          <Alert>
            <ShieldAlert aria-hidden="true" />
            <AlertTitle>Consentimento revogado</AlertTitle>
            <AlertDescription>
              As imagens e áudios da pessoa foram apagados. Este item não pode ser usado nem restaurado.
              {consentimento?.revogadoEm && ` Revogado em ${formatDateTime(consentimento.revogadoEm)}${consentimento.revogadoPor ? ` por ${consentimento.revogadoPor.name}` : ""}.`}
            </AlertDescription>
          </Alert>
        )}

        {registrado && consentimento && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm" data-testid="consentimento-dados">
            <dt className="text-muted-foreground">Pessoa</dt>
            <dd>{consentimento.nome ?? "—"}</dd>
            <dt className="text-muted-foreground">Data</dt>
            <dd>{consentimento.data ? formatDate(`${consentimento.data}T12:00:00`) : "—"}</dd>
            {consentimento.observacao && (
              <>
                <dt className="text-muted-foreground">Observação</dt>
                <dd className="whitespace-pre-wrap">{consentimento.observacao}</dd>
              </>
            )}
            <dt className="text-muted-foreground">Registrado por</dt>
            <dd>
              {consentimento.registradoPor?.name ?? "—"}
              {consentimento.registradoEm && ` em ${formatDateTime(consentimento.registradoEm)}`}
            </dd>
            <dt className="text-muted-foreground">Prova</dt>
            <dd>
              {consentimento.prova?.link ? (
                <a href={consentimento.prova.link} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">
                  Ver imagem
                </a>
              ) : consentimento.prova?.audio ? (
                <PlayerAudio audio={consentimento.prova.audio} rotulo="Áudio da prova" onRenovar={() => undefined} />
              ) : consentimento.temProva ? (
                "Guardada"
              ) : (
                "Sem prova"
              )}
            </dd>
          </dl>
        )}

        {!revogado && bloqueado && <p className="text-sm text-muted-foreground">{bloqueado}</p>}

        {!revogado && !bloqueado && (registrado && !editando ? (
          <Button type="button" variant="outline" size="sm" onClick={() => setEditando(true)}>
            Atualizar consentimento
          </Button>
        ) : (
          <FormConsentimento
            perfilId={perfilId}
            atual={consentimento}
            oQue={oQue}
            onCancelar={registrado ? () => setEditando(false) : undefined}
            onRegistrar={async (body) => {
              await onRegistrar(body);
              setEditando(false);
            }}
          />
        ))}

        {isOwner && registrado && !revogado && <RevogarDialog carregarPrevia={carregarPrevia} onRevogar={onRevogar} />}
      </CardContent>
    </Card>
  );
}

function hoje(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function FormConsentimento({
  perfilId,
  atual,
  oQue,
  onCancelar,
  onRegistrar,
}: {
  perfilId: string | null;
  atual: ConsentimentoPessoa | null | undefined;
  oQue: string;
  onCancelar?: () => void;
  onRegistrar: (body: Omit<ConsentimentoRequest, "version">) => Promise<void>;
}) {
  const [nome, setNome] = useState(atual?.nome ?? "");
  const [data, setData] = useState(atual?.data ?? hoje());
  const [observacao, setObservacao] = useState(atual?.observacao ?? "");
  const [tipoProva, setTipoProva] = useState<Prova>("nenhuma");
  const [imagem, setImagem] = useState<{ image: ImageRef; nome: string } | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [erros, setErros] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!nome.trim()) errs.nome = "Informe o nome da pessoa";
    if (!data) errs.data = "Informe a data do consentimento";
    if (tipoProva === "imagem" && !imagem) errs.prova = "Escolha a imagem da prova";
    if (tipoProva === "audio" && !audio) errs.prova = "Escolha o áudio da prova";
    setErros(errs);
    if (Object.keys(errs).length > 0) return;
    setBusy(true);
    setError(null);
    try {
      let prova: ConsentimentoRequest["prova"] = null;
      if (tipoProva === "imagem" && imagem) prova = { imageId: imagem.image.id };
      if (tipoProva === "audio" && audio) prova = { audioId: (await geracoesApi.enviarAudio(perfilId, audio)).id };
      await onRegistrar({ nome: nome.trim(), data, observacao: observacao.trim(), ...(prova ? { prova } : {}) });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4" noValidate data-testid="consentimento-form">
      <Alert role="note">
        <ShieldAlert aria-hidden="true" />
        <AlertTitle>Antes de usar {oQue} de uma pessoa real</AlertTitle>
        <AlertDescription>
          Menores de idade e pessoas famosas não são permitidos. Registrar o consentimento é responsabilidade de quem registra: ele fica
          no histórico com o seu nome.
        </AlertDescription>
      </Alert>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome da pessoa" error={erros.nome}>
          {({ id, describedBy, invalid }) => (
            <Input id={id} value={nome} maxLength={120} aria-invalid={invalid} aria-describedby={describedBy} onChange={(e) => setNome(e.target.value)} />
          )}
        </Field>
        <Field label="Data do consentimento" error={erros.data}>
          {({ id, describedBy }) => <DateField id={id} value={data} aria-describedby={describedBy} onChange={setData} />}
        </Field>
      </div>
      <Field label="Observação" hint="Ex.: termo assinado, guardado na pasta da agência.">
        {({ id, describedBy }) => (
          <Textarea id={id} rows={2} value={observacao} maxLength={1000} aria-describedby={describedBy} onChange={(e) => setObservacao(e.target.value)} />
        )}
      </Field>
      <Field label="Prova (opcional)" error={erros.prova}>
        {({ id, describedBy }) => (
          <NativeSelect id={id} value={tipoProva} aria-describedby={describedBy} onChange={(e) => setTipoProva(e.target.value as Prova)}>
            <option value="nenhuma">Sem prova</option>
            <option value="imagem">Imagem (termo, foto do documento)</option>
            <option value="audio">Áudio (a pessoa autorizando)</option>
          </NativeSelect>
        )}
      </Field>
      {tipoProva === "imagem" && (
        <div className="flex flex-wrap items-center gap-3">
          {imagem ? (
            <span className="flex items-center gap-2 text-sm">
              <img src={imagem.image.urls.thumb} alt="" className="size-12 rounded border object-cover" />
              {imagem.nome}
              <Button type="button" variant="ghost" size="sm" aria-label="Tirar a imagem da prova" onClick={() => setImagem(null)}>
                <X aria-hidden="true" />
              </Button>
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">Envie a imagem como asset "Imagem" do perfil e escolha aqui.</span>
          )}
          <LibraryImageDialog perfilId={perfilId} tipos={["imagem"]} value={imagem?.image.id ?? null} onPick={(image, item) => setImagem({ image, nome: item.assetName })} />
        </div>
      )}
      {tipoProva === "audio" && (
        <Field label="Áudio da prova" hint="WAV, M4A, OGG ou MP3, até 25 MB.">
          {({ id, describedBy }) => <FileField id={id} accept={AUDIO_ACCEPT} aria-describedby={describedBy} onChange={(e) => setAudio(e.target.files?.[0] ?? null)} />}
        </Field>
      )}
      {error !== null && <ApiErrorAlert error={error} />}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy} aria-busy={busy}>
          {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
          Registrar consentimento
        </Button>
        {onCancelar && (
          <Button type="button" variant="ghost" disabled={busy} onClick={onCancelar}>
            Cancelar
          </Button>
        )}
      </div>
    </form>
  );
}
