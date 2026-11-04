# Desenvolvimento e validação internos

Infraestrutura experimental separada da aplicação. Não implementa recomendador alternativo, busca de pesos ou avaliação de qualidade. A Etapa 5 arquitetural permanece pausada.

## Origem e protocolo

`divisao_interna.py` aceita apenas o arquivo chamado `treino.csv` cujo SHA-256 e tamanho coincidam com a entrada `resultados/treino.csv` de um manifesto experimental aprovado do esquema `cinematch.experimento.perfil`, versão 1, MovieLens Latest Small de 26/09/2018, divisão original semente 42 e fração 0,20. O manifesto de procedência é uma âncora fornecida explicitamente: não é assinado digitalmente nem prova autenticidade contra adulteração deliberada de ambas as entradas. O runner não abre `teste.csv`, `ratings.csv`, ranking ou matriz de produção. A procedência aprovada já contém a conferência da divisão original; não é necessário reconstituí-la usando o teste novamente.

Na execução real, o treino original contém 80.896 avaliações e o SHA-256 é `f4bfeae36b20990f5612be5ca36551ead9921a1fc9467c1484503530802850e0`. A conservação exata de seus registros e a identidade com a fonte aprovada impedem introduzir avaliações externas sem detectar divergência. Não se fez nova interseção contra o teste original: a garantia depende também da disjunção original já verificada e da procedência confiável.

Divisão interna: semente **101**, fração nominal **0,20**. Reutiliza `recomendador.dividir()` sem alterá-la: usuários/filmes ordenados, `numpy.random.default_rng(seed)` e `choice` sem reposição por usuário. Para histórico de tamanho n:

- n=1: nenhuma avaliação vai para validação; o registro permanece em desenvolvimento.
- n>=2: validação recebe `min(n-1, max(1, floor(n × 0,20)))` avaliações.
- Todas as demais avaliações ficam no desenvolvimento, preservando IDs, notas e timestamps.
- Nenhuma avaliação é removida por mínimo de usuário, filme ou quantidade de positivos ao dividir.

Essa proporção reserva dados para validação e mantém a maior parte para desenvolvimento, seguindo a regra do holdout existente, mas com semente distinta. O arredondamento por usuário explica por que não são exatamente 20% das linhas. Com históricos curtos, a regra pode reservar proporcionalmente mais que 20%; não duplica registros nem inventa observações. É holdout aleatório, não previsão temporal.

## Execução em uma pasta nova

A partir da raiz, usando o Python já disponível:

```sh
.venv/bin/python -B movielens_prototipo/divisao_interna.py \
  --treino movielens_prototipo/resultados/treino.csv \
  --procedencia experimentos/avaliacao_perfil_20261028/manifesto.json \
  --saida experimentos/NOVA_DIVISAO_INTERNA \
  --seed 101 --fracao 0.2
```

Nunca reutilizar diretório ocupado. A saída não pode ficar dentro dos diretórios de entrada. Reutiliza da Etapa 3 a reserva exclusiva, o marcador `.preparacao-em-andamento` e `assinatura()` para hashes/tamanhos. O manifesto só é escrito após os CSVs e a auditoria; falhas de escrita preservam o marcador. Não é utilizado o esquema de oito artefatos de produção: este conjunto não é um modelo da aplicação.

Saídas: `desenvolvimento.csv`, `validacao.csv`, `auditoria.json` e `manifesto.json`. Esquema `cinematch.experimento.divisao_interna`, versão 1. O manifesto registra UUID, horário UTC, dataset, identidade/hash do treino, hash do manifesto de procedência, semente original, algoritmo/semente/fração internos, contagens, hash canônico da união (todos os quatro campos), hashes de cada artefato, hashes do código e versões de Python/NumPy/pandas.

Parâmetros da divisão ficam em `parametros_divisao`; as definições propostas para experimentos futuros ficam em `protocolo_futuro`. Relevância continua >=4; referências 1–5; semente de referência proposta 201; mínimos propostos de usuário/filme 5. Esses parâmetros não filtram nem mudam as partições. Nenhuma recomendação ou métrica é gerada pelo runner.

Exemplo estrutural de manifesto (valores ilustrativos):

