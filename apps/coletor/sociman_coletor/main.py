"""CLI `sociman-coletor` (contracts/coletor.md, "CLI"; FR-022).

| Comando | Sai com |
|---|---|
| `rodar` | só por sinal (3), `PARAR` (0) ou parada do serviço (4 token/escopo, 5 protocolo) |
| `uma-vez --limite N [--fora-da-janela]` | 0 tudo gravado/repetido; 2 erro/inválido; 3 sinal |
| `dry-run [--limite N]` | 0 (fila sem reserva, nada aberto, nada enviado) |
| `autoteste [--sem-token]` | 0 ok; 1 com a lista de falhas |
| `perfil-iniciar` | 0 ("perfil pronto") |
| `parar [--agora]` | 0 |
| `reprocessar --desde AAAA-MM-DD [--ate] [--tipo]` | 0; 2 se algum item voltou `invalido` |
| `--versao` | 0 |

Toda saída passa pelo `log.py`: nunca cookie, token, nome, @, texto de avaliação ou URL com `?`.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sociman_coletor import PROTOCOLO, __version__, api, config, log, modelos
from sociman_coletor.estado import Estado
from sociman_coletor.navegador import (
    ErroNavegador,
    Trava,
    achar_chrome,
    perfil_iniciar,
    versao_chrome,
)
from sociman_coletor.redes.tiktok_shop import adaptador_padrao
from sociman_coletor.rodada import Coletor


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sociman-coletor", description="Coletor de mercado do SociMan (só leitura)."
    )
    p.add_argument("--versao", action="store_true", help="imprime a versão e o protocolo")
    p.add_argument("--config-dir", default=None, help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="comando")
    sub.add_parser("rodar", help="laço contínuo (serviço)")
    uma = sub.add_parser("uma-vez", help="uma rodada com no máximo N páginas")
    uma.add_argument("--limite", type=int, required=True)
    uma.add_argument(
        "--fora-da-janela",
        action="store_true",
        help="ignora a janela (só para a sonda guiada com o dono)",
    )
    dry = sub.add_parser("dry-run", help="mostra a fila sem reservar, sem abrir o Chrome")
    dry.add_argument("--limite", type=int, default=40)
    auto = sub.add_parser("autoteste", help="confere config, token, CA, API, Chrome e sessão")
    auto.add_argument("--sem-token", action="store_true")
    sub.add_parser("perfil-iniciar", help="abre o Chrome no perfil dedicado para o dono logar")
    parar = sub.add_parser("parar", help="cria o arquivo PARAR")
    parar.add_argument("--agora", action="store_true", help="também envia SIGTERM ao processo")
    rep = sub.add_parser("reprocessar", help="reaplica o parser atual ao bruto já guardado")
    rep.add_argument("--desde", required=True, type=date.fromisoformat)
    rep.add_argument("--ate", type=date.fromisoformat, default=None)
    rep.add_argument("--tipo", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.versao:
        print(f"sociman-coletor {__version__} (protocolo {PROTOCOLO})")
        return 0
    if not args.comando:
        _parser().print_help()
        return 0
    try:
        cfg = config.carregar(args.config_dir)
    except config.ErroConfig as exc:
        print(f"erro de configuração ({exc.codigo}): {exc.mensagem}", file=sys.stderr)
        return 1
    logger = log.configurar(cfg.log.nivel, cfg.log.arquivo)
    comandos = {
        "rodar": cmd_rodar,
        "uma-vez": cmd_uma_vez,
        "dry-run": cmd_dry_run,
        "autoteste": cmd_autoteste,
        "perfil-iniciar": cmd_perfil_iniciar,
        "parar": cmd_parar,
        "reprocessar": cmd_reprocessar,
    }
    try:
        return comandos[args.comando](cfg, args)
    except config.ErroConfig as exc:
        logger.error("configuracao: %s", exc.codigo)
        print(f"erro de configuração ({exc.codigo}): {exc.mensagem}", file=sys.stderr)
        return 1
    except api.ParaServico as exc:
        logger.error("parando: %s", exc.codigo)
        print(exc.mensagem or exc.codigo, file=sys.stderr)
        return exc.codigo_saida


# ---- comandos ----


def _coletor(cfg: config.Config) -> Coletor:
    token = config.ler_token(cfg)
    return Coletor(cfg, token, adaptador_padrao())


def cmd_rodar(cfg: config.Config, _args: argparse.Namespace) -> int:
    return _coletor(cfg).rodar()


def cmd_uma_vez(cfg: config.Config, args: argparse.Namespace) -> int:
    if args.limite < 1:
        print("--limite precisa ser >= 1", file=sys.stderr)
        return 1
    return _coletor(cfg).uma_vez(args.limite, fora_da_janela=args.fora_da_janela)


def cmd_dry_run(cfg: config.Config, args: argparse.Namespace) -> int:
    token = config.ler_token(cfg)
    cliente = api.ClienteApi(cfg, token)
    try:
        fila = cliente.fila(args.limite, simular=True)
    finally:
        cliente.fechar()
    print(
        f"habilitada={fila.habilitada} dentro_da_janela={fila.janela.dentro} "
        f"fuso={fila.fuso} motivo_vazia={fila.motivo_vazia or '-'}"
    )
    print(
        f"limites: paginas/dia={fila.limites.paginas_dia} imagens/dia={fila.limites.imagens_dia} "
        f"itens/rodada={fila.limites.itens_por_coleta} pausa={fila.limites.pausa_min_s}.."
        f"{fila.limites.pausa_max_s}s"
    )
    print(
        f"orcamento: paginas restantes={fila.orcamento.paginas_restantes} "
        f"imagens restantes={fila.orcamento.imagens_restantes}"
    )
    for t in fila.tarefas:
        print(f"  {t.tipo:15} nivel={t.nivel} {t.chave}  {log.url_sem_query(t.url)}")
    print(f"{len(fila.tarefas)} tarefa(s); nada foi reservado, aberto ou enviado")
    return 0


def cmd_autoteste(cfg: config.Config, args: argparse.Namespace) -> int:
    falhas: list[str] = []
    avisos: list[str] = []
    print(f"config: {cfg.dir} api_url={cfg.api_url}")
    if cfg.ca_cert is not None and not cfg.ca_cert.exists():
        falhas.append(f"ca_cert não encontrado: {cfg.ca_cert}")
    elif cfg.ca_cert is None and cfg.api_url.startswith("https://"):
        avisos.append("sem ca_cert: a verificação TLS usa só as CAs do sistema")
    token = None
    if not args.sem_token:
        try:
            token = config.ler_token(cfg)
            print("token: ok (modo 600)")
        except config.ErroConfig as exc:
            falhas.append(f"token: {exc.codigo}: {exc.mensagem}")
    try:
        chrome = achar_chrome(cfg.chrome_bin)
        print(f"chrome: encontrado, versao={versao_chrome(chrome) or '?'}")
    except ErroNavegador as exc:
        falhas.append(f"chrome: {exc}")
    if cfg.perfil_dir.exists():
        print("perfil: " + ("livre" if Trava(cfg.perfil_dir).livre() else "EM USO"))
        if not Trava(cfg.perfil_dir).livre():
            falhas.append("perfil do Chrome em uso por outro processo")
    else:
        avisos.append("perfil do Chrome ainda não existe: rode perfil-iniciar")
    if config.tem_tela():
        print("sessao grafica: ok")
    else:
        falhas.append("sem DISPLAY/WAYLAND_DISPLAY: o coletor não abre o Chrome sem sessão gráfica")
    cliente = api.ClienteApi(cfg, token)  # sem token, o /health vai sem Authorization
    try:
        try:
            saude = cliente.health()
            print(f"api /health: {saude.get('status', '?')}")
        except api.ErroRede as exc:
            falhas.append(f"api: sem resposta ({exc}); confira api_url e a CA")
        except api.ErroApi as exc:
            falhas.append(f"api /health: {exc.status} {exc.codigo}")
        if token is not None:
            try:
                fila = cliente.fila(1, simular=True)
                print(
                    f"fila (simulada): habilitada={fila.habilitada} fuso={fila.fuso} "
                    f"tarefas={len(fila.tarefas)}"
                )
                local = datetime.now().astimezone().tzinfo
                servidor = ZoneInfo(fila.fuso)
                agora = datetime.now(servidor)
                if agora.utcoffset() != datetime.now(local).utcoffset():
                    avisos.append(
                        f"fuso local difere do servidor ({fila.fuso}); a janela segue o servidor"
                    )
            except api.ParaServico as exc:
                falhas.append(
                    {
                        "token_invalido": "token recusado (401): gere outro na tela de coleta",
                        "escopo_coleta": "token sem escopo de coleta (403)",
                        "coleta_suspensa": "cliente suspenso (403)",
                        "protocolo_coleta": f"atualize o coletor: {exc.mensagem}",
                    }.get(exc.codigo, f"{exc.status} {exc.codigo}")
                )
            except api.ColetaDesligada:
                avisos.append("coleta desligada no servidor (503); a fila fica vazia até ligar")
            except (api.ErroApi, api.ErroRede) as exc:
                falhas.append(f"fila: {exc}")
    finally:
        cliente.fechar()
    for a in avisos:
        print(f"aviso: {a}")
    if falhas:
        print("FALHAS:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("autoteste ok")
    return 0


def cmd_perfil_iniciar(cfg: config.Config, _args: argparse.Namespace) -> int:
    chrome = achar_chrome(cfg.chrome_bin)
    rede = adaptador_padrao()
    print("abrindo o Chrome no perfil dedicado; faça o login e feche a janela")
    perfil_iniciar(chrome, cfg.perfil_dir, rede.URL_LOGIN)
    print("perfil pronto")
    return 0


def cmd_parar(cfg: config.Config, args: argparse.Namespace) -> int:
    cfg.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    cfg.caminho_parar.touch()
    print("PARAR criado: a rodada atual termina a tarefa e fecha como interrompida")
    estado = Estado.carregar(cfg.caminho_estado)
    try:
        token = config.ler_token(cfg)
        cliente = api.ClienteApi(cfg, token)
        try:
            cliente.evento(
                modelos.Evento(tipo="parar_local", ocorreu_em=datetime.now().astimezone())
            )
        except (api.ErroApi, api.ErroRede):
            pass
        finally:
            cliente.fechar()
    except config.ErroConfig:
        pass
    if args.agora and estado.pid:
        try:
            os.kill(estado.pid, signal.SIGTERM)
            print(f"SIGTERM enviado ao processo {estado.pid}")
        except ProcessLookupError:
            print("nenhum processo do coletor em execução")
    return 0


def cmd_reprocessar(cfg: config.Config, args: argparse.Namespace) -> int:
    """Para cada rodada do período: baixa o bruto de cada item, reaplica o parser atual e
    reenvia por `…/itens` com `reprocessadoDe`. Não abre o Chrome."""
    token = config.ler_token(cfg)
    rede = adaptador_padrao()
    cliente = api.ClienteApi(cfg, token)
    logger = log.obter("reprocessar")
    ate = args.ate or date.today()
    invalidos = 0
    enviados = 0
    try:
        for resumo in cliente.listar_coletas(args.desde, ate):
            detalhe = cliente.detalhe_coleta(resumo.id)
            for item in detalhe.itens:
                if item.tarefa_id is None or item.status not in ("gravado", "repetido"):
                    continue
                if args.tipo and item.tipo != args.tipo:
                    continue
                try:
                    link = cliente.link_bruto(resumo.id, item.tarefa_id)
                    bruto = cliente.baixar_bruto(link.link)
                except api.ErroApi as exc:
                    logger.info("bruto indisponivel item=%d codigo=%s", item.id, exc.codigo)
                    continue
                resultado = rede.reprocessar(item.tipo, bruto, getattr(item, "fonte", None))
                if not resultado.tem_campos:
                    logger.info(
                        "reprocessar sem campos item=%d codigo=%s", item.id, resultado.erro_codigo
                    )
                    continue
                novo = modelos.Item(
                    tarefa_id=item.tarefa_id,
                    status="ok",
                    coletado_em=datetime.now().astimezone(),
                    esquema_versao=rede.esquema,
                    fonte=resultado.fonte,  # type: ignore[arg-type]
                    campos=resultado.campos,
                    bruto=None,
                    imagens=[],
                    reprocessado_de=item.id,
                )
                resposta = cliente.enviar_itens(resumo.id, [novo])
                enviados += 1
                for r in resposta.resultados:
                    if r.status == "invalido":
                        invalidos += 1
                    logger.info(
                        "reprocessado item=%d status=%s codigo=%s", item.id, r.status, r.erro_codigo
                    )
                time.sleep(0.6)  # respeita o limite por minuto do cliente (padrão 120/min)
    finally:
        cliente.fechar()
    print(f"reprocessados: {enviados}; invalidos: {invalidos}")
    return 2 if invalidos else 0


def caminho_config_padrao() -> Path:
    return config.DIR_PADRAO.expanduser()


if __name__ == "__main__":
    sys.exit(main())
