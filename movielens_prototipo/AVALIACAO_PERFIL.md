# Avaliação offline do recomendador personalizado

## Escopo e auditoria

O experimento está em `avaliacao_perfil.py`, separado da aplicação. Chama o `Recomendador.recomendar_perfil()` de produção, sem alterar pesos, filtros, fórmulas ou desempates. Não avalia conversa, usabilidade, satisfação ou serviços de streaming. A Etapa 5 arquitetural permanece pausada.

A divisão existente é um holdout aleatório por usuário, com fração nominal de teste 0,20 e semente 42. A preparação elimina duplicatas antes de separar os pares. Os mínimos são cinco avaliações por usuário e por filme, calculados no treino. Não é uma previsão temporal de consumo futuro.

O runner lê os arquivos já preparados e verifica em memória se a divisão salva corresponde à aplicação de `limpar()` e `dividir()` aos CSVs locais. Essa reconstituição serve apenas para conferência; as entradas efetivas da avaliação são `treino.csv` e `teste.csv` existentes. Nenhum deles é regravado. A função de download/preparação automática não é utilizada.

As estatísticas são recalculadas exclusivamente de treino e comparadas ao ranking salvo. Os dois baselines globais também são recalculados com `avaliar()` e precisam coincidir com o relatório existente. Esses resultados globais são uma conferência separada, não a comparação pareada descrita abaixo.

## Referências e população

1. Uma referência elegível é um filme do usuário com nota **de treino >=4**.
2. IDs são ordenados antes do sorteio. Cada usuário possui um gerador independente com `SeedSequence([42, userId])`.
3. Sorteia-se uma permutação dos positivos de treino e usam-se seus primeiros cinco IDs, quando disponíveis. Os perfis de 1, 2, 3, 4 e 5 são prefixos aninhados da mesma seleção.
4. Não há ajuste de semente, escolha da melhor amostra ou calibração por resultados de teste.
5. O histórico excluído contém **todos** os filmes avaliados no treino daquele usuário, inclusive notas baixas e referências que não participam do perfil com n menor.
6. Preferências positivas/negativas de gêneros e rejeições da sessão são vazias: o experimento representa o perfil inicial, não o refinamento por conversa.

Selecionar referências apreciadas é uma hipótese experimental explícita, mais específica que informar qualquer filme assistido na página. Não permite generalizar automaticamente para referências neutras ou rejeitadas.

São publicados dois recortes:

- `por_n_disponivel`: em cada n, inclui todos os usuários com pelo menos n positivos no treino. A população pode mudar entre n, mas é idêntica entre métodos dentro de cada n.
- `fixa_5`: inclui somente usuários com pelo menos cinco positivos de treino, para comparar n de 1 a 5 na mesma população. Este é o recorte principal para comparar quantidades de referências.

Usuários sem referências positivas suficientes não recebem uma lista substituta dos baselines. A comparação fica não aplicável para os três métodos, com métricas ausentes. O número dessas exclusões é reportado. Se ninguém atender ao mínimo de treino, o experimento encerra com diagnóstico explícito, em vez de fabricar médias zero.

## Universo comum e baselines

A implementação da página exclui candidatos sem similaridade de gênero quando não há preferências explícitas. Portanto, comparar apenas as listas finais com baselines globais não utilizaria a mesma elegibilidade efetiva.

O protocolo pareado utiliza:

```text
C(u,n) = filmes com pelo menos cinco avaliações no treino
         - todo o histórico de treino do usuário
         com pelo menos um gênero em comum com suas n referências
```

O marcador `(no genres listed)` é removido dos gêneros. Com referências válidas e preferências de gênero vazias, possuir algum gênero em comum equivale a ter a média Jaccard estritamente positiva. Esse cálculo replica somente a elegibilidade, não o score.

- Perfil: chama o método real de produção, com todo o histórico conhecido e as referências selecionadas.
- Popularidade: conserva a ordenação por contagem, contagem e menor `movieId` do baseline existente; restringe sua lista a C(u,n).
- Nota ponderada: conserva a ordenação por nota ponderada, contagem e menor `movieId`; restringe sua lista ao mesmo conjunto.

Os baselines são, portanto, **condicionados às mesmas referências para elegibilidade**. Não são os rankings globais históricos sem filtro de gêneros. Suas estatísticas e fórmulas permanecem as existentes. O código verifica que os três métodos usam a mesma população, respeitam C(u,n), não repetem vistos e retornam `min(10, |C|)` itens. Registra quantidade e hash dos candidatos para cada par usuário/n.

