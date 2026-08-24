"""Regras determinísticas de PLD — tratamento de dados e sinalizações.

Espelha a lógica implementada no notebook do Nível 1, reaproveitada aqui
sobre a base maior (dados_nivel_2.json). A separação é deliberada:
TODA decisão numérica (limite, mediana, contagem) acontece em pandas;
o LLM só interpreta o resultado pronto.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

LIMITE_SOMA_DIA = 50_000.00   # Regra 1: soma do dia ultrapassa R$ 50 mil
LIMITE_OP_ISOLADA = 20_000.00  # Regra 1: nenhuma operação isolada atinge R$ 20 mil
MIN_OPS_NO_DIA = 3             # Regra 1: 3 ou mais operações no mesmo dia
FATOR_ATIPICO = 5.0            # Regra 2: valor > 5x a mediana do cliente
MIN_OPS_CLIENTE_REGRA2 = 4     # Regra 2: vale apenas para clientes com >= 4 operações


def carregar_e_limpar(caminho: str | Path) -> pd.DataFrame:
    """Carrega o JSON, remove duplicatas exatas e normaliza valores para BRL."""
    caminho = Path(caminho)
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    taxa = float(bruto["taxa_cambio_usd_brl"])

    df = pd.DataFrame(bruto["operacoes"])

    # --- Problema 1: IDs duplicados (registros regravados pelo sistema legado)
    # Remove apenas quando a linha inteira é idêntica; duplicata com dados
    # divergentes seria mantida e reportada, pois indicaria conflito real.
    antes = len(df)
    df = df.drop_duplicates(subset=["id"], keep="first").reset_index(drop=True)
    df.attrs["duplicatas_removidas"] = antes - len(df)

    # --- Problema 2: datas nulas ("data nao capturada pelo sistema")
    # Mantidas na base (volume/mediana continuam válidos), mas marcadas;
    # a Regra 1 ignora operações sem data porque o agrupamento por dia
    # seria artificial.
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["data_ausente"] = df["data"].isna()

    # --- Problema 3: valores em USD ("remessa internacional")
    # Normalizados ANTES de qualquer regra, usando a taxa fixa do próprio
    # arquivo. Fazer isso depois esconderia atípicos (ex.: OP-0013 no Nível 1).
    fator = pd.Series(1.0, index=df.index)
    fator[df["moeda"] == "USD"] = taxa
    df["valor_brl"] = (df["valor"] * fator).round(2)

    df.attrs["taxa_cambio_usd_brl"] = taxa
    return df


def regra_fracionamento(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Regra 1 — Fracionamento.

    Sinaliza (cliente, dia) com >= 3 operações cuja soma ultrapassa
    R$ 50 mil sem que nenhuma operação isolada atinja R$ 20 mil.
    Retorna o DataFrame com a flag por operação e o resumo dos dias sinalizados.
    """
    df = df.copy()
    df["flag_fracionamento"] = False

    validos = df.loc[~df["data_ausente"]]
    grupos = validos.groupby(["cliente_id", "data"], observed=True)["valor_brl"]
    resumo = grupos.agg(
        qtd_operacoes="count",
        soma_dia="sum",
        maior_op="max",
    ).reset_index()
    resumo = resumo[
        (resumo["qtd_operacoes"] >= MIN_OPS_NO_DIA)
        & (resumo["soma_dia"] > LIMITE_SOMA_DIA)
        & (resumo["maior_op"] < LIMITE_OP_ISOLADA)
    ].copy()

    if not resumo.empty:
        chave = resumo.set_index(["cliente_id", "data"]).index
        mascara = ~df["data_ausente"] & df.set_index(["cliente_id", "data"]).index.isin(chave)
        df.loc[mascara, "flag_fracionamento"] = True
    return df, resumo


def regra_valor_atipico(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame | pd.Series]:
    """Regra 2 — Valor atípico.

    Operação com valor_brl superior a 5x a mediana do próprio cliente,
    aplicada somente a clientes com 4 ou mais operações.
    """
    df = df.copy()
    df["flag_valor_atipico"] = False

    tam = df.groupby("cliente_id")["valor_brl"].transform("size")
    mediana = df.groupby("cliente_id")["valor_brl"].transform("median")
    elegivel = tam >= MIN_OPS_CLIENTE_REGRA2
    df.loc[elegivel, "flag_valor_atipico"] = (
        df.loc[elegivel, "valor_brl"] > FATOR_ATIPICO * mediana[elegivel]
    )
    return df, df.groupby("cliente_id")["valor_brl"].median()


def clientes_mais_sinalizados(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Ranking de clientes por número de operações sinalizadas.

    Critério: contagem de operações marcadas por qualquer regra;
    desempate pelo volume total transacionado em BRL.
    """
    df = df.copy()
    df["sinalizada"] = df["flag_fracionamento"] | df["flag_valor_atipico"]

    grp = df.groupby("cliente_id")
    ranking = pd.DataFrame(
        {
            "sinalizacoes": grp["sinalizada"].sum(),
            "volume_total_brl": grp["valor_brl"].sum(),
            "qtd_operacoes": grp["id"].count(),
        }
    ).reset_index()

    # Duas ordenações estáveis: desempate por volume, depois por sinalizações.
    elegidos = ranking[ranking["sinalizacoes"] > 0]
    elegidos = elegidos.sort_values(by="volume_total_brl", ascending=False)
    elegidos = elegidos.sort_values(by="sinalizacoes", ascending=False)
    return elegidos.head(top_n).reset_index(drop=True)


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent / "dados"
    df = carregar_e_limpar(base / "dados_nivel_2.json")
    print(f"Operações após limpeza: {len(df)} (removidas {df.attrs['duplicatas_removidas']} duplicatas)")
    df, dias = regra_fracionamento(df)
    df, _ = regra_valor_atipico(df)
    print(f"Dias com fracionamento: {len(dias)}")
    print(f"Ops atípicas: {df['flag_valor_atipico'].sum()}")
    print(clientes_mais_sinalizados(df).to_string(index=False))
