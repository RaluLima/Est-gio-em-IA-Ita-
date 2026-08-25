# Uso de IA neste desafio

Transparência total sobre onde IA foi usada, como e com quais salvaguardas.

## 1. IA como par de programação

O código deste repositório foi desenvolvido com auxílio de um assistente de IA
(opencode), sob minha direção: interpretei o enunciado, validei cada número contra
os dados brutos, revisei decisões de design e executei tudo localmente. Exemplo
concreto de erro da IA corrigido por validação: a primeira sugestão aplicava a
Regra 2 **antes** da conversão USD→BRL — o teste numérico mostrou que CLI-A-4
(US$ 12.000 ≈ R$ 64.800) escaparia da sinalização; a ordem foi corrigida e virou
assert de validação no notebook.

## 2. LLM dentro do produto (pipeline)

O desafio propõe um processo híbrido regras + LLM. Sem chave de API gratuita no
início, construí primeiro backends offline honestos; em seguida instalei um LLM
real 100% local ([Ollama](https://ollama.com) + `llama3.2:3b`, camada gratuita
do enunciado) e **reexecutei os dois níveis com chamadas reais** — os caches e
outputs commitados são desta execução final:

### Nível 1 — Parte B do notebook com LLM real
- O notebook chama `chamar_llm()` contra o Ollama local; as entradas de
  `llm_cache/nivel1_*.json` têm `"origem": "api"` com tokens/latência reais;
- A falha estrutural demonstrada é genuína: o prompt v1 (pergunta aberta) fez o
  modelo responder em prosa livre, violando o contrato JSON — o retry corretivo
  converteu a resposta em um `ParecerLLM` válido; o prompt v2 (contrato
  explícito) entregou JSON válido de primeira;
- A comparação v1 × v2 na tabela final usa as métricas reais dessas chamadas
  (tokens e latência medidas pelo SDK);
- Histórico: antes do LLM local existir neste projeto, essas respostas eram
  pré-geradas offline e revisadas por mim contra os fatos calculados em pandas —
  o design cache-first manteve o código idêntico na troca.

### Nível 2 — agente com LLM real, backend offline como fallback
- Os 10 clientes sinalizados foram processados pelo agente com chamadas reais ao
  Ollama (~11,7 mil tokens; métricas completas em `outputs/custos_resumo.csv`);
- O backend `offline` permanece disponível: mesmo loop decidir→agir→observar,
  com política determinística documentada (`docs/DECISOES.md`, item 8);
- Integração via SDK OpenAI-compatível (`nivel_2/llm_client.py`):
  Groq/Gemini/OpenRouter/Ollama — basta trocar `.env`.

## 3. Salvaguardas

- Todo número em qualquer parecer vem de resultado de ferramenta pandas — o LLM
  é proibido pelo prompt de inventar valores;
- Saída do LLM sempre validada por schema pydantic antes de virar registro;
- Cache commitado permite auditar exatamente qual texto entrou em cada entrega;
- Nenhum dado sensível real foi usado (dataset sintético do desafio).
