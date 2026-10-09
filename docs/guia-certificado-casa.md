# Guia: certificado da casa e instalação do app

Como abrir o SociMan pela rede de casa em `https://192.168.86.47:8543` sem aviso de certificado
e instalá-lo como app (spec [002-pwa](../specs/002-pwa/spec.md), decisões R6 a R8 em
[research.md](../specs/002-pwa/research.md)).

## 1. O que é a CA da casa
- O navegador só instala um PWA por **HTTPS confiável**. Um IP de rede local não consegue
  certificado público, então o SociMan usa uma **autoridade certificadora (CA) própria**, a
  "SociMan CA da casa".
- A CA assina o certificado do edge (`docker/certs/localhost.pem`), que vale para
  `192.168.86.47`, `localhost` e `127.0.0.1`.
- Cada aparelho que instalar a CA passa a confiar nesse certificado.

**Por que é seguro para uso doméstico:**
- A CA só existe nesta máquina. A chave privada (`docker/certs/ca/sociman-ca.key`) tem
  permissão 600, fica fora do git e nunca sai de `docker/certs/ca/`.
- Quem não tem a chave não consegue emitir certificados em nome da CA.
- O risco que sobra é o da própria chave: quem a tiver consegue se passar por **qualquer site**
  nos aparelhos que confiam na CA. Por isso ela nunca é compartilhada (seção 9).
- Se quiser, remova a CA de um aparelho quando ele não for mais usar o SociMan.

## 2. Gerar e renovar
```bash
./scripts/certs-casa.sh                 # IP padrão: 192.168.86.47
./scripts/certs-casa.sh 192.168.86.50   # se o IP da máquina mudar
```
O script roda o `openssl` num container (sem sudo e sem instalar nada no host) e:
1. cria a CA **só se ela ainda não existir** (validade de 10 anos);
2. reemite o certificado do servidor (validade de 825 dias, o máximo aceito por iOS e Chrome);
3. gera `docker/certs/ca/sociman-ca.crt` (PEM) e `sociman-ca.cer` (DER);
4. imprime a **impressão digital SHA-256 da CA** e as validades;
5. reinicia o edge.

**Renovar** é rodar o script de novo. A CA continua a mesma, então os aparelhos **não precisam
reinstalar nada**. Só é preciso reinstalar a CA nos aparelhos se ela mudar, o que só acontece se
`docker/certs/ca/sociman-ca.key` for apagada.

Para rever as validades depois:
```bash
openssl x509 -in docker/certs/localhost.pem -noout -enddate
openssl x509 -in docker/certs/ca/sociman-ca.crt -noout -enddate
```

## 3. Levar a CA até o aparelho
**Pela rede (mais simples):** no navegador do aparelho, conectado ao Wi-Fi de casa, abra
- `http://192.168.86.47:8180/sociman-ca.cer` (DER, melhor para Android e Windows), ou
- `http://192.168.86.47:8180/sociman-ca.crt` (PEM, melhor para iPhone e Linux).

Esses são os únicos endereços que continuam em HTTP pelo IP da casa. O resto redireciona para
HTTPS, e o aparelho ainda não confia no HTTPS antes de instalar a CA.

**Por cabo ou mensageiro:** copie `docker/certs/ca/sociman-ca.cer` ou `.crt` para o aparelho
(USB, e-mail para você mesmo etc.). **Nunca copie** o `sociman-ca.key`.

## 4. Conferir a impressão digital SHA-256
Como a CA viaja por HTTP, alguém na rede poderia, em tese, trocá-la no caminho. Antes de confiar,
confira se a impressão digital no aparelho é **igual à que o script imprimiu**. Para ver de novo
no computador:
```bash
openssl x509 -in docker/certs/ca/sociman-ca.crt -noout -fingerprint -sha256
```
Confira todos os pares de dígitos, e não só os primeiros. Se não bater, **não instale** e baixe de
novo por cabo.

Onde ver no aparelho:
- **Android:** depois de instalar, em Credenciais confiáveis → Usuário → "SociMan CA da casa".
  Algumas versões mostram só SHA-1; nesse caso compare no Chrome do computador ou use o cabo.
- **iPhone:** Ajustes → Geral → VPN e Gerenciamento de Dispositivos → perfil → Mais detalhes.
- **Chrome (Linux/Windows):** no certificado importado → Detalhes → SHA-256.
- **Windows:** abrir o `.crt` → Detalhes → mostra só SHA-1 no campo "Impressão digital"; use o
  comando `certutil -hashfile sociman-ca.cer SHA256`, que calcula o SHA-256 do arquivo DER (o
  mesmo valor da impressão digital).

## 5. Instalar a CA em cada aparelho
### Android
1. Baixe `http://192.168.86.47:8180/sociman-ca.cer`.
2. Configurações → Segurança (ou "Segurança e privacidade") → Mais configurações de segurança →
   **Criptografia e credenciais** → **Instalar um certificado** → **Certificado de CA**.
3. Confirme o aviso "Instalar mesmo assim" e escolha o arquivo baixado.
4. Confira a impressão digital (seção 4).

Os nomes dos menus mudam por fabricante. Se não achar, busque "certificado" nas Configurações.
O Chrome do Android confia em CAs de usuário para sites, que é o caso aqui.

