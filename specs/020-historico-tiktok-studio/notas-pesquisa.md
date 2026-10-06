# Notas de pesquisa: exportação do TikTok Studio (020)

Data: 2026-10-02. Material bruto para o `research.md` do plano. A TikTok não documenta o formato
publicamente. A seção 0 vem de um **arquivo real**; as seções 1 a 5 (pesquisa na web, anterior ao
arquivo) ficam como contexto.

## 0. Formato confirmado (arquivo real de @atavernanerd, exportado em 2026-10-02, interface em inglês)

O dono baixou as 4 seções do Analytics do TikTok Studio, e **cada uma veio num ZIP**. Os originais ficam
em `~/Downloads` e **nunca entram no repositório** (o de Conteúdo tem títulos e links). Os testes usam
arquivos **sintéticos** com o mesmo formato.

| ZIP | Conteúdo | Uso na 020 |
|---|---|---|
| `Overview_2026-09-25_1790891174_atavernanerd.zip` | `Overview.csv` (320 B) | **sim** |
| `Followers_atavernanerd.zip` | `FollowerHistory.csv` (223 B), `FollowerActivity.csv` (`"Date","Hour","Active followers"`), `FollowerGender.csv` (`"Gender","Distribution"`), `FollowerTopTerritories.csv` (`"Top territories","Distribution"`); os três últimos vieram só com o cabeçalho | **só** `FollowerHistory.csv` |
| `Content_atavernanerd.zip` | `Content.csv` (totais por vídeo, com títulos e links) | não (FR-024) |
| `Viewers_atavernanerd.zip` | `Viewers.xlsx` | não |

**Os ZIPs:**
- as entradas ficam na raiz, sem pastas, sem compressão (método *stored*);
- o nome da Visão geral é `Overview_<AAAA-MM-DD do 1º dia>_<epoch em s>_<handle>.zip`. O epoch
  `1790891174` = 2026-10-01 18:46:14 −03 (21:46 UTC), que é o **fim do período** (o último dia do
  arquivo). Os demais ZIPs só trazem `<Seção>_<handle>.zip`;
- **o @ só aparece no nome do ZIP**, nunca no CSV.

**Os CSVs:** UTF-8 **com BOM**, separador `,`, todos os campos entre aspas, sem quebra de linha no fim,
inteiros sem separador de milhar (nos números vistos). Um dia por linha, em ordem crescente, e o último dia
é **ontem** (o dia da exportação não vem).

```text
Overview.csv
"Date","Video Views","Profile Views","Likes","Comments","Shares"
"September 25","118","0","5","0","0"
… (até "October 1")

FollowerHistory.csv
"Date","Followers","Difference in followers from previous day"
"September 25","0","0"
… "October 1","4","1"
```

- **Datas sem ano** ("September 25", "October 1"), com o nome do mês em inglês. O ano vem do nome do ZIP
  da Visão geral, ou é deduzido (FR-005a).
- **Visão geral:** números **do dia** (views de vídeo, visitas ao perfil, curtidas, comentários,
  compartilhamentos). Não traz alcance nem seguidores.
- **Seguidores:** `Followers` é o **total** no dia, e a diferença é para o dia anterior (no 1º dia
  aparece 0).
- **Dados reais** (25/09 a 01/10): views 118, 201, 1, 2, 6, 834 e 914; seguidores 0, 0, 0, 1, 2, 3 e 4.
- **A conferir quando o dono mudar a interface para pt-BR:** os cabeçalhos e o nome dos meses traduzidos.
  Os sinônimos em pt-BR da 020 são provisórios.

**Comparação com a coleta da 016** (banco de dev, 02/10):

| conta | 1ª coleta | situação do dia |
|---|---|---|
| @atavernanerd | 30/09 14:58 (−03) | o dia 30/09 não está inteiro coberto; 01/10 é o 1º dia inteiro |
| @meusqueridinhos10 | 01/10 18:11 (−03) | conta com vídeos desde 05/2025: no dia 01/10, a 019 soma as views da vida inteira deles |

O Studio corrige esses primeiros dias.

## 1. Onde fica e como se baixa
- **Só no desktop.** O app de celular não tem botão de exportar. O caminho é o TikTok Studio
  (`tiktok.com/tiktokstudio`, menu Analytics) para contas pessoais e de criador. Para contas Business, é o
  Business Suite (`tiktok.com/business-suite/insight/overview`). [2][3][5]
- O botão "Download data" (ícone de seta) fica no alto da página de Analytics. Ele exporta **uma seção
  por vez** (Overview, Content ou Followers), e cada seção vira um arquivo separado. [1][4][6]
- **Formatos:** CSV ou XLSX, e às vezes só XLSX. [1][4][6]
- **O "Download your data"** (Configurações → Conta) é outra coisa: traz TXT/JSON de atividade e
  **não tem métricas** de desempenho. Não serve para esta spec. [2][7]

## 2. Período
- Os guias divergem. O mais citado é o **intervalo personalizado de até 60 dias** por download [1][4][6][7].
  Há também os atalhos de 7, 28, 60 e **365 dias** no seletor, e a TikTok guarda só cerca de **1 ano** de
  analytics [3][8]. Hipótese de trabalho: o arquivo cobre **até 60 dias** (talvez 365), e mais tempo exige
  vários downloads.
