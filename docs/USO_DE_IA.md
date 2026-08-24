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

O desafio propõe um processo híbrido regras + LLM. Como não havia chave de API
gratuita disponível no período, adotei uma arquitetura honesta em duas camadas:

### Nível 1 — pareceres pré-gerados em cache
- O código chama `llm_client.chamar_llm()` exatamente como chamaria um provedor real;
- As entradas de `llm_cache/*.json` contêm prompt completo + resposta, no MESMO
  formato de retorno de API (incluindo campos `usage`), marcadas com
  `"origem": "pre_gerado_offline"`;
- As respostas foram redigidas pelo assistente de IA seguindo o contrato JSON
  (`ParecerLLM`) e revisadas por mim contra os fatos calculados em pandas;
- Inclui deliberadamente um caso de falha (`nivel1_cli_a_1_v1.json`: resposta em
  prosa que viola o contrato) para demonstrar o retry corretivo funcionando.

### Nível 2 — backend offline determinístico
- O agente mantém o loop decidir→agir→observar idêntico ao modo API, mas as
  decisões vêm de uma política fixa e documentada (`docs/DECISOES.md`, item 8),
  não de invenção livre;
- Métricas de custo/latência saem com tokens nulos e `origem=offline_policy`,
  deixando claro nos outputs (`outputs/custos_resumo.csv`) que nenhuma chamada
  real foi feita;
- A integração real está implementada (`nivel_2/llm_client.py`, SDK OpenAI-
  compatível com Groq/Gemini/OpenRouter/Ollama): basta preencher `.env`.

## 3. Salvaguardas

- Todo número em qualquer parecer vem de resultado de ferramenta pandas — o LLM
  é proibido pelo prompt de inventar valores;
- Saída do LLM sempre validada por schema pydantic antes de virar registro;
- Cache commitado permite auditar exatamente qual texto entrou em cada entrega;
- Nenhum dado sensível real foi usado (dataset sintético do desafio).
