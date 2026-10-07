"""Mapa explícito das operações do OpenAPI para o MCP (R2, FR-009/FR-010).

Toda operação de `app.openapi()` fica em exatamente uma lista:

- `TOOLS`: vira tool (escopo `leitura` ou `propostas`). Nome, parâmetros e schemas vêm do
  OpenAPI; o mapa só acrescenta título e descrição em pt-BR, o escopo, a paginação padrão e os
  campos que o agente não pode mandar (`ocultar`);
- `FORA`: não vira tool (upload, `deprecated`, infra, escritas fora do primeiro corte, IA paga e
  dados de dono). O portão responde `escopo_mcp`;
- `PROIBIDAS`: atos humanos (FR-024). O portão responde `somente_humano` + evento.

`tests/unit/test_mcp_mapa.py` falha com operação sem classificação, id inexistente, PROIBIDA
como tool, rota `RequireHumanOwner`/`RequireHuman` fora de `PROIBIDAS` ou escrita em `leitura`.
Rota nova da API nunca vira tool sozinha.
"""

from dataclasses import dataclass
from typing import Literal

Escopo = Literal["leitura", "propostas"]


@dataclass(frozen=True)
class Tool:
    titulo: str
    descricao: str  # pt-BR, para o agente (FR-012)
    escopo: Escopo = "leitura"
    escrita: bool = False
    limite_padrao: int | None = None  # listas: `limit`/`limite` quando o agente não manda
    entidade: str | None = None  # escritas: o tipo do item alterado (registro, R8)
    ocultar: tuple[str, ...] = ()  # campos do corpo/query fora do alcance do agente


def _l(titulo: str, descricao: str, limite_padrao: int | None = None,
       ocultar: tuple[str, ...] = ()) -> Tool:
    return Tool(titulo, descricao, limite_padrao=limite_padrao, ocultar=ocultar)


def _versoes(item: str) -> Tool:
    return _l(f"Histórico de {item}",
              f"Histórico de versões de {item}: autor (usuário, agente ou sistema), data, campos "
              "alterados, antes e depois. Da versão mais recente para a mais antiga.")


_FILTROS_ANALYTICS = ("Filtros opcionais: período (`de`, `ate`), perfil, conta, rede e medida. "
                      "Os números são os mesmos da tela de analytics para um membro.")