- Consequência: o histórico possível vai no máximo ~1 ano para trás, e o que não for baixado agora se
  perde aos poucos.

## 3. Colunas (evidência concreta)
O projeto de código aberto `cgillinger/tiktok_stats` (2025) lia as exportações do Studio e guardava os
cabeçalhos. **Os cabeçalhos vêm traduzidos para o idioma da interface** (o projeto é sueco). [9]

**Arquivo diário da conta (Overview), uma linha por dia.** O projeto identifica o arquivo por
`date` + `video views` (inglês) ou `datum` + `videovisningar` (sueco). As colunas em sueco, com a
tradução:

| sueco | inglês provável | significado |
|---|---|---|
| Datum | Date | dia |
| Videovisningar | Video views | views de vídeo no dia |
| Målgrupp som nåtts | Reached audience | alcance (às vezes ausente) |
| Profilvisningar | Profile views | visitas ao perfil |
| Gilla-markeringar | Likes | curtidas no dia |
| Kommentarer | Comments | comentários no dia |
| Delningar | Shares | compartilhamentos no dia |
| Nettotillväxt | Net growth | seguidores líquidos no dia |
| Nya följare | New followers | novos seguidores |
| Tappade följare | Lost followers | seguidores perdidos |
| Klick på produktlänkar, GMV…, Webbplatsklickar… | (Business) | cliques e vendas: só Business, fora do escopo |

**Arquivo por vídeo (Content), uma linha por vídeo**, com os totais **na data da exportação** e sem
série diária: identificado por `video title` + `post time`. Colunas: Videotitel/Video title,
Videolänk/Video link, Publiceringstid/Post time, Videovisningar/Video views, Gilla-markeringar/Likes,
Kommentarer/Comments, Delningar/Shares, Lägg till i Favoriter/Add to Favorites. [9]

Observações:
- Numa versão posterior, o projeto parou de aceitar esses formatos ("legado"), o que **sugere que a TikTok
  mudou a exportação** em algum momento de 2025. [9] Outro motivo para conferir com um arquivo real.
- **Os números do diário são valores do dia** (views ganhas, curtidas ganhas, seguidores líquidos), e não
  totais acumulados como as fotos da Display API (016). Talvez exista uma coluna de total de seguidores,
  mas a evidência não confirma.
- Não há o @ da conta em coluna conhecida. Ele pode aparecer no nome do arquivo, mas sem garantia.

## 4. Fuso
- Um guia afirma que **as datas do arquivo exportado vêm em UTC** [1]. Nenhuma fonte oficial confirma.
  Para um dado diário, a diferença para São Paulo é de 3 h na borda do dia. A spec assume "dia do
  arquivo" com uma nota visível, a confirmar no arquivo real.

## 5. Limitações relevantes para a spec
- Exportação manual, sem API, um arquivo por seção e por download (60 dias, talvez 365).
- Cabeçalhos dependem do idioma da interface (pt-BR ou inglês, no caso do dono).
- O dia de hoje vem incompleto.
- O formato muda sem aviso [9]. O importador precisa recusar bem o que não reconhece.
- Os números do Studio e da Display API podem não bater exatamente (vídeos privados, atraso de
  atualização, correções da TikTok).

## Fontes
1. Commentpicker / pesquisa agregada, "Export TikTok Analytics" (CSV/XLSX, seções, UTC): https://commentpicker.com/export-tiktok-analytics.php
2. Graphed, "How to Download TikTok Analytics Data": https://www.graphed.com/blog/how-to-download-tiktok-analytics-data
3. Reelyze, "How to Check Your TikTok Analytics (2026)": https://getreelyze.com/guides/how-to-check-tiktok-analytics
4. clariBI, "How to Export CSV Data from TikTok Business Center": https://claribi.com/knowledge-base/how-to-export-csv-data-from-tiktok-business-center-and-import-it-into-claribi/
5. Conbersa, "What Is TikTok Studio?": https://www.conbersa.ai/learn/what-is-tiktok-studio
6. Graphed, "How to Export TikTok Analytics": https://www.graphed.com/blog/how-to-export-tiktok-analytics
7. Coupler.io, "How to Export Data from TikTok On a Schedule": https://blog.coupler.io/how-to-export-data-from-tiktok/
8. Sociality, "TikTok analytics 2025": https://sociality.io/blog/tiktok-analytics/
9. GitHub `cgillinger/tiktok_stats` (commit inicial 178b1d6, `src/utils/constants.js`, e versão atual com
   `LEGACY_FORMATS`): https://github.com/cgillinger/tiktok_stats

## A conferir com o arquivo real
- [x] Extensão: ZIP por seção com CSV dentro (UTF-8 com BOM, `,`, tudo entre aspas). XLSX só em
  Espectadores.
- [x] Cabeçalhos exatos em **inglês** (seção 0).
- [ ] Cabeçalhos e nomes de mês em **pt-BR**: falta exportar com a interface em português.
- [ ] Período máximo do download personalizado (60 ou 365 dias): o arquivo real tem 7 dias.
- [x] Seguidores: há o **total** (`Followers`) e a diferença diária. Não há novos nem perdidos.
- [x] Data sem ano ("September 25"); o @ só aparece no nome do ZIP.
- [ ] Fuso do dia (UTC ou o da conta): não dá para saber pelo arquivo. A 020 grava o dia de calendário.
