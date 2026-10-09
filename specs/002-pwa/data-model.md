# Modelo de dados: 002-pwa

A feature não cria tabelas nem chaves no Redis. Os "dados" são artefatos estáticos e o estado do
navegador.

## Manifesto do app (`manifest.webmanifest`, gerado no build)
| Campo | Valor | Regra |
|---|---|---|
| `name` / `short_name` | `SociMan` / `SociMan` | FR-002 |
| `description` | "Gestão das contas de mídia social da agência" | |
| `lang` | `pt-BR` | |
| `start_url` | `/app` | redireciona ao login sem sessão (spec 001) |
| `scope` / `id` | `/` / `/` | o app inteiro |
| `display` | `standalone` | janela própria (FR-002) |
| `theme_color` / `background_color` | `#0f172a` / `#0f172a` | |
| `icons` | 64, 192 e 512 (`purpose: any`), 512 (`purpose: maskable`) | FR-003 |

No `index.html` entram também `<meta name="theme-color">`,
`<link rel="apple-touch-icon" href="/apple-touch-icon-180x180.png">`,
`<meta name="apple-mobile-web-app-capable" content="yes">` e o título `SociMan`
(iOS, melhor esforço).

## Cache do service worker (navegador)
| Cache | Conteúdo | Ciclo de vida |
|---|---|---|
| precache Workbox (`workbox-precache-v2-…`) | só os arquivos do build: HTML, JS e CSS com hash, ícones e manifest | um por versão; o antigo sai na ativação (`cleanupOutdatedCaches`) |

**Invariantes** (SC-004, checadas por `check:pwa` e pelo e2e PWA):
- nenhuma URL `/api/*` ou `/img/*` no Cache Storage;
- nada de token ou dado de usuário no Cache Storage, IndexedDB, localStorage ou sessionStorage.

## Estados da interface (US2 e US3)
```
boot ──refresh ok──▶ app
  │ ──401/sem cookie──▶ login
  └──falha de rede──▶ "Sem conexão com o SociMan" ──Tentar de novo──▶ boot

SW novo instalado ──▶ aviso "Nova versão disponível" ──Atualizar──▶ skipWaiting + reload (sessão preservada via refresh)
                                  └──ignorado──▶ assume ao fechar todas as janelas (próxima abertura)
```

## Certificados (arquivos no host, fora do git)
| Arquivo | Conteúdo | Git |
|---|---|---|
| `docker/certs/ca/sociman-ca.key` | chave privada da CA da casa (600) | **ignorado** |
| `docker/certs/ca/sociman-ca.crt` / `.cer` | CA pública (PEM / DER), para instalar nos aparelhos | ignorado (é gerada por máquina) |
| `docker/certs/localhost.pem` / `localhost-key.pem` | certificado do servidor (SAN `IP:192.168.86.47`, `DNS:localhost`, `IP:127.0.0.1`; 825 dias) | ignorado (já era) |