TOOLS: dict[str, Tool] = {
    # ---- perfis e contas ----
    "perfis_list": _l("Listar perfis", "Lista os perfis da agência (nicho, idioma, situação e "
                      "redes das contas ativas). Filtre por texto (`q`), situação ou arquivados."),
    "perfis_get": _l("Ver perfil", "Detalhe de um perfil com todas as suas contas (inclusive as "
                     "arquivadas, marcadas), modos e intervalo mínimo entre posts."),
    "perfis_versions": _versoes("um perfil"),
    "contas_modos": _l("Modos de publicação da conta", "Modos disponíveis para uma conta "
                       "(lembrete, rascunho, publicar) e por que algum está indisponível. Só "
                       "informa: agendar e publicar são atos do dono."),
    "contas_versions": _versoes("uma conta"),
    # ---- kit, padrões, guia ----
    "kit_get": _l("Ver kit de marca", "Kit de marca do perfil em tokens (paleta, fontes, "
                  "legenda, cartão de gancho, marca d'água, bordões e séries)."),
    "kit_export": _l("Exportar kit de marca", "Kit de marca do perfil no formato aplicável por "
                     "máquina (o mesmo que vai para o gerador de cortes), como JSON.",
                     ocultar=("download",)),
    "kit_versions": _versoes("o kit de marca"),
    "envios_padroes_get": _l("Ver padrões de corte", "Padrões de corte do perfil (duração, "
                             "quantidade, idioma e estilo) usados ao gerar cortes."),
    "envios_padroes_versions": _versoes("os padrões de corte"),
    "guias_perfil_get": _l("Ver guia de comunicação do perfil", "Guia de comunicação do perfil: "
                           "tom, faça e não faça, vocabulário, palavras proibidas, emojis, "
                           "hashtags fixas e exemplos. Use ao propor textos."),
    "guias_perfil_versions": _versoes("o guia de comunicação do perfil"),
    "guias_conta_get": _l("Ver guia de comunicação da conta", "Guia de comunicação específico "
                          "de uma conta, que se soma ao do perfil (hashtags fixas, proibidas)."),
    "guias_conta_versions": _versoes("o guia de comunicação da conta"),
    # ---- assets e fontes ----
    "assets_list": _l("Listar assets", "Biblioteca de assets do perfil (avatares, cenários, "
                      "fundos, stickers, marcas d'água e imagens), com filtros e paginação "
                      "(`cursor`).", limite_padrao=50),
    "assets_get": _l("Ver asset", "Detalhe de um asset com os arquivos, descrições e onde é "
                     "usado. Imagens vêm como link, nunca embutidas."),
    "assets_images": _l("Listar imagens por tipo", "Imagens do perfil de um tipo (para fundo ou "
                        "marca d'água), com busca por texto.", limite_padrao=50),
    "assets_versions": _versoes("um asset"),
    "fontes_list": _l("Listar fontes do perfil", "Fontes tipográficas enviadas para o perfil, "
                      "usadas pelo kit de marca."),
    "fontes_padrao_list": _l("Listar fontes padrão", "Fontes padrão disponíveis para todos os "
                             "perfis."),
    "fontes_versions": _versoes("uma fonte"),
    # ---- canais, vídeos-fonte, envios e cortes ----
    "canais_list": _l("Listar canais-fonte", "Canais-fonte (de onde saem os cortes) com o status "
                      "informativo de direito, os perfis ligados e a sincronização."),
    "canais_get": _l("Ver canal-fonte", "Detalhe de um canal-fonte, com o status de direito "
                     "(informativo; só o dono muda) e as estatísticas."),
    "canais_versions": _versoes("um canal-fonte"),
    "videos_fonte_list": _l("Listar vídeos-fonte", "Vídeos dos canais-fonte com pontuação, "
                            "duração e se já têm envio para corte (`naoCortados`). Paginação por "
                            "`cursor`.", limite_padrao=50),
    "videos_fonte_get": _l("Ver vídeo-fonte", "Detalhe de um vídeo-fonte, com métricas e envios "
                           "que já existem para ele."),
    "envios_list": _l("Listar envios para corte", "Envios para o gerador de cortes do perfil "
                      "(selecionado, enviado, processando, pronto, falhou), mais novos primeiro; "
                      "use `before` para a próxima página.", limite_padrao=50),
    "envios_get": _l("Ver envio", "Detalhe de um envio para corte: vídeo, padrões, progresso e "
                     "cortes gerados."),
    "envios_versions": _versoes("um envio"),
    "cortes_list": _l("Listar cortes", "Cortes do perfil (gerados ou enviados), com status e "
                      "origem; use `before` para a próxima página.", limite_padrao=50),
    "cortes_get": _l("Ver corte", "Detalhe de um corte: duração, gancho, status e links. Vídeos "
                     "só por link assinado (`midia_links`)."),
    "cortes_versions": _versoes("um corte"),
    # ---- conteúdos, destinos e calendário ----
    "conteudos_list": _l("Listar conteúdos", "Central de conteúdos com o estado efetivo de cada "
                         "destino (a_postar, atrasado, em_revisao…), igual à tela Conteúdos. "
                         "Paginação por `cursor`.", limite_padrao=50),
    "conteudos_resumo": _l("Resumo dos conteúdos", "Contagem de conteúdos por estado efetivo, "
                           "com filtro opcional por perfil e conta."),
    "conteudos_get": _l("Ver conteúdo", "Detalhe de um conteúdo com todos os destinos (conta, "
                        "estado efetivo, textos e agendamento)."),
    "conteudos_versions": _versoes("um conteúdo"),
    "destinos_get": _l("Ver destino", "Detalhe de um destino (conteúdo × conta): estado, textos "
                       "(título, descrição, hashtags), aprovação e agendamento."),
    "destinos_tentativas": _l("Tentativas de envio do destino", "Tentativas de envio "
                              "automático de um destino, com resultado e erro."),
    "destinos_vinculo_get": _l("Vínculo do destino com o post", "Post da rede ligado ao "
                               "destino (ou os candidatos), usado pelas métricas."),
    "destinos_metricas": _l("Métricas do destino", "Métricas do post ligado ao destino "
                            "(views, curtidas, comentários) ao longo do tempo."),
    "destinos_versions": _versoes("um destino"),
    "postagens_calendario": _l("Calendário de postagens", "Destinos agendados e postados entre "
                               "`de` e `ate`, com filtros por perfil, plataforma e conta."),
    # ---- métricas e analytics ----
    "metricas_videos_list": _l("Listar vídeos com métricas", "Vídeos publicados com as métricas "
                               "mais recentes, com filtros, ordem e paginação (`cursor`, "
                               "`limite`).", limite_padrao=50),
    "metricas_videos_get": _l("Ver métricas de um vídeo", "Série de métricas de um vídeo "
                              "publicado e o destino ligado a ele."),
    "metricas_conta": _l("Métricas da conta", "Seguidores, curtidas e vídeos de uma conta ao "
                         "longo do tempo (`de`, `ate`, `resolucao`)."),
    "analytics_visao_geral": _l("Analytics: visão geral", "Visão geral do desempenho (views, "
                                "engajamento, tendência). " + _FILTROS_ANALYTICS),
    "analytics_quando_postar": _l("Analytics: quando postar", "Melhores dias e horários para "
                                  "postar, pelo desempenho real. " + _FILTROS_ANALYTICS),
    "analytics_o_que_funciona": _l("Analytics: o que funciona", "Características dos vídeos que "
                                   "performam melhor (duração, origem, gancho, série). "
                                   + _FILTROS_ANALYTICS),
    "analytics_curvas": _l("Analytics: curvas de crescimento", "Curvas de views por idade do "
                           "vídeo, comparadas à média. " + _FILTROS_ANALYTICS),
    "analytics_contas": _l("Analytics: contas", "Comparação entre as contas (crescimento, "
                           "engajamento, ritmo de posts). " + _FILTROS_ANALYTICS),
    "analytics_funil": _l("Analytics: funil", "Funil do vídeo-fonte até o post e o desempenho. "
                          "O custo de IA vem nulo (dado de dono). " + _FILTROS_ANALYTICS),
    "analytics_mercado": _l("Analytics: mercado", "Desempenho dos canais-fonte e do nicho, para "
                            "achar oportunidades. " + _FILTROS_ANALYTICS),
    "analytics_alertas": _l("Analytics: alertas", "Alertas de desempenho (quedas, picos, contas "
                            "paradas). " + _FILTROS_ANALYTICS),
    "analytics_ordem_contas": _l("Analytics: ordem das contas", "Todas as contas na ordem "
                                 "estável usada pelas cores dos gráficos."),
    "analytics_publico": _l("Analytics: público", "Público de cada conta importado do TikTok "
                            "Studio: gênero e territórios dos seguidores (foto datada), "
                            "atividade por dia e hora e espectadores por dia. "
                            + _FILTROS_ANALYTICS),  # spec 022
    # ---- aprendizado (spec 023): só leitura ----
    "aprendizado_temas_list": _l("Aprendizado: temas do perfil", "A taxonomia de temas do "
                                 "perfil (nome, descrição, palavras-chave, posts por tema)."),
    "aprendizado_classificacoes_list": _l(
        "Aprendizado: classificações", "Tema, estilo do gancho e origem (IA ou dono) de cada "
        "post do perfil; filtre por conta, tema, origem ou pendentes.", limite_padrao=50),
    "aprendizado_analise": _l("Aprendizado: análise", "Efeitos por fator (tema, gancho, "
                              "duração, horário, hashtag) na entrega e no rendimento, com n, "
                              "intervalo, confiança e avisos. Exploratório."),
    "aprendizado_recomendacoes": _l("Aprendizado: recomendações", "Recomendações abertas por "
                                    "regra e as decisões do dono. Só informa: decidir é do "
                                    "dono."),
    "aprendizado_preferencias_get": _l("Aprendizado: preferências", "Preferências aceitas pelo "
                                       "dono (temas a ampliar ou cortar, hashtags a evitar, "
                                       "padrões) do perfil e da conta."),
    "aprendizado_diagnostico": _l("Aprendizado: diagnóstico", "Sinais de distribuição por conta "
                                  "e por post (conta nova, muitos no dia, repostagem…) e o "
                                  "checklist do que conferir no app."),
    "aprendizado_post_diagnostico": _l("Aprendizado: diagnóstico do post", "Sinais de um post, "
                                       "se está estagnado e as conferências do dono."),
    # ---- apoio ----
    "ia_tipos_list": _l("Tipos de campo do assistente", "Tipos de campo que o assistente de IA "
                        "sabe preencher e as regras de cada um (útil para propor textos)."),
    "ia_tipos_get": _l("Ver tipo de campo do assistente", "Regras de um tipo de campo do "
                       "assistente de IA (limites e instruções)."),
    "midia_links": _l("Links de mídia", "Gera links assinados e com validade para vídeos, "
                      "imagens e fontes. Nada é embutido na resposta; não altera nada."),
    "armazenamento_get": _l("Armazenamento", "Situação do HD de dados (espaço livre e se está "
                            "disponível)."),
    "integracoes_get": _l("Integrações", "Quais integrações estão configuradas (sem nenhum valor "
                          "de chave)."),
    # ---- cenas (spec 010) ----
    "cenas_list": _l("Listar cenas", "Cenas do perfil para o Flow/Veo (tomadas de até 8 s), "
                     "com status (rascunho, pronta, usada), filtros por avatar, cenário, foto do "
                     "produto, tag e busca (`q`), e paginação (`cursor`).", limite_padrao=50),
    "cenas_get": _l("Ver cena", "Detalhe de uma cena: campos, prompt montado em inglês (ao vivo "
                    "em rascunho, congelado em pronta/usada), negative prompt, ingredientes "
                    "(imagens por link), avisos e onde foi usada. Para propor mudanças, grave "
                    "uma `proposta_cena` com `anotacoes_create`."),
    "cenas_versions": _versoes("uma cena"),
    "cenas_tomadas_list": _l("Listar tomadas da cena", "Tomadas (vídeos gerados no Flow) de uma "
                             "cena, com duração, proporção, nota e o prompt usado em cada uma. "
                             "Sem link de vídeo."),
    "cenas_tomadas_versions": _versoes("uma tomada"),
    "cenas_padroes_get": _l("Ver padrões das cenas", "Estilo e negative prompt padrão das cenas "
                            "do perfil (usados quando a cena deixa o campo vazio)."),
    "cenas_padroes_versions": _versoes("os padrões das cenas"),
    "conteudos_cenas_get": _l("Cenas de um conteúdo", "Cenas que compõem um conteúdo de vídeo "
                              "próprio."),
    # ---- anotações (leitura) ----
    "anotacoes_list": _l("Listar anotações e propostas", "Anotações e propostas presas aos itens, "
                         "com filtros (alvo, perfil, situação, tipo, cliente) e paginação "
                         "(`cursor`).", limite_padrao=50),
    "anotacoes_get": _l("Ver anotação", "Detalhe de uma anotação ou proposta, com o item alvo e "
                        "a situação (aberta, aplicada, descartada, arquivada)."),
    "anotacoes_versions": _versoes("uma anotação"),
    # ---- importação da agência (spec 013, leitura do registro) ----
    "agencia_importacoes_list": _l("Listar importações da agência", "Importações do markdown da "
                                   "agência para o SociMan (quem, quando, estado e contagens), "
                                   "mais recentes primeiro. O SociMan é a fonte da verdade "
                                   "depois da importação."),
    "agencia_importacoes_get": _l("Ver importação da agência", "Itens de uma importação: arquivo "
                                  "e trecho de origem, situação, escolha do dono, resultado e a "
                                  "entidade criada ou alterada. Filtros `situacao`, `tipo`, "
                                  "`perfil`."),
    # ---- escopo `propostas` (escritas do primeiro corte, FR-018) ----
    "anotacoes_create": Tool(
        "Criar anotação ou proposta",
        "Grava uma observação ou uma proposta de texto presa a um item (perfil, conta, canal, "
        "vídeo-fonte, corte, conteúdo ou destino). A proposta de texto (título, descrição, "
        "hashtags) só vale em destino e não muda o destino: o dono aplica ou descarta. "
        "Proposta de cena (spec 010): `tipo = \"proposta_cena\"` com alvo `perfil` (cena "
        "nova) ou `cena` (alteração; nunca numa cena usada) e `campos` com os campos da cena "
        "em camelCase (nome, avatarId, avatarArquivoId, cenarioId, cenarioArquivoId, plano, "
        "movimento, camera, acao em inglês, fala em pt-BR, textoTela, estilo, audio, duracaoS "
        "4/6/8, modo, quadroInicial, quadroFinal, produtoNome, produtoImagemId, negative). Os "
        "ids são assets do perfil (veja `assets_list`). Não cria nem altera a cena: o humano "
        "aceita pelo formulário.",
        escopo="propostas", escrita=True, entidade="anotacao"),
    "anotacoes_update": Tool(
        "Editar anotação", "Edita o texto ou os campos de uma anotação sua que ainda está "
        "aberta. Mande a `version` lida.", escopo="propostas", escrita=True, entidade="anotacao"),
    "anotacoes_archive": Tool(
        "Arquivar anotação", "Arquiva uma anotação sua que ainda está aberta.",
        escopo="propostas", escrita=True, entidade="anotacao"),
    "envios_selecionar": Tool(
        "Selecionar vídeo para corte", "Marca um vídeo-fonte (ou um link) como `selecionado` "
        "para corte no perfil. Não envia ao gerador de cortes: enviar é ato do dono, com o aviso "
        "de direito.", escopo="propostas", escrita=True, entidade="envio"),
    "destinos_update": Tool(
        "Editar textos do destino", "Edita título, descrição e hashtags de um destino ainda não "
        "aprovado (pendente ou com aprovação pedida). Aprovado em diante: recusado com "
        "`destino_aprovado`; grave uma proposta de texto no lugar. Mande a `version` lida.",
        escopo="propostas", escrita=True, entidade="destino", ocultar=("ia", "propostaId")),
}

