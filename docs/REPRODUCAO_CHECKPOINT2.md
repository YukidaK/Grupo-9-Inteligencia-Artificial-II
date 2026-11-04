# Reprodução do Checkpoint 2

Este guia descreve protocolos existentes. A GIT-02 não reexecutou experimentos, não selecionou parâmetros e não alterou resultados. Valores abaixo provêm das evidências históricas selecionadas em [relatórios](../relatorios/checkpoint2/README.md) e [manifestos de referência](../reproducao/README.md).

## Dados e preparação

Use a cópia MovieLens de 26/09/2018, conferindo o [hash do dataset](DATASET.md). São 100.836 avaliações, 610 usuários, 9.742 filmes cadastrados e 9.724 avaliados. A limpeza existente valida campos numéricos e notas em passos de 0,5 entre 0,5 e 5, remove referências inválidas e duplicatas usuário–filme mantendo a mais recente, valida o catálogo e extrai o ano do título. Nessa cópia, as contagens não mudaram após a limpeza.

A divisão original aleatória por usuário usa semente **42** e fração nominal de teste **0,20**. Para históricos com mais de um registro, o número de teste é limitado a `min(n-1, max(1, floor(n*0.2)))`; históricos unitários permanecem no treino. Foram registrados 80.896 registros de treino e 19.940 de teste, com 610 usuários em cada partição. Filtro mínimo de usuário no treino: cinco; filtro mínimo de filme para candidatos: cinco. Nenhum usuário foi removido nessa cópia. A matriz de treino tem 610 × 8.960 posições e 80.896 avaliações armazenadas; 3.218 filmes são elegíveis para ranking. O filtro de filme não elimina essas colunas da matriz.

As estatísticas e os baselines usam somente o treino recebido. A matriz não representa zeros como rejeições. Os baselines globais foram avaliados no teste externo; a similaridade da página não utiliza a matriz colaborativa.

## Divisão interna e isolamento

Somente as 80.896 avaliações do treino original foram divididas, com semente **101** e fração nominal de validação **0,20**, por usuário, conservando registros e IDs. Foram registrados:

| Partição | Avaliações | Usuários | Filmes distintos |
|---|---:|---:|---:|
| Desenvolvimento | 64.960 | 610 | 8.262 |
| Validação interna | 15.936 | 610 | 4.635 |

Os filmes podem aparecer nas duas partições; os pares usuário–filme são disjuntos. Históricos insuficientes ficam no desenvolvimento, sem fabricar avaliações ou descartá-las silenciosamente. A união deve corresponder exatamente ao treino de origem. Manifestos e auditoria verificam procedência, hashes e conservação. Estatísticas do treino original completo não podem ser reutilizadas na avaliação interna: elas incluiriam a validação.

A geração recebe apenas desenvolvimento e catálogo, grava e assina listas antes de carregar notas reservadas para métricas. Usuários sem positivos suficientes não formam o perfil exigido. A coorte interna fixa exige cinco notas >=4 no desenvolvimento: **594 elegíveis**, dos quais **586 avaliáveis** e **oito sem positivos na validação**, excluídos das médias de qualidade.

## Referências e candidatos compartilhados

Relevância: **nota >=4**. Tamanho máximo das listas: **10**. Preferências explícitas e rejeições ficam vazias na simulação de perfil inicial. O histórico conhecido completo de desenvolvimento é excluído de todos os métodos.

A avaliação externa de perfil usa semente **42** para referências. A comparação interna e o item–item usam **201**, com `SeedSequence([201,userId])`, IDs positivos ordenados e sorteio por usuário. Perfis de uma a cinco referências são prefixos consistentes da mesma amostra de cinco. Não se usam notas de validação para selecionar referências, ajustar pesos ou construir rankings.

