# Protótipo independente item–item

Não integra a aplicação web e não altera os três métodos existentes. A Etapa 5 arquitetural continua pausada. Uma única configuração foi registrada em `verificacoes/item_item_20261029/configuracao_previa.json`, em 29/10/2026 às 23:12:16 UTC, antes de construir o protótipo e abrir a validação nesta atividade. Não foi feita busca por parâmetros.

## Justificativa e configuração

O desenvolvimento tem 610 usuários, 8.262 filmes e 64.960 avaliações, com aproximadamente 98,71% das combinações sem nota. A matriz legada (610 × 8.960, 80.896 notas) foi apenas inspecionada: inclui a validação interna e não pode ser reutilizada para treinar este modelo.

Escolha inicial: cosseno ajustado pela média de usuário, em pares coavaliados. Isso utiliza a intensidade das avaliações explícitas, compensando parte da diferença de escala entre usuários. Não é cosseno binário de consumo nem previsão supervisionada de estrelas.

Para cada usuário u, calcula-se μ_u sobre TODAS as suas notas observadas de desenvolvimento, antes de cortar itens de pouco suporte. Define-se a_ui = r_ui − μ_u apenas quando r_ui foi observado. Para filmes i,j e U_ij, conjunto de usuários que avaliaram ambos:

```
cosseno(i,j) = Σ[u em U_ij] a_ui a_uj /
               sqrt(Σ[u em U_ij] a_ui² × Σ[u em U_ij] a_uj²)
s(i,j) = cosseno(i,j) × |U_ij| / (|U_ij| + 10)
```

Configuração única:

- Filme precisa de pelo menos cinco avaliações de desenvolvimento para entrar no modelo.
- Par precisa de pelo menos cinco coavaliadores; o próprio item é excluído como vizinho.
- Normas nulas não produzem relação; só s>0 é guardado. Correlações negativas não são convertidas em rejeição de visitante.
- Usa todas as relações positivas qualificadas, sem selecionar top K vizinhos.
- Score do candidato = soma de s com as referências ativas, dividida pelo número total de referências ativas (1–5). Referência sem relação contribui com ausência de sinal, não nota negativa.
- Retorna somente candidatos com score>0, até dez. Desempate por menor movieId, sem popularidade ou nota ponderada.
- Não há fallback. Listas vazias/curtas são mantidas e avaliadas como tais.

Os limiares e o fator dez são escolhas iniciais conservadoras, não valores ótimos demonstrados. Usar apenas correlações positivas e suporte mínimo pode reduzir cobertura; isso será medido, não corrigido automaticamente.

## Dados ausentes e memória

Um indicador observado separado distingue nota ausente de desvio zero. A máscara mantém avaliações iguais à média do usuário no cálculo de suporte. Os produtos esparsos calculam numeradores e normas somente nos coavaliadores. Não se atribui nota zero aos pares ausentes nem se calcula erro de previsão contra zeros artificiais.

NumPy e SciPy já instalados são suficientes. Os produtos item × item são calculados em blocos de 128 linhas, sem matriz densa de todos os pares. As relações e suportes são CSR; a pontuação usa um vetor denso de tamanho número de itens. O pico RSS do processo, tempos e bytes das matrizes são registrados; os bytes dos produtos por bloco não representam toda a memória temporária, pois há estruturas Python e alocações internas adicionais.

`ItemItem` admite limiares menores nos testes sintéticos para tornar os valores manuais verificáveis. O runner real fixa cinco/cinco/dez/128; isso não constitui comparação de múltiplas configurações reais.

## Sobreposição com o usuário simulado

O modelo global inclui as notas de desenvolvimento de todos os usuários, inclusive quem é avaliado. O perfil explícito, porém, recebe apenas as referências ativas; as notas pessoais adicionais não entram na soma de scores. Todo o histórico de desenvolvimento é usado somente para excluir conhecidos, como nos controles.

Mais especificamente, para um candidato j nunca avaliado pelo usuário alvo u, u não pertence a U_ij para nenhuma referência i. Logo, ele não contribui com numerador, normas ou suporte desses pares. A média de u afeta somente sua própria linha, que também não entra nesses pares. Os testes exercitam essa propriedade alterando uma nota não ativa de u. É uma vantagem metodológica das normas restritas aos coavaliadores em relação a normalizações globais de colunas.