_PROIBIDAS_I = {op: "publicação só com decisão humana (princípio I)" for op in (
    "conexoes_iniciar", "conexoes_retorno", "conexoes_desconectar", "conexoes_criador",
    "destinos_aprovar", "destinos_lote_aprovar", "conteudos_aprovar_todas",
    "conteudos_desaprovar_todas", "destinos_recusar",
    "agendamentos_create", "agendamentos_update", "agendamentos_cancelar",
    "agendamentos_lote_cancelar", "agendamentos_lote_reagendar", "agendamentos_sequencia",
    "destinos_enviar_agora", "destinos_confirmar_envio", "destinos_tentar_de_novo",
    "destinos_marcar_postado", "publicacao_config_update")}
_PROIBIDAS_II = {op: "direito e envio para corte são do dono (princípio II)" for op in (
    "canais_direito", "envios_enviar", "envios_retry", "envios_confirmar_qualidade",
    "cortes_retry", "cortes_aplicar_marca")}
_PROIBIDAS_VII = {op: "reverter e decidir propostas é do dono (princípio VII)" for op in (
    "assets_revert", "canais_revert", "contas_revert", "conteudos_revert", "destinos_revert",
    "envios_padroes_revert", "guias_conta_revert", "guias_perfil_revert", "ia_regras_revert",
    "kit_revert", "perfis_revert", "anotacoes_revert", "anotacoes_descartar",
    # spec 010
    "cenas_revert", "cenas_tomadas_revert", "cenas_padroes_revert")}
