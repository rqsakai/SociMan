import { ArrowLeft, Undo2 } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ApiErrorAlert } from "@/components/ApiErrorAlert";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Andamento } from "@/components/importacao/Andamento";
import { ItensImportacao } from "@/components/importacao/ItensImportacao";
import { usePageMeta } from "@/components/shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/authStore";
import { useAgenciaMutations, useImportacaoAgencia, type Importacao } from "@/lib/importacao";
import { formatDateTime } from "@/lib/tz";

const LISTA = "/app/configuracoes/importacao";

// /app/configuracoes/importacao/:id (spec 013, US7): andamento ou resultado, os itens e, para o
// dono, "Desfazer" (arquiva o que foi criado e reverte o que foi trocado, se ninguém mexeu depois).
export default function ImportacaoDetalhe() {
  const { id = "" } = useParams();
  const ehDono = useAuth((s) => s.user?.role === "dono");
  const q = useImportacaoAgencia(id);
  const mut = useAgenciaMutations();
  const imp = q.data;
  const title = imp ? `Importação de ${formatDateTime(imp.criadaEm)}` : "Importação";
  usePageMeta({ title, breadcrumbs: [{ label: "Importar da agência", to: LISTA }] });

  async function desfazer(i: Importacao) {
    try {
      await mut.desfazer.mutateAsync({ id: i.id, version: i.version });
      toast.success("Importação desfeita.");
    } catch {
      // o erro aparece acima dos itens (mut.desfazer.error)
    }
  }

  return (
    <div className="space-y-6">
      <Link to={LISTA} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden="true" />
        Importar da agência
      </Link>
      <h1 className="text-lg font-semibold">{title}</h1>
      {q.isError ? (
        <ApiErrorAlert error={q.error} />
      ) : q.isPending || !imp ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <>
          <Card className="shadow-card" role="region" aria-labelledby="importacao-resultado">
            <CardHeader>
              <CardTitle>
                <h2 id="importacao-resultado">Resultado</h2>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Andamento imp={imp} />
              {mut.desfazer.error ? <ApiErrorAlert error={mut.desfazer.error} onReload={() => void q.refetch()} /> : null}
              {ehDono && imp.estado === "concluida" && <Desfazer imp={imp} busy={mut.desfazer.isPending} onConfirm={() => desfazer(imp)} />}
            </CardContent>
          </Card>

          <Card className="shadow-card" role="region" aria-labelledby="importacao-itens">
            <CardHeader>
              <CardTitle>
                <h2 id="importacao-itens">Itens</h2>
              </CardTitle>
              <CardDescription>Tudo o que a leitura encontrou, com a escolha e o resultado de cada item.</CardDescription>
            </CardHeader>
            <CardContent>
              <ItensImportacao itens={imp.itens} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function Desfazer({ imp, busy, onConfirm }: { imp: Importacao; busy: boolean; onConfirm: () => Promise<void> }) {
  const criados = imp.itens.filter((i) => i.resultado === "criado" && !i.desfeitoEm).length;
  const trocados = imp.itens.filter((i) => i.resultado === "atualizado" && !i.desfeitoEm).length;
  return (
    <ConfirmButton
      label="Desfazer importação"
      icon={Undo2}
      busy={busy}
      title="Desfazer esta importação?"
      description={
        <>
          {criados} {criados === 1 ? "item criado vai ser arquivado" : "itens criados vão ser arquivados"} e {trocados}{" "}
          {trocados === 1 ? "item trocado volta" : "itens trocados voltam"} à versão anterior. O que foi editado ou usado depois fica como está, com o motivo. Nada é
          apagado: imagens e vídeos continuam no HD.
        </>
      }
      onConfirm={onConfirm}
    />
  );
}
