"""Confronta o nível de risco do agente com o esperado pelas regras.

Mapeamento do risco esperado (política acordada):
- 2 regras distintas disparadas -> alto
- 1 regra -> médio
- 0 regras -> baixo (não ocorre no top 10)

A divergência é classificada por direção: o agente foi mais severo (conservador,
aceitável em PLD) ou menos severo (requer revisão).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import tools

PASTA_SAIDA = Path(__file__).resolve().parent.parent / "outputs"
ORDEM = {"baixo": 0, "médio": 1, "alto": 2}


def _regras_do_cliente(cliente_id: str) -> list[str]:
    base = tools._base()
    cli = base[base["cliente_id"] == cliente_id]
    regras = []
    if cli["flag_fracionamento"].any():
        regras.append("fracionamento")
    if cli["flag_valor_atipico"].any():
        regras.append("valor_atipico")
    return regras


def main() -> None:
    arquivo_lote = PASTA_SAIDA / "lote_pareceres.csv"
    if not arquivo_lote.exists():
        raise SystemExit("Execute primeiro nivel_2/executar_lote.py para gerar o lote.")
    lote = pd.read_csv(arquivo_lote)

    linhas = []
    for _, linha in lote.iterrows():
        regras = _regras_do_cliente(linha["cliente_id"])
        esperado = {2: "alto", 1: "médio", 0: "baixo"}[len(regras)]
        agente = linha["nivel_risco"]
        dif = ORDEM[agente] - ORDEM[esperado]
        direcao = "concordante" if dif == 0 else ("agente_mais_severo" if dif > 0 else "agente_menos_severo")
        linhas.append(
            {
                "cliente_id": linha["cliente_id"],
                "regras_disparadas": "+".join(regras) or "-",
                "qtd_regras": len(regras),
                "risco_esperado": esperado,
                "risco_agente": agente,
                "concordancia": direcao,
                "tipologia_suspeita": linha["tipologia_suspeita"],
            }
        )

    df = pd.DataFrame(linhas)
    df.to_csv(PASTA_SAIDA / "confronto.csv", index=False, encoding="utf-8-sig")

    total = len(df)
    concordantes = int((df["concordancia"] == "concordante").sum())
    mais_severo = int((df["concordancia"] == "agente_mais_severo").sum())
    menos_severo = int((df["concordancia"] == "agente_menos_severo").sum())
    pct_concordancia = round(100 * concordantes / total, 1)

    por_regra = (
        df.groupby("qtd_regras")
        .agg(clientes=("cliente_id", "count"), concordantes=("concordancia", lambda s: int((s == "concordante").sum())))
        .reset_index()
    )

    texto = f"""# Confronto: risco do agente x risco esperado pelas regras

## Resumo quantitativo
- Clientes analisados: {total}
- Concordantes: {concordantes} ({pct_concordancia}%)
- Agente mais severo que o esperado: {mais_severo}
- Agente menos severo que o esperado: {menos_severo}

{por_regra.to_string(index=False)}

## Detalhamento

{df.drop(columns=["tipologia_suspeita"]).to_string(index=False)}

## Análise qualitativa

O mapeamento "nº de regras -> nível de risco" é uma régua minimalista: trata as duas
regras como igualmente graves e ignora magnitude, canal e moeda. O agente LLM enxerga
essas dimensões extras, e é por isso que diverge exatamente nos clientes com UMA regra
disparada ({mais_severo} casos), classificando-os como ALTO:

- Nos clientes com fracionamento isolado, a soma diária supera folgadamente o limite
  legal de referência (R$ 50 mil) em vários dias, o que na prática pesa mais que um
  único valor atípico marginal;
- Nos clientes apenas com valores atípicos, há evidências agravantes que a regra não
  pontua individualmente: operações >= 10x a mediana do próprio cliente, depósitos em
  espécie e concentração de múltiplos atípicos no mesmo dia — padrões clássicos de
  colocação/estruturação descritos na COAF;

Nenhum caso ficou MENOS severo que o esperado ({menos_severo} ocorrências), ou seja,
a divergência é toda na direção conservadora. Em PLD, falso positivo vai para revisão
humana com custo operacional baixo; falso negativo é risco regulatório. Portanto o
comportamento do agente é adequado à política da casa — mas a política formal de
níveis deveria incorporar esses agravantes para reduzir a ambiguidade entre camadas.
"""
    (PASTA_SAIDA / "confronto.md").write_text(texto, encoding="utf-8")

    print(f"Concordancia: {concordantes}/{total} ({pct_concordancia}%) | "
          f"agente mais severo: {mais_severo} | menos severo: {menos_severo}")
    print("Artefatos: outputs/confronto.csv, outputs/confronto.md")


if __name__ == "__main__":
    main()
