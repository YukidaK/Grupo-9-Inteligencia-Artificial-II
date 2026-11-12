# CineMatch

Protótipo acadêmico de recomendação de filmes do curso de Ciência da Computação da FIB. O projeto permite pesquisar filmes, selecionar referências e obter recomendações, além de comparar métodos em experimentos offline com o MovieLens Latest Small.

## Sistema de recomendação de filmes

### Problema e público

Em catálogos com milhares de títulos, o usuário pode perder tempo procurando o que assistir. O protótipo recomenda até dez filmes a partir de uma a cinco referências ativas. Com zero referências, não gera recomendações personalizadas. Uma ou duas referências são aceitas com orientação adicional; de três a cinco, segue o fluxo normal. Mais referências não garantem maior precisão.

Público: pessoas que querem descobrir filmes a partir de títulos conhecidos, sem precisar entender aprendizado de máquina.

Entrada: de uma a cinco referências, escolhidas no autocomplete. É possível remover uma escolha antes de confirmar ou iniciar uma nova seleção.

Saída: até dez recomendações com justificativas. A comparação com os baselines de popularidade e nota ponderada pertence à avaliação experimental; o baseline de popularidade e o item–item experimental não geram as recomendações da página. Seleção de plataformas, consultas de disponibilidade e refinamento interativo foram definitivamente descontinuados no escopo final.

### Direitos autorais e utilização

O CineMatch é um projeto acadêmico desenvolvido no contexto do curso de Ciência da Computação da FIB.

Seu código-fonte está disponível publicamente para consulta e conhecimento do projeto. Não é concedida, neste momento, uma licença geral para reutilização, modificação ou redistribuição do código, além dos direitos previstos na legislação aplicável e nos Termos de Serviço do GitHub.

Os direitos dos respectivos autores e as condições de utilização de recursos de terceiros, incluindo o dataset MovieLens, permanecem preservados.


## Funcionamento atual

A página utiliza um recomendador baseado em gêneros: compara os gêneros dos filmes de referência por Jaccard e combina esse sinal com nota ponderada calculada no treino. O componente de preferências permanece vazio no fluxo público; a fórmula original foi preservada. Não utiliza o item–item experimental nem um modelo de linguagem.

- De uma a cinco referências ativas; sem referências, não há recomendação personalizada.
- Até dez recomendações, excluindo o histórico conhecido; busca e autocomplete.
- Seleção de filmes pelo título original ou pelos três aliases brasileiros homologados; remoção de escolhas antes da confirmação e opção de começar novamente.
- Sessões temporárias em memória, sem login ou banco de dados.
- Pôsteres opcionais por TMDB, com cache local e placeholder quando indisponíveis. A execução básica não exige credenciais.
- Sem seleção de streaming, comandos de conversa ou feedback posterior às recomendações.

A filtragem colaborativa item–item existe somente como experimento independente. Séries e novos datasets não estão implementados. Streaming não integra o produto final.

## Tecnologias

Python 3.12, NumPy (operações numéricas), pandas (tabelas) e SciPy (matrizes esparsas). O servidor usa `http.server` da biblioteca padrão. A interface usa HTML, CSS e JavaScript sem framework. Os testes usam `unittest` e o executor nativo do Node.js; Jupyter/Colab é uma opção acadêmica separada. Não há banco de dados.

## Preparação e execução

Os comandos abaixo são instruções para uma execução futura, na raiz do repositório. Não foram executados durante a preparação GIT-02. Ambiente de referência: Linux e Python 3.12.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r movielens_prototipo/requirements-verificado.txt
```

Obtenha os arquivos conforme [dataset e licença](docs/DATASET.md). Os CSVs devem estar em `movielens_prototipo/dados/ml-latest-small/`. A cópia local não faz parte da seleção pública.

```sh
.venv/bin/python -B movielens_prototipo/recomendador.py
.venv/bin/python -B movielens_prototipo/app.py
```

Abra `http://127.0.0.1:8000`. A preparação gera resultados locais; não execute sobre resultados que precise preservar. A aplicação reutiliza resultados existentes, portanto trocar CSVs sem preparar uma saída coerente não atualiza automaticamente o modelo. Se arquivos essenciais faltarem, o carregador pode extrair o ZIP local ou tentar baixar o dataset: prepare os dados antes de executar em ambiente sem rede.

No Windows, o executável do ambiente virtual fica em `.venv\Scripts\python.exe`. Os comandos experimentais e a medição de memória por `resource` foram concebidos para Linux; a execução completa no Windows não foi homologada.

## Testes

```sh
.venv/bin/python -B -m unittest discover -s movielens_prototipo -p testes.py
node --test --test-isolation=none movielens_prototipo/testes_autocomplete.cjs
```

Node.js é necessário apenas para os testes JavaScript (executor nativo, sem `npm install`). Testes sintéticos não exigem consultas reais ao TMDB; verificações condicionais de dados reais e ambiente podem ser puladas quando os arquivos ou recursos não estiverem disponíveis. Não execute o notebook como substituto da suíte.

## Organização e documentação

| Caminho | Responsabilidade |
|---|---|
| `movielens_prototipo/` | Aplicação, módulos, interface, testes e documentação técnica. |
| `docs/` | Dataset, reprodução acadêmica e preparação de publicação. |
| `relatorios/checkpoint2/` | Seleção de resultados agregados históricos, sem avaliações individuais. |
| `reproducao/` | Fontes históricas mínimas e referências de proveniência. |
| `experimentos/`, `verificacoes/` | Artefatos brutos e evidências locais, ignorados pelo Git. |

Consulte o [README técnico](movielens_prototipo/README.md), o [guia do Checkpoint 2](docs/REPRODUCAO_CHECKPOINT2.md), os [resultados selecionados](relatorios/checkpoint2/README.md) e a [preparação GIT-02](docs/GIT02_RELATORIO.md).

## Limitações e créditos

O catálogo histórico não representa lançamentos nem disponibilidade atual. Gêneros são uma descrição limitada; as métricas dos baselines não avaliam automaticamente o algoritmo da página. Os experimentos internos usam uma divisão e uma amostra de referências; não demonstram superioridade universal. Popularidade foi superior aos demais métodos na comparação interna registrada. O item–item superou o perfil por gêneros, sem justificar sua integração ao produto.

Fonte: MovieLens/GroupLens; referência e condições em [DATASET.md](docs/DATASET.md). Metadados opcionais de pôsteres vêm do TMDB. A investigação histórica de disponibilidade TMDB/JustWatch foi preservada como documentação; sua implementação ativa foi removida. Os requisitos de uso externo do TMDB continuam sujeitos à revisão aplicável.

**Não há licença de código escolhida nesta preparação.** O repositório é público, sem concessão de licença geral de reutilização do código. A concordância dos titulares e as decisões aplicáveis de privacidade continuam sujeitas à confirmação humana. Nenhum logotipo externo foi acrescentado.

## Estabilização do escopo final

Consulte o [relatório de encerramento](docs/ENCERRAMENTO_ESCOPO_CINEMATCH.md). O piloto de títulos de 100 filmes foi preservado, sem executar as 98 consultas pendentes. A pesquisa com os três aliases funciona localmente. Sem credencial TMDB, o pôster usa o placeholder; testes simulados não homologam a API real. O notebook histórico não deve exportar seus módulos antigos sobre a aplicação atual; utilize uma cópia isolada.
