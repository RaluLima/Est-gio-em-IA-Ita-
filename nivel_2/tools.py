"""Ferramentas que consultam a base de operações — consumidas pelo agente.

Cada ferramenta devolve um dicionário serializável em JSON. TODO cálculo
(agregação, mediana, contagem) acontece AQUI, deterministicamente em pandas;
o agente/LLM apenas decide qual ferramenta chamar e interpreta o resultado.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from regras import (
    carregar_e_limpar,
    clientes_mais_sinalizados,
    regra_fracionamento,
    regra_valor_atipico,
)

PASTA_DADOS = Path(__file__).resolve().parent.parent / "dados" / "dados_nivel_2.json"


@lru_cache(maxsize=1)
def _carregar_estado() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carrega e prepara a base uma única vez (limpeza + regras aplicadas)."""
    df = carregar_e_limpar(PASTA_DADOS)
    df, dias = regra_fracionamento(df)
    df, _ = regra_valor_atipico(df)
    return df, dias


def _base() -> pd.DataFrame:
    return _carregar_estado()[0]


def _formatar_data(valor) -> str | None:
    ts = pd.Timestamp(valor)
    return None if pd.isna(ts) else ts.strftime("%Y-%m-%d")


def historico_cliente(cliente_id: str) -> dict:
    """Resumo agregado das operações do cliente, incluindo sinalizações."""
    base = _base()
    cli = base[base["cliente_id"] == cliente_id]
    if cli.empty:
        raise ValueError(f"Cliente {cliente_id} nao encontrado na base.")

    datas = cli.loc[~cli["data_ausente"], "data"]
    dias_frac = _carregar_estado()[1]
    dias_suspeitos = [
        {
            "data": linha["data"].strftime("%Y-%m-%d"),
            "qtd_operacoes": int(linha["qtd_operacoes"]),
            "soma_dia_brl": round(float(linha["soma_dia"]), 2),
            "maior_op_brl": round(float(linha["maior_op"]), 2),
        }
        for _, linha in dias_frac[dias_frac["cliente_id"] == cliente_id].iterrows()
    ]
    atipicas = cli[cli["flag_valor_atipico"]]

    return {
        "cliente_id": cliente_id,
        "qtd_operacoes": int(len(cli)),
        "volume_total_brl": round(float(cli["valor_brl"].sum()), 2),
        "ticket_medio_brl": round(float(cli["valor_brl"].mean()), 2),
        "mediana_brl": round(float(cli["valor_brl"].median()), 2),
        "primeira_operacao": _formatar_data(datas.min()) if not datas.empty else None,
        "ultima_operacao": _formatar_data(datas.max()) if not datas.empty else None,
        "moedas_utilizadas": sorted(cli["moeda"].unique().tolist()),
        "operacoes_sem_data": int(cli["data_ausente"].sum()),
        "sinalizacoes": {
            "ops_em_dias_de_fracionamento": int(cli["flag_fracionamento"].sum()),
            "dias_com_fracionamento": dias_suspeitos,
            "ops_com_valor_atipico": int(cli["flag_valor_atipico"].sum()),
            "detalhe_ops_atipicas": [
                {
                    "id": linha["id"],
                    "data": _formatar_data(linha["data"]),
                    "valor_brl": float(linha["valor_brl"]),
                    "razao_vs_mediana": round(
                        float(linha["valor_brl"]) / float(cli["valor_brl"].median()), 1
                    ),
                    "canal": linha["canal"],
                    "tipo": linha["tipo"],
                }
                for _, linha in atipicas.iterrows()
            ],
        },
    }


def operacoes_do_dia(cliente_id: str, data: str) -> dict:
    """Recorte de todas as operações do cliente em um dia específico (AAAA-MM-DD)."""
    base = _base()
    alvo = pd.Timestamp(data)
    cli = base[(base["cliente_id"] == cliente_id) & (base["data"] == alvo)]
    if cli.empty:
        raise ValueError(f"Sem operacoes de {cliente_id} em {data}.")

    operacoes = [
        {
            "id": linha["id"],
            "valor_brl": float(linha["valor_brl"]),
            "moeda_original": linha["moeda"],
            "canal": linha["canal"],
            "tipo": linha["tipo"],
            "contraparte": linha["contraparte"],
        }
        for _, linha in cli.iterrows()
    ]
    return {
        "cliente_id": cliente_id,
        "data": data,
        "qtd_operacoes": len(operacoes),
        "soma_dia_brl": round(float(cli["valor_brl"].sum()), 2),
        "maior_op_brl": round(float(cli["valor_brl"].max()), 2),
        "operacoes": operacoes,
    }


def perfil_canal(cliente_id: str) -> dict:
    """Distribuição do uso de canais pelo cliente (contagem e volume)."""
    base = _base()
    cli = base[base["cliente_id"] == cliente_id]
    if cli.empty:
        raise ValueError(f"Cliente {cliente_id} nao encontrado na base.")

    volume_total = float(cli["valor_brl"].sum())
    agrupado = (
        cli.groupby("canal")
        .agg(qtd=("id", "count"), volume_brl=("valor_brl", "sum"))
        .sort_values("volume_brl", ascending=False)
    )
    canais = [
        {
            "canal": canal,
            "qtd_operacoes": int(linha["qtd"]),
            "volume_brl": round(float(linha["volume_brl"]), 2),
            "pct_do_volume": round(100 * float(linha["volume_brl"]) / volume_total, 1),
        }
        for canal, linha in agrupado.iterrows()
    ]
    return {"cliente_id": cliente_id, "canais": canais}


def top_clientes(n: int = 10) -> pd.DataFrame:
    """Ranking dos clientes mais sinalizados pelas regras determinísticas."""
    return clientes_mais_sinalizados(_base(), top_n=n)


# --- Registro consultável pelo agente ---------------------------------------
FERRAMENTAS = {
    "historico_cliente": {
        "funcao": historico_cliente,
        "descricao": (
            "Resumo agregado do cliente: volume, mediana, período, moedas, "
            "operações sinalizadas pelas regras e dias suspeitos."
        ),
        "argumentos": ["cliente_id"],
    },
    "operacoes_do_dia": {
        "funcao": operacoes_do_dia,
        "descricao": (
            "Detalha todas as operações do cliente em um dia específico "
            "(argumentos: cliente_id, data 'AAAA-MM-DD'). Útil para examinar "
            "concentração diária e contrapartes."
        ),
        "argumentos": ["cliente_id", "data"],
    },
    "perfil_canal": {
        "funcao": perfil_canal,
        "descricao": (
            "Distribuição de uso dos canais (pix, ted, boleto, cartao, especie) "
            "por contagem e volume."
        ),
        "argumentos": ["cliente_id"],
    },
}


def executar_ferramenta(nome: str, argumentos: dict) -> dict:
    """Executa uma ferramenta registrada validando os argumentos obrigatórios."""
    if nome not in FERRAMENTAS:
        raise ValueError(f"Ferramenta desconhecida: {nome}. Disponiveis: {list(FERRAMENTAS)}")
    obrigatorios = FERRAMENTAS[nome]["argumentos"]
    faltando = [a for a in obrigatorios if a not in argumentos]
    if faltando:
        raise ValueError(f"Argumentos obrigatorios ausentes para {nome}: {faltando}")
    return FERRAMENTAS[nome]["funcao"](**argumentos)
