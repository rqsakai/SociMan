# Quickstart de validação: 002-pwa

O contrato está em [contracts/pwa.md](contracts/pwa.md), e os estados e artefatos em
[data-model.md](data-model.md).

## 1. Certificado da casa (uma vez)
```bash
./scripts/certs-casa.sh            # CA da casa + certificado para 192.168.86.47 e localhost
```
Esperado: o script imprime a impressão digital SHA-256 da CA, e
`openssl s_client -connect 192.168.86.47:8543 </dev/null | openssl x509 -noout -ext subjectAltName`
mostra `IP Address:192.168.86.47`.

## 2. Modo casa (build de produção)
```bash
npm run casa:up                    # build + EDGE_MODE=prod + perfil prod
curl -sI http://192.168.86.47:8180/app | grep -i location   # → https://192.168.86.47:8543/app
curl -s http://192.168.86.47:8180/sociman-ca.crt | head -1    # → -----BEGIN CERTIFICATE-----
curl -sI http://localhost:8180/ | head -1                     # → 200 (sem redirecionamento)
```

## 3. Instalar a CA nos aparelhos (guia: `docs/guia-certificado-casa.md`)
- **Android:** baixar `http://192.168.86.47:8180/sociman-ca.cer` → Configurações → Segurança →
  Criptografia e credenciais → Instalar certificado → Certificado de CA. Conferir a impressão
  digital.
- **Desktop Linux (Chrome):** `chrome://settings/certificates` → Autoridades → Importar.
- **Windows:** abrir o `.crt` → Instalar → "Autoridades de Certificação Raiz Confiáveis".
- **iPhone (melhor esforço):** abrir o `.crt` no Safari → Ajustes → Perfil baixado → Instalar →
  Ajustes → Geral → Sobre → Ajustes de Confiança de Certificado → ativar.

## 4. Instalar o app (US1)
Abrir `https://192.168.86.47:8543` → sem aviso de certificado → menu "Instalar app" → abrir pelo
ícone: janela própria, nome e ícone do SociMan → login → fechar e reabrir: continua logado.

## 5. Sem rede (US2)
Com o app instalado, ativar o modo avião → abrir o app → "Sem conexão com o SociMan" → desativar →
"Tentar de novo" → o app volta.

## 6. Versão nova (US3)
Com o app aberto, mudar um texto qualquer e rodar `npm run casa:up` → o app mostra "Nova versão
disponível" → "Atualizar" → o texto novo aparece e a sessão continua.

## 7. Testes automatizados (princípio VI)
```bash
npm run check:web            # inclui check:pwa (build) e check:csp (CSP inalterada)
npm run test:e2e             # e2e de dev (inalterados; stack em modo dev)
npm run casa:up && npm run test:e2e:pwa   # e2e do PWA (stack em modo prod)
```
Obrigatórios:
- o SW registra;
- offline mostra "Sem conexão";
- o Cache Storage não tem `/api` depois de login e navegação (SC-004);
- redirecionamento HTTP → HTTPS pelo IP da casa;
- `localhost` sem redirecionamento.

## 8. Medir e registrar
SC-001 (instalar em menos de 1 min por aparelho), SC-002 (abrir em menos de 2 s), SC-003 (sem
rede em menos de 2 s) e SC-005 (versão nova em no máximo uma reabertura).

## Resultado da verificação (2026-09-29)
- `npm run check:web`: verde (inclui `check:pwa`, `check:csp` inalterado, `check:contract`).
- `pytest`: 193 passed (sem mudança na API).
- `test:e2e:pwa` (modo casa): 9/9 em 3 rodadas seguidas. Cobrem: manifest, SW activated, cadeia HTTPS válida para a CA da casa (IP e localhost), redirecionamento HTTP → HTTPS pelo IP, CA por HTTP, cache sem `/api`/token antes e depois de Sair, "Sem conexão" em menos de 2 s (SC-003) e versão nova com sessão preservada (SC-005).
- `test:e2e` (modo dev): 7/7.
- Validação manual nos aparelhos: **aprovada pelo dono** em 2026-09-29. SC-001 (instalação em menos de 1 min) e SC-002 (abertura em menos de 2 s) não tiveram os tempos medidos e registrados.
