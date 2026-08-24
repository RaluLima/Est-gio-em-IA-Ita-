"""Agente de triagem: LLM decide quais ferramentas chamar e emite parecer.

Separação de responsabilidades (exigida pelo desafio):
- tools.py calcula TUDO deterministicamente em pandas;
- o LLM só decide a sequência de ferramentas e interpreta os resultados;
- a saída final é validada contra o contrato ParecerLLM (modelos.py).

Dois backends com a mesma interface:
- "api": chamada real a um provedor compatível com OpenAI (cache-first);
- "offline": política determinística pré-acordada, usada quando não há chave
  de API — mantém o pipeline executável e auditável sem custo.
"""
from __future__ import annotations

import argparse
import json

from modelos import DecisaoFerramenta, DecisaoFinal, ParecerLLM
import tools
from llm_client import chave_disponivel, chamar_llm, extrair_json

MAX_PASSOS = 5
MAX_TENTATIVAS_PARSE = 2

SYSTEM_PROMPT = """Você é um analista de PLD (Prevenção à Lavagem de Dinheiro) de uma fintech.
Sua tarefa é investigar UM cliente sinalizado por regras determinísticas e emitir um parecer.

Ferramentas disponíveis (você as aciona devolvendo APENAS um JSON):
{"acao": "ferramenta", "ferramenta": "<nome>", "argumentos": {...}}
"""
for nome, spec in tools.FERRAMENTAS.items():
    SYSTEM_PROMPT += f'- {nome}({", ".join(spec["argumentos"])}): {spec["descricao"]}\n'
SYSTEM_PROMPT += """
Quando tiver evidências suficientes, responda APENAS:
{"acao": "parecer_final", "nivel_risco": "baixo"|"médio"|"alto",
 "tipologia_suspeita": "...", "red_flags": ["..."], "justificativa": "..."}

Regras estritas:
- Responda SOMENTE com um único objeto JSON, sem texto antes ou depois.
- NUNCA invente números: cite apenas valores presentes nos resultados das ferramentas.
- Investigue no máximo 3 ferramentas antes do parecer_final.
- Valores em BRL já consideram conversão de USD pela taxa 5.4."""


# --- Backends -----------------------------------------------------------------
def _decidir_via_llm(contexto: dict, passo: int) -> tuple[dict, dict]:
    """Pede a decisão ao provedor real (cache-first), com retry corretivo."""
    mensagens = contexto["mensagens"]
    for tentativa in range(MAX_TENTATIVAS_PARSE):
        case_key = f"{contexto['case_key']}_passo{passo}"
        if tentativa > 0:
            case_key += "_retry"
        user = json.dumps(mensagens, ensure_ascii=False)
        texto, metricas = chamar_llm(case_key, SYSTEM_PROMPT, user)
        try:
            return json.loads(extrair_json(texto)), metricas
        except (ValueError, json.JSONDecodeError) as erro:
            mensagens.append(
                {
                    "papel": "erro_parse",
                    "detalhe": str(erro),
                    "instrucao": "Reenvie SOMENTE um objeto JSON válido no protocolo.",
                }
            )
    raise RuntimeError(f"LLM nao devolveu JSON valido apos {MAX_TENTATIVAS_PARSE} tentativas.")


def _parecer_offline(resultados: list[dict], cliente_id: str) -> dict:
    """Política determinística acordada para o modo offline.

    ALTO se: fracionamento OU atípico >=10x mediana OU >=2 atípicos no mesmo dia
    OU atípico em espécie. Caso contrário MÉDIO. Nunca BAIXO para clientes que
    chegaram até o agente (todos têm ao menos uma regra disparada).
    """
    hist = next(r for r in resultados if r["ferramenta"] == "historico_cliente")["resultado"]
    sinais = hist["sinalizacoes"]
    red_flags: list[str] = []
    tipologias: list[str] = []
    forte = False

    for dia in sinais["dias_com_fracionamento"]:
        forte = True
        tipologias.append("Fracionamento de valores")
        red_flags.append(
            f"{dia['qtd_operacoes']} operacoes em {dia['data']} somando "
            f"R$ {dia['soma_dia_brl']:.2f}, nenhuma isolada >= R$ 20.000,00"
        )

    datas_atipicas: dict[str | None, int] = {}
    for op in sinais["detalhe_ops_atipicas"]:
        red_flags.append(
            f"{op['id']} ({op['data']}): R$ {op['valor_brl']:.2f} via {op['canal']} "
            f"[{op['tipo']}] = {op['razao_vs_mediana']}x a mediana do cliente"
        )
        datas_atipicas[op["data"]] = datas_atipicas.get(op["data"], 0) + 1
        if op["razao_vs_mediana"] >= 10 or op["canal"] == "especie":
            forte = True

    if sinais["ops_com_valor_atipico"]:
        tipologias.append("Valores atípicos frente ao perfil do cliente")
    if any(qtd >= 2 for qtd in datas_atipicas.values()):
        forte = True
        dias_multi = [d for d, q in datas_atipicas.items() if q >= 2]
        red_flags.append(
            f"Multiplos valores atipicos concentrados no(s) dia(s) {', '.join(str(x) for x in dias_multi)}"
        )
    moedas = hist.get("moedas_utilizadas", [])
    if len(moedas) > 1:
        red_flags.append(f"Operacoes em multiplas moedas: {', '.join(moedas)}")

    nivel = "alto" if forte else "médio"
    justificativa = (
        f"Cliente {cliente_id} apresenta {hist['qtd_operacoes']} operacoes somando "
        f"R$ {hist['volume_total_brl']:.2f} (mediana R$ {hist['mediana_brl']:.2f}). "
        + ("; ".join(tipologias) + ". " if tipologias else "")
        + f"Evidencias conferem com nivel de risco {nivel.upper()} conforme politica de triagem."
    )
    return {
        "acao": "parecer_final",
        "nivel_risco": nivel,
        "tipologia_suspeita": "; ".join(tipologias) or "Comportamento atipico",
        "red_flags": red_flags,
        "justificativa": justificativa,
    }


