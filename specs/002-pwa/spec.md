# Feature Specification: SociMan instalável como app (002-pwa)

**Feature Branch**: `002-pwa`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "002-pwa: modo PWA do SociMan (manifest, ícones, service worker compatível com a CSP estrita). O SPA (apps/web, React 19 + Vite) já tem auth completa (spec 001: access token só em memória, refresh em cookie httpOnly com Path=/api/auth/refresh). O dono quer instalar o SociMan como app no celular e no desktop pela rede de casa. Restrições: CSP estrita herdada do volans (check:csp compara vite.config.ts com docker/nginx/05-edge-mode.envsh); o service worker não pode cachear respostas de /api nem guardar tokens; o cookie de sessão é Secure (exige HTTPS, edge em :8543)."

## Clarifications

### Session 2026-09-29

- Q: Como os aparelhos da casa vão confiar no HTTPS do SociMan? → A: CA local da casa (estilo mkcert), instalada uma vez em cada aparelho; sem serviço externo, só rede de casa.
- Q: Por qual endereço os aparelhos abrem o SociMan? → A: IP fixo `https://192.168.86.47:8543` (reservado no roteador); o certificado também cobre `localhost`.
- Q: Acesso por HTTP na rede de casa? → A: `http://192.168.86.47:8180` redireciona para o endereço HTTPS; `localhost:8180` segue em HTTP para dev e e2e.
- Q: O iPhone é obrigatório nesta entrega? → A: Melhor esforço. Android e desktop são obrigatórios e testados; no iPhone entram ícone, metadados e o guia da CA, sem depender de teste num iPhone real para aceitar.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Instalar o SociMan no celular e no computador (Priority: P1)

O dono abre o SociMan no navegador do celular ou do computador, pela rede de casa, e o
navegador oferece "Instalar app". Depois de instalado, o SociMan abre pelo ícone na tela
inicial, em janela própria (sem barra de endereço), com nome e ícone do SociMan, e o login
funciona como no navegador.

**Why this priority**: é o objetivo da feature; sem instalação não há PWA.

**Independent Test**: num celular Android com Chrome e num computador com Chrome/Edge, na rede
de casa, instalar o SociMan, abrir pelo ícone, entrar e usar uma tela protegida.

**Acceptance Scenarios**:

1. **Given** um aparelho na rede de casa, **When** o dono abre o endereço do SociMan, **Then** o
   navegador considera a conexão segura (sem aviso de certificado) e oferece a instalação.
2. **Given** o app instalado, **When** o dono o abre pelo ícone, **Then** ele abre em janela
   própria, com o nome "SociMan", o ícone e a cor do tema, direto na tela inicial do app.
3. **Given** o app instalado, **When** o dono entra com e-mail e senha, **Then** a sessão
   funciona e continua ao fechar e reabrir o app dentro do prazo da sessão (7 dias).
4. **Given** um iPhone (Safari), **When** o dono usa "Adicionar à Tela de Início", **Then** o app
   abre em tela cheia com o ícone correto. (Melhor esforço: não bloqueia a aceitação da feature.)

---

### User Story 2 - Abrir o app sem rede (Priority: P2)

Se o aparelho estiver sem conexão com o SociMan (fora de casa ou servidor desligado), o app
instalado ainda abre e mostra uma tela clara de "Sem conexão com o SociMan", em vez de uma
página de erro do navegador. Nenhum dado de negócio fica guardado no aparelho.

**Why this priority**: evita a impressão de app quebrado; não é essencial para usar o SociMan,
que depende do servidor de casa.

**Independent Test**: com o app instalado, desligar a rede do aparelho e abrir o app: aparece a
tela "Sem conexão"; religar a rede e tocar em "Tentar de novo": o app volta ao normal.

**Acceptance Scenarios**:

1. **Given** o app instalado e sem conexão, **When** o dono o abre, **Then** vê "Sem conexão com o
   SociMan" e um botão "Tentar de novo".
2. **Given** a tela de sem conexão, **When** a rede volta e o dono toca em "Tentar de novo",
   **Then** o app carrega normalmente (e pede login se a sessão tiver expirado).
3. **Given** qualquer uso do app, **When** se inspeciona o que ficou guardado no aparelho,
   **Then** não há respostas da API, tokens nem dados de usuários.

---

### User Story 3 - Receber a versão nova do app (Priority: P2)

Quando uma versão nova do SociMan é publicada no servidor de casa, o app instalado passa a usá-la
sem que o dono precise desinstalar ou limpar dados.

**Why this priority**: sem isso o app instalado pode ficar preso numa versão velha, que conversa
errado com a API nova.

**Independent Test**: com o app aberto, publicar uma versão nova; o app avisa e, ao aceitar,
recarrega já na versão nova.

**Acceptance Scenarios**:

1. **Given** o app aberto e uma versão nova publicada, **When** o app percebe a atualização,
   **Then** mostra "Nova versão disponível" com o botão "Atualizar".
2. **Given** o aviso, **When** o dono toca em "Atualizar", **Then** o app recarrega na versão nova
   sem perder a sessão.
3. **Given** o dono ignora o aviso, **When** ele fecha e reabre o app, **Then** a versão nova é
   usada.

---

### Edge Cases

- Certificado inválido ou expirado: o navegador não oferece instalação; a documentação diz como
  renovar/instalar o certificado.
- Aparelho sem a CA instalada: o navegador mostra aviso de certificado e não oferece instalação;
  o guia (FR-004a) resolve.
- Endereço da rede de casa mudou (IP novo): o app instalado deixa de abrir; a documentação indica
  que o endereço precisa ser fixo (IP reservado no roteador ou nome local).