_PROIBIDAS_DONO = {op: "escolha do dono (vínculo do post, guia e regras)" for op in (
    "destinos_vinculo_criar", "destinos_vinculo_desfazer", "guias_perfil_update",
    "guias_conta_update", "ia_regras_update", "ia_regras_padrao")}
# Spec 020: importar (prévia, confirmar) e desfazer o histórico do TikTok Studio são do dono.
_PROIBIDAS_DONO |= {op: "importação do TikTok Studio é do dono (spec 020)" for op in (
    "studio_previa", "studio_confirmar", "studio_desfazer")}
# Spec 013: ler a pasta, confirmar e desfazer a importação da agência são do dono humano.
_PROIBIDAS_DONO |= {op: "importação da agência é do dono (spec 013)" for op in (
    "agencia_previa", "agencia_confirmar", "agencia_desfazer")}
_PROIBIDAS_PESSOAS = {op: "pessoas, autenticação e segurança" for op in (
    "users_list", "users_create", "users_update", "users_set_password",
    "users_resend_verification", "auth_login", "auth_logout", "auth_refresh", "auth_me",
    "auth_change_password", "auth_forgot_password", "auth_reset_password", "auth_verify_email",
    "auth_resend_verification", "security_events_list",
    # Exportação do dataset de métricas: rota de dono humano (spec 016), dado de dono (FR-015).
    "metricas_export")}