def _decidir_offline(contexto: dict, passo: int) -> tuple[dict, dict]:
    """Mesma interface do backend API, mas com roteiro determinístico."""
    metricas = {"origem": "offline_policy", "tokens_prompt": None, "tokens_resposta": None}
    resultados = contexto["resultados"]
    cliente_id = contexto["cliente_id"]

    if not resultados:
        decisao = {"acao": "ferramenta", "ferramenta": "historico_cliente",
                   "argumentos": {"cliente_id": cliente_id}}
    elif len(resultados) == 1:
        hist = resultados[0]["resultado"]["sinalizacoes"]
        if hist["dias_com_fracionamento"]:
            pior = max(hist["dias_com_fracionamento"], key=lambda d: d["soma_dia_brl"])
            decisao = {"acao": "ferramenta", "ferramenta": "operacoes_do_dia",
                       "argumentos": {"cliente_id": cliente_id, "data": pior["data"]}}
        else:
            decisao = {"acao": "ferramenta", "ferramenta": "perfil_canal",
                       "argumentos": {"cliente_id": cliente_id}}
    else:
        decisao = _parecer_offline(resultados, cliente_id)

    metricas["latencia_ms"] = 0
    return decisao, metricas


# --- Loop principal -------------------------------------------------------------
def executar_agente(cliente_id: str, backend: str = "auto") -> dict:
    """Executa o ciclo decidir -> agir -> observar ate o parecer final validado."""
    if backend == "auto":
        backend = "api" if chave_disponivel() else "offline"

    contexto = {
        "cliente_id": cliente_id,
        "backend": backend,
        "case_key": f"nivel2_{cliente_id.lower()}",
        "mensagens": [
            {"papel": "tarefa", "texto": f"Investigue o cliente {cliente_id} e emita o parecer."},
        ],
        "resultados": [],
        "metricas": [],
    }

    for passo in range(1, MAX_PASSOS + 1):
        decidir = _decidir_via_llm if backend == "api" else _decidir_offline
        decisao_bruta, metricas = decidir(contexto, passo)
        contexto["metricas"].append({"passo": passo, **metricas})

        if decisao_bruta.get("acao") == "parecer_final":
            parecer = ParecerLLM.model_validate(decisao_bruta)
            return {"cliente_id": cliente_id, "backend": backend, "passos": passo,
                    "parecer": parecer.model_dump(), "metricas": contexto["metricas"]}

        chamada = DecisaoFerramenta.model_validate(decisao_bruta)
        try:
            resultado = tools.executar_ferramenta(chamada.ferramenta, chamada.argumentos)
            contexto["mensagens"].append({
                "papel": "chamada_ferramenta",
                "ferramenta": chamada.ferramenta,
                "argumentos": chamada.argumentos,
            })
            contexto["mensagens"].append({
                "papel": "resultado_ferramenta",
                "ferramenta": chamada.ferramenta,
                "dados": resultado,
            })
            contexto["resultados"].append(
                {"ferramenta": chamada.ferramenta, "argumentos": chamada.argumentos,
                 "resultado": resultado}
            )
        except ValueError as erro:
            contexto["mensagens"].append({
                "papel": "erro_ferramenta",
                "ferramenta": chamada.ferramenta,
                "erro": str(erro),
            })

    raise RuntimeError(
        f"Agente excedeu {MAX_PASSOS} passos sem parecer final para {cliente_id}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente de triagem PLD (nivel 2).")
    parser.add_argument("--cliente", help="ID do cliente, ex.: CLI-029")
    parser.add_argument("--backend", choices=["auto", "api", "offline"], default="auto")
    parser.add_argument("--listar-top10", action="store_true",
                        help="Mostra o ranking dos clientes mais sinalizados.")
    args = parser.parse_args()

    if args.listar_top10:
        print(tools.top_clientes(10).to_string(index=False))
        return
    if not args.cliente:
        parser.error("Informe --cliente ou use --listar-top10.")

    relatorio = executar_agente(args.cliente, args.backend)
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
