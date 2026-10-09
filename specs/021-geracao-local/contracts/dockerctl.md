# Contrato: `dockerctl` (ajuste de RAM do ComfyUI) — D1 = A (decidida em 2026-10-07)

> **RISCO DE SEGURANÇA.** Quem tem acesso ao `docker.sock` tem **poder total sobre o host** (pode criar um
> container privilegiado que monta `/` e virar root). Este contrato descreve a opção recomendada (A, um
> container mínimo do SociMan com o socket) e a alternativa B (o mesmo script como serviço do host). As
> duas reduzem o que o **gerador** pode pedir a 3 ações fixas, mas o processo que segura o socket continua
> sendo um ponto de poder total. O dono escolhe entre A e B (research R4). Proxy genérico do socket e
> socket montado no gerador estão **rejeitados**.

## API (igual em A e B)

Base: `DOCKERCTL_URL` (A: `http://dockerctl:8080`; B: `http://<IP da gpu-local>:18790`). Todo pedido leva
`Authorization: Bearer <DOCKERCTL_TOKEN>`; sem ele ou errado → 401 (comparação em tempo constante).
O corpo dos pedidos é **ignorado**.

| Método e caminho | Faz no Docker | Resposta |
|---|---|---|
| `GET /comfyui/memoria` | `GET /v1.47/containers/comfyui/json` | `{memoria_bytes, memoria_swap_bytes, estado: "normal"|"job"|"outro"}` |
| `POST /comfyui/memoria/subir` | `POST /v1.47/containers/comfyui/update` com `{"Memory": MEM_JOB, "MemorySwap": MEM_JOB}` | igual ao GET, depois de ler de novo |
| `POST /comfyui/memoria/devolver` | idem com `MEM_NORMAL` | igual ao GET |

Qualquer outro método ou caminho → 404 (com linha no log). O nome do container (`comfyui`), a versão da
API do Docker e os valores vêm **só** do ambiente do `dockerctl`: `DOCKERCTL_CONTAINER=comfyui`,
`DOCKERCTL_MEM_JOB=28g`, `DOCKERCTL_MEM_NORMAL=12g`. O `docker update` de memória para baixo funciona com
o container rodando (o cgroup aceita reduzir se o uso atual couber; se não couber, o Docker devolve erro e
o `dockerctl` responde 409 `nao_coube`, e o gerador tenta de novo depois de `POST /free` no ComfyUI).

Log (stdout, uma linha por ação): data, ação, antes, depois, resultado. Sem o token.

## Opção A (escolhida pelo dono): container no compose do SociMan

```yaml
  dockerctl:
    build: ./docker/dockerctl          # Dockerfile FROM python:3.12-alpine, só server.py (stdlib)
    user: "1000:${DOCKER_GID}"          # gid do grupo docker do host (data-setup.sh check descobre)
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    environment:
      DOCKERCTL_TOKEN: ${DOCKERCTL_TOKEN:-}
      DOCKERCTL_CONTAINER: comfyui
      DOCKERCTL_MEM_JOB: 28g
      DOCKERCTL_MEM_NORMAL: 12g
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock   # PODER TOTAL: só aqui
    networks: [dockerctl]
    # sem ports
networks:
  dockerctl:
    internal: true    # sem saída; só o gerador está nela
```
- Sem `DOCKERCTL_TOKEN`, o `dockerctl` não sobe (sai com erro) e o gerador fica sem jobs `comfyui`
  (`memoriaComfyui: "nao_configurado"`).
- O `check:secrets` cobre o token (o dono gera com `openssl rand -hex 32`, nunca impresso).

## Opção B (não escolhida; só registro): serviço de usuário no host
O mesmo `server.py`, como unit `systemd --user` (`~/.config/systemd/user/sociman-dockerctl.service`),
ouvindo só no IP da rede `gpu-local` (fixado com `--subnet` na criação da rede) e na porta 18790, com uma
regra do ufw para a sub-rede. O gerador entra pela `gpu-local`. Fica fora do compose e do repo (como o
OpenClaw); o script e a unit ficam em `docs/` como referência.

## Fake
- pytest: `apps/api/tests/fakes/dockerctl_fake.py` (estado do limite; falhas "não volta", "fora", "não coube");
- e2e: `openshorts-fake` em `/dockerctl/*` (`DOCKERCTL_URL=http://openshorts-fake:8000/dockerctl`), com
  `GET /geracao-e2e/memoria` para o teste conferir 28 → 12 em cada job.