_PROIBIDAS_MCP = {op: "gestão do próprio MCP (só o dono humano)" for op in (
    "mcp_clientes_list", "mcp_clientes_create", "mcp_clientes_get", "mcp_clientes_update",
    "mcp_clientes_suspender", "mcp_clientes_reativar", "mcp_clientes_rotacionar",
    "mcp_clientes_revogar", "mcp_clientes_versions", "mcp_config_get", "mcp_config_update",
    "mcp_config_versions", "mcp_chamadas_list")}

# Spec 023: toda escrita do aprendizado (temas, classificação, decidir, preferências, análises
# da IA e conferências) é do dono humano.
_PROIBIDAS_DONO |= {op: "aprendizado: decisão do dono (spec 023)" for op in (
    "aprendizado_temas_create", "aprendizado_temas_lote", "aprendizado_temas_update",
    "aprendizado_temas_archive", "aprendizado_temas_restore", "aprendizado_temas_juntar",
    "aprendizado_temas_revert", "aprendizado_taxonomia_propor", "aprendizado_classificacoes_put",
    "aprendizado_classificacoes_revert", "aprendizado_classificar_pendentes",
    "aprendizado_recomendacoes_decidir", "aprendizado_decisoes_revert",
    "aprendizado_preferencias_patch", "aprendizado_preferencias_revert",
    "aprendizado_analises_estimativa", "aprendizado_analises_create",
    "aprendizado_hipotese_recomendar", "aprendizado_conferencias_put")}