O restante das notas do alvo ainda altera outras relações globais entre itens que ele avaliou e os contadores de suporte desses itens. Não se deve dizer que o modelo foi treinado sem esse usuário. A elegibilidade geral de referências é calculada com todos; nesta configuração, para haver uma relação pontuável com candidato inédito, são necessários cinco OUTROS coavaliadores, então o suporte mínimo do par impede que a única contribuição do alvo torne a relação utilizável. Isso não é uma simulação completa de usuário inteiramente novo, nem um experimento geral de leave-one-user-out. Não foi ajustado modelo separado para cada usuário.

## Comparação e isolamento

Reutiliza controles congelados de `experimentos/avaliacao_interna_20261029/`: listas de popularidade, nota ponderada e perfil que foram geradas só do desenvolvimento. Manifesto, código, divisão, catálogo, parâmetros e hashes são conferidos. Nenhum ranking do treino original completo é aberto. As métricas dos controles são recalculadas e precisam coincidir com a execução aprovada.

Coorte fixa: 594 usuários com cinco positivos no desenvolvimento. Referências: semente 201 e mesmos prefixos 1–5. C(u,n) é reconstruído exclusivamente de desenvolvimento e catálogo, conferindo hash e tamanho contra os controles: suporte >=5, menos todo o histórico conhecido, com algum gênero compartilhado com referências. O filtro de gêneros é mantido e **pode impedir descobertas colaborativas entre gêneros diferentes**.

O universo disponível é igual para os quatro métodos. O item–item pode não pontuar parte dele; não se eliminam esses usuários da avaliação nem se completam suas listas. Essa diferença aparece em cobertura, tamanho médio e casos sem candidatos pontuáveis. `n_candidatos` e hash descrevem C; `n_pontuaveis` descreve o suporte efetivo do método. Nos três controles, todos os candidatos são pontuáveis.

Todas as listas são salvas e assinadas antes de abrir validação como tabela. Depois disso, a auditoria semântica da divisão e o carregador explícito de validação conferem isolamento e execução. Reutiliza `pontuar_coorte` para as métricas de todas as linhas, estendendo somente a agregação para o novo nome de método. Fórmulas, relevância >=4, Precision/10, Recall com todos os positivos e NDCG binário são preservados. Usuários sem positivos na validação têm métricas ausentes; usuários com positivos e lista vazia têm zero justificado. Não se consulta o teste original.

## Reprodução

Na raiz, sempre com uma saída nova:

```sh
.venv/bin/python -B movielens_prototipo/experimento_item_item.py \
  --divisao experimentos/divisao_interna_20261029_final \
  --treino movielens_prototipo/resultados/treino.csv \
  --procedencia experimentos/avaliacao_perfil_20261028/manifesto.json \
  --filmes movielens_prototipo/resultados/filmes.csv \
  --controles experimentos/avaliacao_interna_20261029 \
  --configuracao verificacoes/item_item_20261029/configuracao_previa.json \
  --saida experimentos/NOVO_ITEM_ITEM
```

Saídas: listas dos quatro métodos (scores do item–item incluídos), métricas por usuário, resumo CSV/JSON, usuários, auditoria de custo e relações, similaridades/suportes NPZ, IDs dos itens e registro prévio de configuração. Manifesto separado, esquema `cinematch.experimento.item_item` versão 1, com hashes de entradas, código e saídas. Não é formato de modelo da aplicação. Reserva exclusiva e marcador da Etapa 3 evitam sobrescrita.

O runner usa `resource` para RSS no Linux; portabilidade dessa medição para Windows não foi implementada. O notebook e seus módulos exportados não mudam: este protótipo não é dependência deles.

## Limitações

Filmes sem suporte, pares raros, normas nulas e correlações não positivas não geram recomendações; referências novas são cold start. Os gêneros continuam limitando os candidatos. Coavaliação é afetada por exposição e popularidade; correlação não garante causalidade nem gosto do visitante. A centralização mede desvio relativo à média do usuário, não necessariamente gostar/desgostar em sentido absoluto.

Uma divisão, uma amostra de referências e uma configuração não estimam robustez ou superioridade universal. A validação já foi observada em atividades anteriores: é um instrumento de desenvolvimento, não teste final intocado. Não houve ajuste com as notas do teste original. Futuros ajustes exigem autorização e protocolo de seleção dentro de desenvolvimento, sem eleger combinações pela mesma validação repetidamente. Não integrar ao produto apenas por uma média favorável.