Para cada usuário e quantidade de referências, os métodos internos compartilham os candidatos: suporte mínimo de cinco avaliações no desenvolvimento, exclusão do histórico individual e pelo menos um gênero em comum com as referências. O marcador de gênero ausente é descartado. Portanto, os baselines desta comparação são **condicionados ao perfil**, diferentes dos baselines globais históricos. O universo muda entre quantidades de referências; isso impede atribuir toda diferença de métrica apenas à quantidade informada.

## Métodos existentes

- **Popularidade:** ordena pela contagem de avaliações, com desempate pelo menor `movieId`, usando somente a partição de construção.
- **Nota ponderada:** `W=(v*R + m*C)/(v+m)`, com `v` contagem do filme, `R` média do filme, `C` média global da partição de construção e `m=5`. Ordena por W, contagem e menor ID.
- **Perfil da página:** média do Jaccard de conjuntos de gêneros com cada referência; score `0.65*S + 0.25*A + 0.10*(W/5)`, sendo A o sinal de preferências positivas. Preferências vazias fazem A ser zero. Regras de exclusão e desempate permanecem as do método de produção. A avaliação não mede a conversa ou o refinamento humano.
- **Item–item experimental:** cosseno ajustado pela média de cada usuário, calculado somente nos coavaliadores. Filme precisa de cinco avaliações, par de cinco coavaliadores, regularização multiplicativa `suporte/(suporte+10)`, blocos de 128 itens, apenas relações positivas, sem top K de vizinhos. Score é a soma das similaridades com as referências ativas dividida pelo número total dessas referências. Retorna somente scores positivos, desempata por menor ID e não utiliza fallback. Ausência de nota é distinta de desvio observado igual a zero. Não está integrado à página.

O modelo colaborativo global inclui o desenvolvimento de todos os usuários, inclusive o avaliado. Seu perfil explícito usa somente as referências. Para candidatos inéditos, o usuário alvo não pertence ao conjunto de coavaliadores daquele par; ainda assim, outras relações e suportes globais incluem seu histórico. Não é um experimento de usuário inteiramente novo. O filtro compartilhado de gêneros pode impedir descobertas colaborativas entre gêneros diferentes.

A [configuração preservada](../reproducao/configuracao_item_item.json) tem registro anterior ao manifesto final do item–item. Isso evidencia os parâmetros registrados, não uma hipótese de superioridade pré-registrada nem prova independente de toda a cronologia. Não foi criada hipótese retroativa na GIT-02; reutilizar esse arquivo numa nova execução não constitui novo pré-registro.

## Métricas e denominadores

Precision@10 é acertos/10, inclusive em listas curtas. Recall@10 divide os acertos por todos os positivos reservados do usuário, inclusive filmes fora dos candidatos. NDCG@10 usa relevância binária, desconto `1/log2(posição+1)` com posições iniciando em um, e ideal com até dez positivos. Ausência de avaliação não é classificada como rejeição explícita.

Usuários sem positivos reservados têm métricas ausentes e ficam fora das médias de qualidade. Usuários com positivos e lista vazia têm zero justificado. Médias de qualidade são macro por usuário avaliável. Cobertura de usuários e média de recomendações usam toda a coorte elegível; cobertura é a fração que recebeu ao menos um item, não cobertura do catálogo. Quantidades de candidatos também usam a coorte elegível. O item–item pode pontuar apenas parte dos candidatos compartilhados; suas listas curtas não são completadas por popularidade.

Os [CSV selecionados](../relatorios/checkpoint2/README.md) preservam os números exatos, sem novo cálculo. Na validação interna registrada, popularidade superou os demais métodos; item–item superou perfil por gêneros. Não comparar diretamente essas métricas com o teste original: são partições, população e estatísticas diferentes.

## Cadeia para execução futura em diretórios novos

**Não executada na GIT-02.** Requer Linux, ambiente do README, mesma cópia do dataset e diretórios de saída inexistentes. Os dados essenciais devem estar presentes para evitar download implícito. As saídas individuais permanecem em `local/`, ignorado pelo Git. Não use pastas de resultados anteriores.

