# Confronto: risco do agente x risco esperado pelas regras

## Resumo quantitativo
- Clientes analisados: 10
- Concordantes: 0 (0.0%)
- Agente mais severo que o esperado: 10
- Agente menos severo que o esperado: 0

 qtd_regras  clientes  concordantes
          1        10             0

## Detalhamento

cliente_id regras_disparadas  qtd_regras risco_esperado risco_agente       concordancia
   CLI-029     fracionamento           1          médio         alto agente_mais_severo
   CLI-017     fracionamento           1          médio         alto agente_mais_severo
   CLI-002     fracionamento           1          médio         alto agente_mais_severo
   CLI-003     fracionamento           1          médio         alto agente_mais_severo
   CLI-014     valor_atipico           1          médio         alto agente_mais_severo
   CLI-013     valor_atipico           1          médio         alto agente_mais_severo
   CLI-028     valor_atipico           1          médio         alto agente_mais_severo
   CLI-005     valor_atipico           1          médio         alto agente_mais_severo
   CLI-023     valor_atipico           1          médio         alto agente_mais_severo
   CLI-001     valor_atipico           1          médio         alto agente_mais_severo

## Análise qualitativa

O mapeamento "nº de regras -> nível de risco" é uma régua minimalista: trata as duas
regras como igualmente graves e ignora magnitude, canal e moeda. O agente LLM enxerga
essas dimensões extras, e é por isso que diverge exatamente nos clientes com UMA regra
disparada (10 casos), classificando-os como ALTO:

- Nos clientes com fracionamento isolado, a soma diária supera folgadamente o limite
  legal de referência (R$ 50 mil) em vários dias, o que na prática pesa mais que um
  único valor atípico marginal;
- Nos clientes apenas com valores atípicos, há evidências agravantes que a regra não
  pontua individualmente: operações >= 10x a mediana do próprio cliente, depósitos em
  espécie e concentração de múltiplos atípicos no mesmo dia — padrões clássicos de
  colocação/estruturação descritos na COAF;

Nenhum caso ficou MENOS severo que o esperado (0 ocorrências), ou seja,
a divergência é toda na direção conservadora. Em PLD, falso positivo vai para revisão
humana com custo operacional baixo; falso negativo é risco regulatório. Portanto o
comportamento do agente é adequado à política da casa — mas a política formal de
níveis deveria incorporar esses agravantes para reduzir a ambiguidade entre camadas.