# Spec 021: pedir, escolher, cancelar, tentar de novo e gerar outras são atos humanos (FR-008,
# FR-014), como enviar um áudio. A geração local fica só pela interface no primeiro corte.
_PROIBIDAS_DONO |= {op: "geração local: ato humano (spec 021)" for op in (
    "geracoes_criar", "geracoes_escolher", "geracoes_cancelar", "geracoes_tentar_de_novo",
    "geracoes_gerar_outras", "audios_enviar")}

PROIBIDAS: dict[str, str] = {**_PROIBIDAS_I, **_PROIBIDAS_II, **_PROIBIDAS_VII,
                             **_PROIBIDAS_DONO, **_PROIBIDAS_PESSOAS, **_PROIBIDAS_MCP}

_FORA_UPLOAD = {op: "upload ou binário (só pela interface)" for op in (
    "assets_upload", "assets_file_upload", "envios_arquivo", "conteudos_video_proprio",
    "cortes_upload", "fontes_upload", "perfis_upload_banner", "perfis_upload_logo", "midia_get",
    "fontes_padrao_file", "cenas_tomadas_upload")}
_FORA_DEPRECATED = {op: "rota deprecated" for op in (
    "fundos_list", "fundos_upload", "marca_dagua_list", "marca_dagua_upload",
    "postagens_sugestoes", "postagens_sugerir")}