Escolha uma única versão para toda a cadeia:

```sh
# Nova execução com código atual:
CINEMATCH_CODIGO=movielens_prototipo
CINEMATCH_SAIDA=local/checkpoint2_nova_01

# Para uma reprodução histórica em outra ocasião, substitua as duas linhas por:
# CINEMATCH_CODIGO=reproducao/historico_20261029
# CINEMATCH_SAIDA=local/checkpoint2_historica_01
```

Em seguida, usando as variáveis acima:

```sh
.venv/bin/python -B "$CINEMATCH_CODIGO/recomendador.py" \
  --dados movielens_prototipo/dados/ml-latest-small \
  --resultados "$CINEMATCH_SAIDA/resultados" --identificar

.venv/bin/python -B "$CINEMATCH_CODIGO/avaliacao_perfil.py" \
  --resultados "$CINEMATCH_SAIDA/resultados" \
  --dados movielens_prototipo/dados/ml-latest-small \
  --saida "$CINEMATCH_SAIDA/perfil" --seed 42

.venv/bin/python -B "$CINEMATCH_CODIGO/divisao_interna.py" \
  --treino "$CINEMATCH_SAIDA/resultados/treino.csv" \
  --procedencia "$CINEMATCH_SAIDA/perfil/manifesto.json" \
  --saida "$CINEMATCH_SAIDA/divisao" --seed 101 --fracao 0.2

.venv/bin/python -B "$CINEMATCH_CODIGO/avaliacao_interna.py" \
  --divisao "$CINEMATCH_SAIDA/divisao" \
  --treino "$CINEMATCH_SAIDA/resultados/treino.csv" \
  --procedencia "$CINEMATCH_SAIDA/perfil/manifesto.json" \
  --filmes "$CINEMATCH_SAIDA/resultados/filmes.csv" \
  --saida "$CINEMATCH_SAIDA/controles"

.venv/bin/python -B "$CINEMATCH_CODIGO/experimento_item_item.py" \
  --divisao "$CINEMATCH_SAIDA/divisao" \
  --treino "$CINEMATCH_SAIDA/resultados/treino.csv" \
  --procedencia "$CINEMATCH_SAIDA/perfil/manifesto.json" \
  --filmes "$CINEMATCH_SAIDA/resultados/filmes.csv" \
  --controles "$CINEMATCH_SAIDA/controles" \
  --configuracao reproducao/configuracao_item_item.json \
  --saida "$CINEMATCH_SAIDA/item_item"
```

Não substituir manifestos gerados pelos manifestos documentais históricos: os novos registram seus próprios IDs, horários e hashes. Os controles precisam corresponder à versão de código do runner. A cadeia não requer distribuir avaliações individuais no GitHub. A preparação original também avalia baselines no teste externo; essa etapa reproduz um protocolo fixo e não autoriza usar o teste para selecionar métodos ou parâmetros.

## Limites da reprodução histórica

Foram preservados nove módulos atestados pelo manifesto item–item e um carregador histórico de apoio, com procedência separada. A resolução estática de dependências não substitui uma execução completa. O código atual de conversa tem hash diferente: misturar versões pode impedir a validação, e isso não deve ser contornado editando metadados. Os manifestos públicos são referências, sem os artefatos individuais necessários para validar as execuções antigas integralmente. Igualdade de métricas em nova máquina não foi medida aqui. O runner item–item usa `resource`, cuja portabilidade para Windows não foi implementada.

Uma divisão, uma amostra de referências e uma configuração não demonstram estabilidade, significância ou superioridade universal. A validação já foi observada; ajustes futuros devem ter protocolo próprio, sem tratá-la como teste intocado. O teste externo permanece fora das decisões de desenvolvimento. A licença do código, a redistribuição da seleção e a privacidade do histórico aguardam aprovação humana.
