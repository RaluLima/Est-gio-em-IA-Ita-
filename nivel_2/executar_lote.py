"""Executa o agente sobre os clientes mais sinalizados e consolida resultados.

Artefatos gerados em outputs/:
- lote_pareceres.json / lote_pareceres.csv : 1 registro por cliente;
- custos_latencia.csv : métricas de cada chamada ao LLM (ou passo offline);
- custos_resumo.csv : agregação de custo/latência por origem.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import tools
from agente import executar_agente

PASTA_SAIDA = Path(__file__).resolve().parent.parent / "outputs"


def main() -> None:
    PASTA_SAIDA.mkdir(exist_ok=True)
    ranking = tools.top_clientes(10)
    clientes = ranking["cliente_id"].tolist()
    print(f"Processando {len(clientes)} clientes: {', '.join(clientes)}")

    relatorios = [executar_agente(c) for c in clientes]

    registros = []
    linhas_custo = []
    for rel in relatorios:
        parecer = rel["parecer"]
        registros.append(
            {
                "cliente_id": rel["cliente_id"],
                "nivel_risco": parecer["nivel_risco"],
                "tipologia_suspeita": parecer["tipologia_suspeita"],
                "qtd_red_flags": len(parecer["red_flags"]),
                "red_flags": " | ".join(parecer["red_flags"]),
                "justificativa": parecer["justificativa"],
                "backend": rel["backend"],
                "passos": rel["passos"],
            }
        )
        for m in rel["metricas"]:
            linhas_custo.append(
                {
                    "cliente_id": rel["cliente_id"],
                    "passo": m["passo"],
                    "origem": m["origem"],
                    "tokens_prompt": m["tokens_prompt"],
                    "tokens_resposta": m["tokens_resposta"],
                    "latencia_ms": m["latencia_ms"],
                }
            )

    df_lote = pd.DataFrame(registros)
    df_lote.to_csv(PASTA_SAIDA / "lote_pareceres.csv", index=False, encoding="utf-8-sig")
    (PASTA_SAIDA / "lote_pareceres.json").write_text(
        json.dumps(relatorios, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    df_custo = pd.DataFrame(linhas_custo)
    df_custo.to_csv(PASTA_SAIDA / "custos_latencia.csv", index=False, encoding="utf-8-sig")
    resumo = (
        df_custo.groupby("origem")
        .agg(
            chamadas=("latencia_ms", "count"),
            tokens_prompt_total=("tokens_prompt", "sum"),
            tokens_resposta_total=("tokens_resposta", "sum"),
            latencia_media_ms=("latencia_ms", "mean"),
            latencia_max_ms=("latencia_ms", "max"),
            latencia_total_ms=("latencia_ms", "sum"),
        )
        .round(1)
        .reset_index()
    )
    resumo.to_csv(PASTA_SAIDA / "custos_resumo.csv", index=False, encoding="utf-8-sig")

    print("\n== Pareces ==")
    print(df_lote[["cliente_id", "nivel_risco", "tipologia_suspeita"]].to_string(index=False))
    print("\n== Custos / latencia ==")
    print(resumo.to_string(index=False))


if __name__ == "__main__":
    main()