_FORA_INFRA = {op: "infraestrutura ou apoio da interface" for op in (
    "health_api_health_get", "app_config", "perfis_slug_suggestion", "notificacoes_list",
    "notificacoes_marcar_lidas", "anotacoes_resumo",
    "agencia_estado")}  # spec 013: estado das pastas da agência (apoio da tela)
_FORA_ESCRITAS = {op: "escrita fora do primeiro corte (FR-018/FR-023)" for op in (
    "perfis_create", "perfis_update", "perfis_archive", "perfis_restore", "perfis_clear_banner",
    "perfis_clear_logo", "contas_create", "contas_update", "contas_archive", "contas_restore",
    "kit_update", "envios_padroes_put", "assets_create", "assets_update", "assets_archive",
    "assets_restore", "assets_reorder", "assets_file_update", "assets_file_archive",
    "assets_file_restore", "fontes_rename", "fontes_archive", "fontes_restore", "canais_create",
    "canais_update", "canais_archive", "canais_restore", "canais_resolver", "canais_sincronizar",
    "conteudos_update", "conteudos_archive", "conteudos_restore", "conteudos_add_destino",
    "cortes_update_hook", "cortes_archive", "cortes_restore", "destinos_archive",
    "destinos_restore", "destinos_pedir_aprovacao", "destinos_lote_pedir_aprovacao",
    "envios_archive", "agendamentos_sequencia_previa",
    # spec 010: o agente só propõe cenas (`proposta_cena`); escrever é do humano
    "cenas_create", "cenas_update", "cenas_duplicar", "cenas_pronta", "cenas_rascunho",
    "cenas_remontar", "cenas_archive", "cenas_restore", "cenas_tomadas_escolher",
    "cenas_tomadas_update", "cenas_tomadas_archive", "cenas_tomadas_restore",
    "conteudos_cenas_put", "cenas_padroes_put")}
_FORA_DONO = {op: "IA paga ou dado de dono" for op in (
    "ia_gerar", "ia_guia_montar", "ia_guia_testar", "ia_chamadas_list", "ia_chamadas_get",
    "ia_chamadas_descartar", "ia_resumo", "ia_regras_versions",
    "publicacao_config_get", "publicacao_config_versions", "conexoes_get",
    "conexoes_versions",
    # Spec 020: a leitura das importações do Studio fica fora do primeiro corte do MCP.
    "studio_importacoes", "studio_cobertura")}

# Spec 023: as análises da IA (pagas, com custo) e os históricos ficam fora do primeiro corte.
_FORA_DONO |= {op: "IA paga ou dado de dono" for op in (
    "aprendizado_analises_list", "aprendizado_analises_get", "aprendizado_temas_versions",
    "aprendizado_classificacoes_versions", "aprendizado_preferencias_versions")}

# Spec 021: as leituras da geração local ficam fora do primeiro corte do MCP.
_FORA_DONO |= {op: "geração local só pela interface no primeiro corte (spec 021)" for op in (
    "geracoes_listar", "geracoes_detalhe", "geracoes_versoes", "audios_detalhe")}

FORA: dict[str, str] = {**_FORA_UPLOAD, **_FORA_DEPRECATED, **_FORA_INFRA, **_FORA_ESCRITAS,
                        **_FORA_DONO}


def classificar(operation_id: str) -> Literal["tool", "fora", "proibida"] | None:
    if operation_id in TOOLS:
        return "tool"
    if operation_id in PROIBIDAS:
        return "proibida"
    if operation_id in FORA:
        return "fora"
    return None


def permitida(tool: Tool, escopo: str | None) -> bool:
    """`propostas` inclui `leitura`."""
    return tool.escopo == "leitura" or escopo == "propostas"