- Sessão expirada enquanto o app estava fechado: ao abrir, vai para o login normalmente.
- Chamada à API sem rede no meio do uso: a tela mostra erro de conexão, sem resposta velha
  guardada.
- App aberto em duas janelas quando chega versão nova: as duas passam para a nova depois de
  recarregar.
- Acesso por `http://192.168.86.47:8180` em outro aparelho: redireciona para
  `https://192.168.86.47:8543` (FR-004c).

## Requirements *(mandatory)*

### Functional Requirements

**Instalação**
- **FR-001**: O SociMan DEVE ser instalável como app nos navegadores que suportam instalação
  (Chrome/Edge no Android e no desktop) e adicionável à tela inicial no iOS.
- **FR-002**: O app instalado DEVE abrir em janela própria, com nome "SociMan", nome curto
  "SociMan", ícone próprio, cor de tema e tela inicial (`/app`, que redireciona ao login se não
  houver sessão).
- **FR-003**: DEVE haver ícones nos tamanhos exigidos pelas plataformas, inclusive a versão
  "maskable" (Android) e o ícone para a tela inicial do iOS.
- **FR-004**: O acesso pela rede de casa DEVE ser feito por um endereço HTTPS que os aparelhos da
  casa reconheçam como seguro, sem aviso de certificado. A confiança vem de uma **autoridade
  certificadora (CA) própria da casa**: o servidor usa um certificado emitido por ela para o
  endereço local, e o dono instala a CA uma vez em cada aparelho. O endereço oficial na rede de
  casa é `https://192.168.86.47:8543`; o certificado vale para esse IP e para `localhost`.
- **FR-004a**: DEVE existir um guia passo a passo, em pt-BR, para instalar a CA no Android, no
  iPhone (incluindo ativar a confiança total), no Linux e no Windows, e para renovar o
  certificado do servidor.
- **FR-004c**: Quem abrir o SociMan por HTTP pelo IP da rede de casa DEVE ser redirecionado para o
  mesmo caminho no endereço HTTPS; o acesso por `localhost` em HTTP continua funcionando
  (desenvolvimento e testes automatizados).
- **FR-004b**: A chave privada da CA e a do servidor NÃO DEVEM entrar no repositório.

**Funcionamento sem rede e segurança**
- **FR-005**: O app DEVE guardar no aparelho apenas os arquivos da própria interface (páginas,
  scripts, estilos, ícones), nunca respostas da API, tokens, cookies ou dados de usuários.
- **FR-006**: Sem conexão, o app DEVE abrir e mostrar a tela "Sem conexão com o SociMan" com o
  botão "Tentar de novo".
- **FR-007**: Todas as chamadas à API DEVEM ir sempre ao servidor (sem resposta guardada); sem
  rede, falham com a mensagem de erro de conexão da interface.
- **FR-008**: A política de segurança de conteúdo estrita (CSP) DEVE continuar valendo em
  produção, sem liberar scripts em linha nem origens externas; a verificação automática de CSP
  continua passando.

**Atualização**
- **FR-009**: Quando houver versão nova, o app DEVE avisar "Nova versão disponível" com o botão
  "Atualizar"; ao aceitar, recarrega na versão nova sem perder a sessão.
- **FR-010**: Uma versão nova DEVE ser usada, no máximo, na próxima abertura do app, mesmo que o
  aviso seja ignorado.
- **FR-011**: Ao sair (logout), nada da sessão pode continuar no aparelho além do que já é
  apagado hoje.

### Key Entities

- **Manifesto do app**: nome, nome curto, descrição, ícones, cores, tela inicial, modo de
  exibição e escopo (todo o SociMan).
- **Arquivos da interface guardados**: cópia local, por versão, dos arquivos estáticos do SPA,
  usada para abrir o app sem rede. Não contém dados.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O dono instala o SociMan no celular Android e no computador em menos de 1 minuto
  cada, sem aviso de certificado.
- **SC-002**: O app instalado abre (tela de login ou tela inicial) em menos de 2 segundos na rede
  de casa, depois da primeira visita.
- **SC-003**: Sem rede, o app instalado mostra a tela "Sem conexão" em menos de 2 segundos, em
  100% das aberturas.
- **SC-004**: Nenhuma resposta da API, token ou dado de usuário é encontrado no armazenamento do
  aparelho após um uso completo (login, telas de usuários e eventos, logout).
- **SC-005**: Depois de publicar uma versão nova, o app instalado passa a usá-la em no máximo uma
  reabertura, sem desinstalar nem limpar dados.
- **SC-006**: A verificação automática de CSP e o conjunto de verificações do front-end continuam
  passando.

## Assumptions

- Aparelhos-alvo: celular Android (Chrome), computador Linux/Windows (Chrome ou Edge) e,
  secundariamente, iPhone (Safari, "Adicionar à Tela de Início").
- Cada aparelho da casa aceita instalar uma CA de usuário (Android com Chrome e iPhone aceitam;
  exige passos manuais descritos no guia).
- O uso é só na rede de casa; acesso de fora de casa (VPN, domínio público) fica fora desta spec.
- O endereço do servidor na rede de casa é fixo: `192.168.86.47` (IP do cabo, reservado no
  roteador), como já recomendado para o OpenClaw. Se mudar, o certificado é reemitido e o app
  reinstalado.
- Notificações push, sincronização em segundo plano e uso offline com dados ficam fora desta spec.
- Ícone: gerado a partir de uma marca simples do SociMan (letra "S" sobre a cor do tema) até
  existir uma logo oficial; trocar a imagem não exige mudar a spec.
- A auth da spec 001 não muda: o token de acesso segue só em memória e o cookie de sessão segue
  restrito à rota de renovação.
