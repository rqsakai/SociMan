import { FolderInput, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Andamento } from "@/components/importacao/Andamento";
import { ListaImportacoes } from "@/components/importacao/ListaImportacoes";
import { PreviaTabela } from "@/components/importacao/PreviaTabela";
import { usePageMeta } from "@/components/shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/authStore";
import {
  escolhasParaEnviar,
  formatMB,
  importacaoPath,
  personaSemPerfil,
  resumoConfirmacao,
  useAgenciaMutations,
  useEstadoAgencia,
  useImportacaoAgencia,
  useImportacoesAgencia,
  useInvalidarAgencia,
  type Escolha,
  type Estado,
  type Previa,
} from "@/lib/importacao";
import { formatDateTime } from "@/lib/tz";

// /app/configuracoes/importacao (spec 013): importar a pasta da agência (`shared/` e os clipes).
// 1. Estado da pasta (todos); 2. "Ler a pasta" → prévia com as escolhas → confirmar (só dono);
// 3. andamento da gravação de fundo; 4. importações (todos), com o detalhe e o desfazer.
export default function ImportacaoAgencia() {
  usePageMeta({ title: "Importar da agência" });
  const ehDono = useAuth((s) => s.user?.role === "dono");
  const estado = useEstadoAgencia();
  const lista = useImportacoesAgencia();
  const mut = useAgenciaMutations();
  const invalidar = useInvalidarAgencia();
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [escolhas, setEscolhas] = useState<Record<number, Escolha>>({});
  const [personaPerfil, setPersonaPerfil] = useState("");
  const [confirmadaId, setConfirmadaId] = useState<string | null>(null);
  const andamentoId = confirmadaId ?? estado.data?.emAndamento?.id ?? null;
  const andamento = useImportacaoAgencia(andamentoId);
  const estadoAndamento = andamento.data?.estado;

  // A gravação de fundo terminou: o estado da pasta e a lista mudam.
  useEffect(() => {
    if (estadoAndamento && estadoAndamento !== "processando") void invalidar();
  }, [estadoAndamento]);

  const mudar = useCallback((n: number, e: Escolha) => setEscolhas((atual) => ({ ...atual, [n]: { ...atual[n], ...e } })), []);

  function descartar() {
    setPrevia(null);
    setEscolhas({});
    setPersonaPerfil("");
    mut.previa.reset();
    mut.confirmar.reset();
  }

  function ler() {
    mut.confirmar.reset();
    mut.previa.mutate(undefined, {
      onSuccess: (p) => {
        setEscolhas({});
        setPersonaPerfil("");
        setPrevia(p);
      },
    });
  }

  async function confirmar() {
    if (!previa) return;
    try {
      const imp = await mut.confirmar.mutateAsync({
        previaId: previa.previaId,
        escolhas: escolhasParaEnviar(previa.itens, escolhas),
        ...(personaPerfil ? { personaPerfil } : {}),
      });
      setConfirmadaId(imp.id);
      setPrevia(null);
      setEscolhas({});
      toast.success("Importação confirmada. A gravação continua em segundo plano.");
    } catch {
      // a prévia expirada ou já usada aparece no erro; "Ler a pasta" de novo gera outra
    }
  }

  const emAndamento = estadoAndamento === "processando" || Boolean(estado.data?.emAndamento);
  const sharedDisponivel = estado.data?.raizes.shared.disponivel ?? false;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-lg font-semibold">Importar da agência</h1>
        <p className="text-sm text-muted-foreground">
          Traz para o SociMan os perfis, contas, canais-fonte, imagens, guias, anotações e clipes que os agentes guardam em markdown. Primeiro você vê o que seria
          gravado; nada entra antes de confirmar, e o que já foi editado no SociMan só muda se você escolher. A pasta da agência nunca é alterada.
        </p>
      </div>

      <Card className="shadow-card" role="region" aria-labelledby="importacao-pasta">
        <CardHeader>
          <CardTitle>
            <h2 id="importacao-pasta">Pasta da agência</h2>
          </CardTitle>
          <CardDescription>{ehDono ? "Leia a pasta para ver a prévia." : "Só o dono lê a pasta e confirma a importação."}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {estado.isError ? (
            <ApiErrorAlert error={estado.error} />
          ) : estado.isPending ? (
            <Skeleton className="h-20 w-full" />
          ) : (
            <EstadoPasta estado={estado.data} />
          )}
          {mut.previa.error ? <ApiErrorAlert error={mut.previa.error} /> : null}
          {ehDono && !previa && (
            <Button type="button" onClick={ler} disabled={mut.previa.isPending || emAndamento || !sharedDisponivel} aria-busy={mut.previa.isPending}>
              {mut.previa.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <FolderInput aria-hidden="true" />}
              Ler a pasta da agência
            </Button>
          )}
          {ehDono && !previa && emAndamento && <p className="text-xs text-muted-foreground">Há uma importação em andamento. Espere terminar para ler de novo.</p>}
        </CardContent>
      </Card>

      {previa && (
        <Card className="shadow-card" role="region" aria-labelledby="importacao-previa" data-previa={previa.previaId}>
          <CardHeader>
            <CardTitle>
              <h2 id="importacao-previa">Pré-visualização</h2>
            </CardTitle>
            <CardDescription>
              Nada foi gravado. <Expira em={previa.expiraEm} />
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <PreviaTabela previa={previa} escolhas={escolhas} onEscolha={mudar} podeEscolher={ehDono} personaPerfil={personaPerfil} onPersonaPerfil={setPersonaPerfil} />
            {mut.confirmar.error ? <ApiErrorAlert error={mut.confirmar.error} /> : null}
            <div className="flex flex-wrap gap-2">
              <ConfirmarImportacao previa={previa} escolhas={escolhas} personaPerfil={personaPerfil} busy={mut.confirmar.isPending} onConfirm={confirmar} />
              <Button type="button" variant="ghost" onClick={descartar} disabled={mut.confirmar.isPending}>
                Descartar a leitura
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {andamentoId && (
        <Card className="shadow-card" role="region" aria-labelledby="importacao-andamento">
          <CardHeader>
            <CardTitle>
              <h2 id="importacao-andamento">{estadoAndamento === "processando" ? "Gravando a importação" : "Última importação"}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {andamento.isError ? (
              <ApiErrorAlert error={andamento.error} />
            ) : andamento.isPending ? (
              <Skeleton className="h-12 w-full" />
            ) : (
              <>
                <Andamento imp={andamento.data} />
                <Link to={importacaoPath(andamento.data.id)} className="inline-block text-sm text-primary underline-offset-2 hover:underline">
                  Ver os itens desta importação
                </Link>
              </>
            )}
          </CardContent>
        </Card>
      )}

      <Card className="shadow-card" role="region" aria-labelledby="importacao-lista">
        <CardHeader>
          <CardTitle>
            <h2 id="importacao-lista">Importações</h2>
          </CardTitle>
          <CardDescription>Quem importou, quando e o resultado. Desfazer fica no detalhe de cada uma.</CardDescription>
        </CardHeader>
        <CardContent>
          {lista.isError ? <ApiErrorAlert error={lista.error} /> : lista.isPending ? <Skeleton className="h-24 w-full" /> : <ListaImportacoes importacoes={lista.data.items} />}
        </CardContent>
      </Card>
    </div>
  );
}

function EstadoPasta({ estado }: { estado: Estado }) {
  const raizes: [keyof Estado["raizes"], string][] = [
    ["shared", "Pasta shared/"],
    ["clipes", "Clipes prontos"],
  ];
  return (
    <div className="space-y-3 text-sm" data-estado-pasta>
      <ul className="space-y-1">
        {raizes.map(([chave, rotulo]) => {
          const r = estado.raizes[chave];
          return (
            <li key={chave} className="flex flex-wrap items-center gap-2" data-raiz={chave} data-disponivel={r.disponivel}>
              <span className="font-medium">{rotulo}</span>
              {r.disponivel ? <Badge className="bg-success text-success-foreground">disponível</Badge> : <Badge variant="destructive">indisponível</Badge>}
              {!r.disponivel && r.motivo && <span className="text-xs text-muted-foreground">{r.motivo}</span>}
            </li>
          );
        })}
      </ul>
      {!estado.raizes.shared.disponivel && (
        <Alert variant="destructive">
          <AlertTitle>A pasta da agência não está disponível</AlertTitle>
          <AlertDescription>Confira a montagem da pasta no servidor e tente de novo.</AlertDescription>
        </Alert>
      )}
      {estado.ultima ? (
        <p className="text-muted-foreground">
          Última importação: <Link to={importacaoPath(estado.ultima.id)} className="text-primary underline-offset-2 hover:underline">{formatDateTime(estado.ultima.criadaEm)}</Link>{" "}
          por {estado.ultima.criadaPor?.name ?? "—"}
        </p>
      ) : (
        <p className="text-muted-foreground">Nenhuma importação ainda.</p>
      )}
      {estado.perfis.length > 0 && (
        <ul className="space-y-1" aria-label="Perfis importados">
          {estado.perfis.map((p) => (
            <li key={p.slug} className="flex flex-wrap items-center gap-2" data-perfil={p.slug}>
              <span className="font-medium">{p.slug}</span>
              {p.ultimaImportacaoEm && <span className="text-xs text-muted-foreground">importado em {formatDateTime(p.ultimaImportacaoEm)}</span>}
              {p.arquivosMudaram && <Badge className="bg-info text-info-foreground">arquivos mudaram desde então</Badge>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// "Expira em 29 min" (a prévia vale 30 min e é de uso único).
function Expira({ em }: { em: string }) {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setAgora(Date.now()), 15_000);
    return () => window.clearInterval(t);
  }, []);
  const min = Math.ceil((new Date(em).getTime() - agora) / 60_000);
  if (min <= 0) return <span className="font-medium text-destructive">A leitura expirou: leia a pasta de novo.</span>;
  return <span data-expira={em}>Vale por mais {min} min ({formatDateTime(em)}).</span>;
}

function ConfirmarImportacao({
  previa,
  escolhas,
  personaPerfil,
  busy,
  onConfirm,
}: {
  previa: Previa;
  escolhas: Record<number, Escolha>;
  personaPerfil: string;
  busy: boolean;
  onConfirm: () => Promise<void>;
}) {
  const r = resumoConfirmacao(previa.itens, escolhas);
  const nada = (r.criar === 0 && r.trocar === 0) || personaSemPerfil(previa, escolhas, personaPerfil);
  return (
    <ConfirmButton
      label="Confirmar importação"
      variant="outline"
      busy={busy}
      disabled={nada}
      title="Confirmar a importação?"
      description={
        <>
          Vão ser criados {r.criar} {r.criar === 1 ? "item" : "itens"} e trocados {r.trocar} pelo markdown
          {r.bytes > 0 ? `, com ${formatMB(r.bytes)} de arquivos no HD` : ""}. O resto fica como está. Tudo vai para o histórico, com você como autor; dá para desfazer
          depois.
        </>
      }
      onConfirm={onConfirm}
    />
  );
}
