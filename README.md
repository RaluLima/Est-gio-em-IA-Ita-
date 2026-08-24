# Desafio Estágio IA — Sistema de Triagem PLD

Processo de triagem antifraude/lavagem (PLD) que combina **regras determinísticas
em pandas** com um **agente LLM** que investiga clientes sinalizados usando ferramentas.

## Estrutura

```
dados/                  dados brutos fornecidos (nivel_1 e nivel_2)
nivel_1/nivel_1.ipynb   notebook JÁ EXECUTADO (Parte A: regras | Parte B: parecer LLM)
nivel_2/
  regras.py             limpeza, dedup, conversão USD->BRL, Regra 1 (fracionamento),
                        Regra 2 (valor atípico) e ranking top-10
  tools.py              ferramentas consultáveis pelo agente (tudo calculado em pandas)
  modelos.py            contratos pydantic (parecer e decisões do agente)
  llm_client.py         cliente provedor-agnóstico com cache-first (Groq/Gemini/OpenRouter/Ollama)
  agente.py             loop decidir->agir->observar; backends api/offline
  executar_lote.py      roda o agente no top-10 e consolida métricas
  confronto.py          risco do agente x risco esperado pelas regras (+ análise qualitativa)
outputs/                pareceres, custos/latência e confronto (commitados)
llm_cache/              respostas de LLM reaproveitadas (cache-first)
docs/                   DECISOES.md e USO_DE_IA.md
```

## Como rodar

```bash
pip install -r requirements.txt

# Nivel 1 — notebook ja vem executado; para reexecutar: jupyter lab nivel_1/nivel_1.ipynb

# Nivel 2
python nivel_2/regras.py                      # limpeza + regras + top-10
python nivel_2/agente.py --cliente CLI-029    # investigacao de 1 cliente
python nivel_2/executar_lote.py               # top-10 -> outputs/
python nivel_2/confronto.py                   # comparacao com risco esperado -> outputs/
```

### Usar um LLM real (opcional)

Sem configuração, o agente usa o backend `offline` (política determinística
documentada em `docs/DECISOES.md`). Para chamadas reais, copie `.env.example`
para `.env` e escolha um provedor compatível com o SDK OpenAI:

```env
LLM_PROVIDER=groq            # groq | gemini | openrouter | ollama
LLM_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=...
```

Respostas anteriores são servidas de `llm_cache/` (economia de cota); novas
perguntas vão para a API e entram no cache automaticamente.

## Resultados principais

- **Nível 2**: 322 operações -> 317 válidas (5 IDs duplicados removidos), 7 convertidas
  de USD, 4 dias de fracionamento, 21 valores atípicos.
- **Top 10** sinalizados processados pelo agente: todos classificados **ALTO**, com
  red flags objetivas citando IDs, datas, valores e razão vs mediana.
- **Confronto**: nenhuma divergência na direção perigosa (agente nunca menos severo
  que a régua minimalista); análise completa em `outputs/confronto.md`.

Detalhes e trade-offs: [`docs/DECISOES.md`](docs/DECISOES.md).
Transparência sobre uso de IA: [`docs/USO_DE_IA.md`](docs/USO_DE_IA.md).