Essa escolha isola diferenças de ordenação dentro do universo comum e não mede a vantagem/desvantagem da seleção de candidatos do perfil contra o catálogo global completo. Além disso, C(u,n) cresce ou permanece igual com os prefixos de referências: diferenças entre n não podem ser atribuídas somente a uma melhoria na representação do gosto.

## Métricas e casos sem resultados

Relevância: nota de **teste >=4**. O teste entra somente em `pontuar_listas()`, depois de `gerar_listas()` ter produzido todas as referências e recomendações. Essa última função não recebe tabela de teste.

- Precision@10: acertos / 10, mesmo quando a lista tem menos de dez itens.
- Recall@10: acertos / quantidade de relevantes do usuário no teste.
- NDCG@10: relevância binária com desconto logarítmico por posição, normalizada pelo ideal com até dez relevantes.
- As métricas são médias macro entre os usuários avaliados, com o mesmo peso por usuário.
- Relevantes fora do catálogo elegível ou do filtro de gêneros **continuam** no denominador de Recall e no ideal de NDCG.
- Usuários aptos sem positivos no teste não entram nas médias dessas três métricas, para manter a política do avaliador original (Recall/NDCG não têm denominador útil; Precision também é excluída por essa política); recebem campos ausentes, não zero. As recomendações ainda são geradas para medir tamanho e cobertura.
- Usuários aptos com positivos, mas sem candidatos, recebem lista vazia e métricas zero. Não são descartados da qualidade.
- Média de recomendações e cobertura usam todos os usuários aptos por referências, incluindo quem não tem positivos no teste. Cobertura = usuários com pelo menos uma sugestão / usuários aptos. Não é cobertura do catálogo nem Recall.
- Quando não há usuários aptos ou avaliados para uma média, o valor fica ausente (`null` em JSON/célula vazia em CSV), com contagens explícitas.

Ausência de avaliação não é rejeição. Itens sem relevância observada não recebem crédito de acerto, o que limita a interpretação de recuperação offline.

## Execução e reprodutibilidade

Exemplo de comando, a partir da raiz, usando uma pasta de saída nova:

```sh
.venv/bin/python -B movielens_prototipo/avaliacao_perfil.py \
  --saida experimentos/avaliacao_perfil_NOVA_EXECUCAO --seed 42
```

Não reutilizar uma saída existente. O programa não baixa dados, não instala dependências e não aceita saída dentro dos diretórios de entrada. O manifesto experimental usa o esquema `cinematch.experimento.perfil`, com versão 1. Reutiliza da Etapa 3 a reserva exclusiva de diretório, o marcador de preparação e as assinaturas SHA-256. Não reutiliza o manifesto de oito artefatos de produção, cujo contrato é diferente. O loader da aplicação rejeita esse esquema experimental.

Saídas:

- `avaliacao_por_usuario.csv`: referências, IDs recomendados, elegibilidade, quantidade/hash de candidatos, métricas e indicação de exclusão para cada usuário/n/método.
- `resumo.csv` e `resumo.json`: métricas, contagens e cobertura por recorte/n/método.
- `auditoria.json`: conferências das entradas, estatísticas de população e baselines globais recalculados.
- `manifesto.json`: hashes das entradas, saídas e código usado; parâmetros, ambiente, dataset e identificação da execução.

O manifesto registra a data da cópia do dataset somente quando confirmada pelo README local. Para os artefatos legados, a ausência de manifesto de origem continua explicitamente registrada; a conferência adicional de divisão e estatísticas não é declarada como validação completa do legado pela Etapa 3.

## Limitações

- Uma única amostra de referências por usuário e uma única divisão aleatória. Não há intervalos de confiança ou teste de significância; não se deve eleger uma configuração com base no teste.
- Referências positivas de treino simulam gosto declarado. A página aceita assistidos provisórios; a equivalência com uso humano não está demonstrada.
- Baselines condicionados por gêneros não têm o mesmo universo efetivo dos baselines globais históricos. As tabelas não devem ser misturadas.
- O recorte disponível por n muda de população. A coorte fixa evita esse fator, mas ainda altera as referências e o conjunto C(u,n).
- O protocolo mede recuperação de avaliações positivas observadas, não satisfação, compreensão de texto ou precisão de disponibilidade.
- Nenhuma fórmula, peso, filtro de produção ou regra de desempate foi ajustada ao teste. A matriz persistida não é usada pelo perfil e não foi regravada.