### iPhone / iPad (melhor esforço)
1. No **Safari**, abra `http://192.168.86.47:8180/sociman-ca.crt` e aceite baixar o perfil.
2. Ajustes → **Perfil Baixado** → Instalar (pede o código do aparelho).
3. **Passo obrigatório:** Ajustes → Geral → Sobre → **Ajustes de Confiança de Certificado** →
   ative "SociMan CA da casa". Sem isso, o iPhone instala a CA, mas não confia nela.

### Chrome no Linux
1. Abra `chrome://settings/certificates` (ou Configurações → Privacidade e segurança →
   Segurança → Gerenciar certificados).
2. Aba **Autoridades** → **Importar** → escolha `docker/certs/ca/sociman-ca.crt`.
3. Marque **"Confiar neste certificado para identificar sites"** → OK.
4. Feche e reabra o Chrome.

O Firefox tem lista própria: Configurações → Privacidade e segurança → Certificados → Ver
certificados → Autoridades → Importar.

### Windows
1. Copie `sociman-ca.crt` (ou baixe o `.cer`) e dê dois cliques → **Instalar Certificado**.
2. Local do repositório: **Usuário Atual**.
3. **Colocar todos os certificados no repositório a seguir** → Procurar → **Autoridades de
   Certificação Raiz Confiáveis** → Concluir → confirme o aviso de segurança.
4. Feche e reabra o Chrome ou o Edge.

## 6. Instalar o app
Antes, suba o modo casa no computador: `npm run casa:up`.

- **Android (Chrome):** abra `https://192.168.86.47:8543`, sem aviso de certificado → menu ⋮ →
  **Instalar app** (ou "Adicionar à tela inicial" → Instalar). O ícone do SociMan aparece na
  tela inicial e abre em janela própria.
- **Desktop (Chrome ou Edge):** abra `https://192.168.86.47:8543` (ou `https://localhost:8543`
  no próprio computador) → ícone de instalar na barra de endereço, ou menu → **Instalar
  SociMan**.
- **iPhone (Safari):** abra `https://192.168.86.47:8543` → botão Compartilhar →
  **Adicionar à Tela de Início**. No iPhone, a instalação é sempre por esse menu.

Depois do login, fechar e reabrir o app mantém a sessão.

## 7. Problemas comuns
**O IP da máquina mudou.** O certificado vale só para o IP em que foi emitido, e o
redirecionamento usa `LAN_HOST`.
1. Reserve o IP no roteador (recomendado), **ou**
2. rode `./scripts/certs-casa.sh <IP-novo>` e suba o edge com `LAN_HOST=<IP-novo>` (por exemplo,
   no `.env` da raiz: `LAN_HOST=<IP-novo>`, depois `docker compose up -d edge`).

A CA não muda, então os aparelhos não precisam reinstalá-la. O app instalado aponta para o
endereço antigo, então instale de novo pelo endereço novo.

**Ainda aparece aviso de certificado.**
- A CA não foi instalada ou, no iPhone, falta ativar a confiança (seção 5).
- O navegador não foi reiniciado depois da importação.
- O endereço não é exatamente `https://192.168.86.47:8543` (outro IP, ou um nome da rede que não
  está no certificado).
- O certificado venceu: rode o script de novo.
- Conferir no computador:
  `echo | openssl s_client -connect 192.168.86.47:8543 -CAfile docker/certs/ca/sociman-ca.crt 2>/dev/null | grep 'Verify return code'`
  deve mostrar `0 (ok)`.

**Abri por HTTP.** `http://192.168.86.47:8180` redireciona sozinho para
`https://192.168.86.47:8543` (menos os arquivos da CA). O app não instala por HTTP. Em
`http://localhost:8180` não há redirecionamento, de propósito, para o desenvolvimento e os testes.

**O download da CA abre como texto ou não instala.** Use o `.cer` no Android e no Windows e o
`.crt` no iPhone e no Linux.

## 8. Remover a CA de um aparelho
- **Android:** Criptografia e credenciais → Credenciais confiáveis → Usuário → remover.
- **iPhone:** Ajustes → Geral → VPN e Gerenciamento de Dispositivos → perfil → Remover.
- **Chrome/Linux:** `chrome://settings/certificates` → Autoridades → "SociMan CA da casa" →
  Excluir.
- **Windows:** `certmgr.msc` → Autoridades de Certificação Raiz Confiáveis → Certificados →
  excluir.

## 9. Aviso: nunca compartilhe `sociman-ca.key`
`docker/certs/ca/sociman-ca.key` é a chave privada da CA. Quem a tiver consegue emitir
certificados aceitos por **qualquer site** em todos os aparelhos que confiam na CA, inclusive
bancos e e-mail.
- Não envie, não copie para o celular, não faça commit (ela já é ignorada pelo git) e não a
  imprima no terminal.
- Só `sociman-ca.crt` e `sociman-ca.cer` são públicos.
- Se a chave vazar: apague `docker/certs/ca/sociman-ca.*`, rode `./scripts/certs-casa.sh` (cria
  uma CA nova), **remova a CA antiga de todos os aparelhos** (seção 8) e instale a nova.
