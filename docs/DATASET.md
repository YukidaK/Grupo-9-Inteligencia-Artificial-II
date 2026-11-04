# Dataset e procedência

A cópia histórica utilizada é **MovieLens Latest Small (`ml-latest-small`), gerada em 26/09/2018**. O README local informa avaliações entre 29/03/1996 e 24/09/2018. Não se trata de uma versão semântica “1.0”; `latest-small` é uma distribuição de desenvolvimento que pode mudar.

Fonte oficial registrada: [GroupLens — MovieLens](https://grouplens.org/datasets/movielens/) e [pacote Latest Small](https://files.grouplens.org/datasets/movielens/ml-latest-small.zip). Esses endereços foram obtidos das evidências locais; não houve consulta ou download na GIT-02.

SHA-256 do ZIP histórico, confirmado localmente:

```text
696d65a3dfceac7c45750ad32df2c259311949efec81f0f144fdfb91ebc9e436
```

## Arquivos

| Arquivo | Campos | Uso |
|---|---|---|
| `movies.csv` | `movieId,title,genres` | Catálogo, busca, gêneros e ano extraído do título. |
| `ratings.csv` | `userId,movieId,rating,timestamp` | Limpeza, divisão, matriz, estatísticas e avaliação. |
| `links.csv` | `movieId,imdbId,tmdbId` | Mapeamento opcional para pôsteres; não confirma disponibilidade. |
| `tags.csv` | `userId,movieId,tag,timestamp` | Presente na distribuição, não usado pelo recomendador atual. |
| `README.txt` | Texto | Procedência, formato, condições de uso e referência. |

`movieId` relaciona os arquivos. `userId` identifica usuários anonimizados históricos, não visitantes da aplicação. Notas são explícitas, de 0,5 a 5, em passos de 0,5; ausência não significa rejeição. `timestamp` registra a avaliação e auxilia a limpeza de duplicatas. Gêneros são separados por `|`; não equivalem a sinopses ou preferências completas.

Contagens históricas registradas: 610 usuários, 100.836 avaliações, 9.742 filmes cadastrados e 9.724 filmes avaliados; 18 cadastrados sem avaliações. A limpeza não removeu registros nessa cópia. Esses números são evidências anteriores, não uma reexecução experimental na GIT-02.

## Obtenção para uma execução futura

1. Leia as condições oficiais e obtenha o ZIP diretamente do GroupLens. Não compartilhe a cópia deste projeto como parte do repositório.
2. Confira o SHA-256, por exemplo com `sha256sum ml-latest-small.zip` no Linux. Para reprodução histórica é necessária a mesma cópia; um download futuro da URL “latest” não garante esse hash. Se divergir, registre a diferença e trate como nova execução; não altere o hash esperado nem declare reprodução histórica completa.
3. Extraia preservando `README.txt` e coloque os CSVs em `movielens_prototipo/dados/ml-latest-small/`. São essenciais `ratings.csv` e `movies.csv`; preserve também `links.csv` para o mapeamento e os demais arquivos da distribuição local.
4. Confira a procedência antes de preparar resultados. O carregador usa CSVs locais; se faltarem, pode extrair o ZIP local ou baixar o pacote. Não existe atualização periódica automática. A consulta de pôsteres não atualiza o catálogo MovieLens.

Dados, ZIP, `origem.json`, matrizes e partições ficam locais e ignorados. O registro local de origem pode conter caminho da máquina e não foi selecionado para publicação.

## Condições verificadas localmente

O `README.txt` distribuído permite uso para pesquisa, exige reconhecimento da fonte, proíbe sugerir endosso e estabelece condições para redistribuição, inclusive transformações. Uso comercial ou que gere receita exige contato e autorização prévia. Estas são informações da cópia local, não uma revisão jurídica completa das condições atuais.

Referência indicada: F. Maxwell Harper e Joseph A. Konstan. 2015. *The MovieLens Datasets: History and Context*. ACM Transactions on Interactive Intelligent Systems 5(4), artigo 19. [DOI](https://doi.org/10.1145/2827872).

O repositório proposto seleciona somente agregados e procedência, sem redistribuir CSVs, partições ou matrizes. Isso não implica autorização automática de todo artefato derivado: o responsável ainda deve revisar a seleção, o reconhecimento da fonte e as condições de publicação. O README também alerta que `latest-small` pode mudar e não é adequado como benchmark compartilhado estável. A cópia é histórica e não representa lançamentos, disponibilidade de streaming ou população geral.