```json
{
  "esquema": "cinematch.experimento.divisao_interna",
  "versao_esquema": 1,
  "execucao_id": "UUID da execução",
  "fonte": {"treino": {"sha256": "hash de origem", "bytes": 123}},
  "parametros_divisao": {"seed": 101, "fracao_validacao": 0.2},
  "protocolo_futuro": {"relevante": 4.0, "referencias": [1, 2, 3, 4, 5]},
  "arquivos": {"desenvolvimento.csv": {"sha256": "hash do artefato", "bytes": 100}}
}
```

O exemplo abreviado não é um manifesto aceito pelo carregador. O real inclui todos os campos e arquivos obrigatórios.

## Fronteiras de acesso

- `validar_execucao(pasta)`: auditoria administrativa lê as duas partições, verifica hashes, ausência de duplicatas/sobreposição, conservação de todos os valores, contagens e reprodução do pertencimento pela regra e semente declaradas. Não constrói modelo ou contexto de preparação.
- `carregar_desenvolvimento(pasta, execucao_esperada=...)`: abre somente manifesto e desenvolvimento; retorna `DesenvolvimentoInterno`, que contém cópia da tabela e ID da execução, sem caminho ou referência para validação. `avaliacoes()` devolve outra cópia.
- `preparar_desenvolvimento(contexto, ...)`: rejeita DataFrames avulsos/diretórios. Em memória, aplica mínimos somente ao desenvolvimento e chama as funções existentes `ranking()` e `selecionar_referencias()`. Não lê estatísticas persistidas nem cria recomendações. Retorna estatísticas, referências positivas, histórico completo dos usuários elegíveis e parâmetros efetivos, vinculados à execução. Relevância permanece fixa em 4; não há mecanismo novo para otimizar sua escolha.
- `carregar_validacao(pasta, execucao_esperada=...)`: acesso explícito separado, destinado à etapa de métricas futura. Exige correspondência de execução. Nenhuma função de preparação aceita seu DataFrame diretamente.

O carregador de desenvolvimento confere seu próprio arquivo sem abrir validação: por desenho, não detectará sozinho validação ausente/corrompida. A auditoria integral deve ser executada separadamente antes de um futuro experimento; o carregador de validação também confere a integridade de sua partição. Não declarar o contexto de desenvolvimento como verificação integral do diretório.

São barreiras contra uso acidental, não isolamento de sistema operacional ou proteção contra Python hostil. Código futuro ainda poderá ler arquivos arbitrários se o programador contornar o contrato. O momento de carregar validação deve ser controlado por um runner futuro, após gerar listas; essa orquestração e as métricas não foram implementadas nesta etapa.

## Elegibilidade futura

Referências devem ser prefixos aninhados de 1–5 notas >=4 exclusivamente do desenvolvimento. Usuário sem n positivos não é elegível para aquele tamanho, sem completar com validação ou substituir por ranking geral. Preservar seu histórico no arquivo. Reportar separadamente coorte disponível por n e coorte fixa com cinco positivos, depois de aplicar o mínimo de treino individual.

Excluir dos candidatos todo o histórico individual de desenvolvimento, inclusive notas baixas e referências não utilizadas em um perfil menor. Notas faltantes não são rejeições. Candidatos e estatísticas deverão ser recalculados do desenvolvimento; não reutilizar `ranking_treino.csv` ou a matriz construída sobre as 80.896 notas completas. Algoritmos futuros devem declarar universo comum, população e sinais pessoais disponíveis antes da comparação. Não há garantia automática de comparabilidade de algoritmos que ainda não existem.

## Limitações

Uma divisão/semente não estima robustez a outros holdouts. Esta reserva interna não desfaz o conhecimento adquirido ao observar o teste original. Se a validação for usada repetidamente para selecionar alternativas, passa a ter função de desenvolvimento; ajustes devem usar subdivisões do desenvolvimento, reservando avaliação final apropriada. Não reutilizar o teste original para escolher versões.

Arquivos sem manifesto, esquemas/execuções incompatíveis, arquivos ausentes/corrompidos e divergências semânticas são rejeitados. Hashes não são assinaturas autenticadas; não protegem contra adulteração deliberada e coerente de manifesto e dados. O notebook não foi executado ou modificado: módulos de produção exportados por ele não mudaram e esta infraestrutura experimental não é dependência da aplicação/notebook.