## Resultados medidos em 28/10/2026

Execução local com auxílio do Codex; não houve conferência manual do grupo. Saída: `experimentos/avaliacao_perfil_20261028/`. Foram utilizados os 80.896 registros de treino e 19.940 de teste já existentes, sem regravá-los. O ranking de treino contém 3.218 filmes elegíveis.

### Coorte fixa — comparação principal

601 usuários aptos para os cinco tamanhos de perfil. Em cada tamanho e método, 591 usuários com positivos no teste entraram nas médias; dez sem positivos foram excluídos. Todos os 601 receberam dez recomendações em todos os métodos/tamanhos: média 10, cobertura 100% dos aptos e zero casos sem candidatos nesta execução. Os 601 aptos equivalem a 98,52% dos 610 usuários de treino. Os nove restantes não tinham cinco referências positivas disponíveis.

| n_referencias | metodo | precision_at_10 | recall_at_10 | ndcg_at_10 |
| --- | --- | --- | --- | --- |
| 1 | popularidade | 0.102876 | 0.083917 | 0.140334 |
| 1 | nota_ponderada | 0.051438 | 0.039478 | 0.069314 |
| 1 | perfil | 0.018613 | 0.010715 | 0.023036 |
| 2 | popularidade | 0.115059 | 0.095192 | 0.156061 |
| 2 | nota_ponderada | 0.055499 | 0.042925 | 0.079393 |
| 2 | perfil | 0.024196 | 0.014996 | 0.032043 |
| 3 | popularidade | 0.117936 | 0.094522 | 0.157270 |
| 3 | nota_ponderada | 0.057530 | 0.044133 | 0.082552 |
| 3 | perfil | 0.023858 | 0.016816 | 0.031553 |
| 4 | popularidade | 0.119966 | 0.096806 | 0.159409 |
| 4 | nota_ponderada | 0.057868 | 0.044457 | 0.083461 |
| 4 | perfil | 0.020643 | 0.016926 | 0.027920 |
| 5 | popularidade | 0.119797 | 0.096528 | 0.159174 |
| 5 | nota_ponderada | 0.058037 | 0.044616 | 0.083687 |
| 5 | perfil | 0.020981 | 0.015625 | 0.027970 |

### População disponível por tamanho

Neste recorte, as métricas completas para os três métodos estão em `resumo.csv`. Os números abaixo usam a mesma definição de elegibilidade para todos eles.

| n_referencias | usuarios_elegiveis | usuarios_avaliados | usuarios_sem_positivos_teste | usuarios_referencias_insuficientes |
| --- | --- | --- | --- | --- |
| 1 | 609 | 595 | 14 | 1 |
| 2 | 608 | 595 | 13 | 2 |
| 3 | 607 | 594 | 13 | 3 |
| 4 | 603 | 593 | 10 | 7 |
| 5 | 601 | 591 | 10 | 9 |

### Interpretação

Na coorte fixa, o perfil obteve resultados menores que os dois baselines nas três métricas para todos os tamanhos de referência. O aumento da quantidade de referências não apresentou melhora monotônica. Esses resultados não motivaram qualquer ajuste de pesos, semente ou regras. Não demonstram uma configuração universalmente melhor nem substituem avaliação com pessoas.

Os baselines globais, recalculados separadamente com o protocolo original, coincidiram com os números anteriores: popularidade P@10=0,117815, R@10=0,094891, NDCG@10=0,158173; nota ponderada P@10=0,058151, R@10=0,044629, NDCG@10=0,083118. São valores de conferência, com população/candidatos diferentes da comparação pareada acima.

### Validação e preservação

- 13 testes sintéticos novos do experimento aprovados.
- Suíte Python: 133 testes, 132 aprovados e um pulado por restrição de socket, sem falhas/erros. Antes: 120 testes, 119 aprovados e um pulado.
- JavaScript: 11 cenários aprovados.
- Conferência independente de 9.084 linhas elegíveis: referências positivas de treino, exclusão de vistos e métricas verificadas com cálculo separado.
- Hashes dos arquivos experimentais conferiram com o manifesto. Dados, resultados anteriores e módulos de produção mantiveram os hashes.
- O notebook teve somente uma explicação atualizada para apontar o experimento separado; suas células de código não foram modificadas nem executadas.
- A Etapa 5 não foi iniciada.
