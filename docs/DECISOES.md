# Decisões e Trade-offs

## Dados

### 1. Deduplicação por ID exato antes de qualquer cálculo
IDs repetidos são o mesmo evento registrado duas vezes; somá-los inflaria volumes
e criaria falsos positivos (ex.: CLI-A-3 no nível 1 passa de R$ 48.500 para
R$ 65.700 com a duplicata — acima do limite da Regra 1). Mantive a **primeira**
ocorrência e registrei quantas foram descartadas.

### 2. Conversão USD→BRL antes das regras
Todas as comparações (limites, medianas) acontecem em BRL. Converter depois faria
operações em USD escaparem da Regra 2 (CLI-A-4 no nível 1 é o contra-exemplo:
US$ 12.000 = R$ 64.800, ~10x a mediana). Taxa fixa de 5.4 conforme enunciado;
numa impl real seria taxa da data da operação.

### 3. Operações sem data ficam fora da Regra 1, mas não somem
A Regra 1 agrupa por dia — sem data é impossível aplicar. As operações continuam
na base para volume, mediana e Regra 2 (que não depende de data). No nível 1,
OP-0017 segue visível nas estatísticas do notebook.

### 4. Mediana inclui os próprios valores atípicos
Escolhi a mediana do cliente **com** todas as operações: é a definição mais simples
e auditável. O efeito é conservador na direção oposta (infla um pouco a mediana,
reduzindo atípicos) — aceitável porque a Regra 2 já usa fator 5x.

## Nível 2

### 5. Ranking top-10 com desempate por volume BRL
Critério primário: nº de operações sinalizadas; desempate: volume total em BRL.
Entre empatados além do 10º lugar o corte é arbitrário por natureza — CLI-026
ficou fora por desempate. Documentado como limitação; em produção eu reportaria
faixas (top-N + menções) em vez de corte duro.

### 6. Cálculo 100% determinístico em pandas; LLM só roteia e interpreta
`tools.py` devolve números prontos; o agente escolhe ferramentas, lê resultados e
redige o parecer validado pelo schema `ParecerLLM`. Nenhum número citado pode ter
vindo "da cabeça" do modelo — exigência de separação regra/LLM do desafio.

### 7. Cache-first por `case_key` (não hash de prompt)
Chaves legíveis (`nivel2_cli-029_passo1`) facilitam auditoria ("qual prompt gerou
isto?") ao custo de invalidar cache se o prompt mudar. Para o exercício, rastreabilidade > sofisticação.

### 8. Backend offline com política determinística documentada
Não havia chave de API gratuita disponível durante o desenvolvimento. Em vez de
simular respostas falsas de LLM no nível 2, implementei dois backends com a mesma
interface: `api` (SDK OpenAI-compatível, pronto p/ Groq/Gemini/OpenRouter/Ollama)
e `offline`, que segue um roteiro fixo (historico → dia crítico/perfil → parecer)
com política explícita: ALTO se fracionamento, OU atípico ≥10x mediana, OU ≥2
atípicos no mesmo dia, OU atípico em espécie; senão MÉDIO. Os outputs commitados
usam o offline e são integralmente reproduzíveis.

### 9. Confronto com régua minimalista e divergência conservadora
Mapeei risco esperado por nº de regras distintas (2→alto, 1→médio). Resultado:
0% de concordância nominal, mas **100% das divergências na direção conservadora**
(agente mais severo, nunca menos). A leitura qualitativa está em
`outputs/confronto.md`: a régua ignora magnitude/canal/moeda que o agente considera.
Em PLD, falso positivo custa revisão humana; falso negativo custa risco regulatório.

## Processo

### 10. Notebook duplica parte da lógica do nível 2
O nível 1 pede notebook autocontido; o nível 2 pede módulos. Extraí o compartilhável
para `nivel_2/regras.py`, mas o notebook mantém versão didática própria. Num repo
maior eu criaria `src/pld/` compartilhado e testes pytest cobrindo as duas camadas.

### 11. O que faria diferente com mais tempo
- `src/` único + suíte pytest (dedup, conversão, fronteiras das regras);
- nível 3 trilha C reaproveitando `tools.py` com `DADOS_PATH` novo;
- taxa de câmbio histórica e limites configuráveis via YAML;
- CI (GitHub Actions) rodando os scripts a cada push.
