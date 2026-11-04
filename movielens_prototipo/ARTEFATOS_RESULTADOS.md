# Resultados isolados e identificados — Etapa 3

## Contrato anterior e compatibilidade

Antes desta etapa, `preparar(pasta=None, min_filme=5, min_usuario=5)` gravava oito arquivos em `ROOT/resultados`. Retornava `(treino, teste, filmes, stats)` e imprimia o relatório. `carregar_modelo()` verificava a existência de `relatorio.json`; quando ausente, chamava `preparar()` sem argumentos. Depois lia somente `filmes.csv`, `ranking_treino.csv` e `treino.csv`.

Esse modo continua sendo o padrão para diretórios **sem manifesto e sem marcador de preparação identificada**. Não há novos avisos, mudança de retorno ou exigência de matriz para carregar um legado. O conteúdo dos artefatos e os cálculos não mudaram. O status de `validar_resultados()` para o legado é:

```python
{'estado': 'legado_sem_manifesto', 'integridade_verificada': False}
```

O código não declara que a integridade ou a origem desse legado foi comprovada. A preparação legada ainda sobrescreve seus arquivos como antes, mas não pode sobrescrever uma pasta que já esteja identificada ou em preparação identificada.

## Diretório opcional

```python
from recomendador import preparar, carregar_modelo
from carregamento_movielens import URL_MOVIELENS

identidade = {
    'nome': 'MovieLens Latest Small',
    'versao': None,  # informar uma versão somente quando comprovada
    'fonte': URL_MOVIELENS,
}

# Exemplo de uso, não executado sobre dados reais nesta etapa.
treino, teste, filmes, stats = preparar(
    pasta='/caminho/dos/csvs',
    diretorio_resultados='execucoes/movielens/execucao-001',
    identificar=True,
    dataset=identidade,
)
modelo = carregar_modelo(
    'execucoes/movielens/execucao-001',
    exigir_manifesto=True,
    dataset_esperado=identidade,
)
```

`diretorio_resultados=None` mantém `ROOT/resultados`. A seleção é feita por chamada, sem estado global que troque automaticamente o dataset do servidor. `identificar=False` não gera manifesto. Metadados `dataset` exigem `identificar=True`, evitando descartá-los silenciosamente.

O CLI de preparação oferece `--resultados DIRETORIO` e `--identificar`. O CLI identificado usa o nome MovieLens, a URL configurada e versão desconhecida (`null`); a função Python permite informar uma versão comprovada. Os argumentos antigos permanecem válidos. Nenhum endpoint ou elemento da interface web foi alterado.

Um diretório explicitamente solicitado a `carregar_modelo()` não é preparado automaticamente se estiver incompleto ou ausente: gera `ErroArtefatos`, sem download. A preparação automática antiga permanece somente no caminho padrão legado.

## Estrutura de uma execução identificada

```text
execucao-001/
├── filmes.csv
├── indices_matriz.json
├── manifesto.json
├── matriz_treino.npz
├── metricas_por_usuario.csv
├── ranking_treino.csv
├── relatorio.json
├── teste.csv
└── treino.csv
```

Os oito artefatos pertencem ao mesmo manifesto, inclusive os arquivos que a página não lê. Durante a geração existe `.preparacao-em-andamento`. Esse marcador é criado exclusivamente; o manifesto é escrito por último e o marcador é removido somente ao concluir. Uma falha deixa o marcador e impede carregar os resultados como legado. Não há recuperação ou limpeza automática.

Identificação requer pasta nova ou vazia. O modo identificado não reutiliza nem sobrescreve resultados existentes. Os nomes e formatos dos oito arquivos foram preservados.

## Manifesto

- `esquema` e `versao_esquema`: contrato de resultados MovieLens com avaliações explícitas. Não é suporte genérico a outras fontes.
- `execucao_id`: UUID único da preparação; `criado_em`: data/hora com fuso.
- `dataset`: nome, versão declarada (ou `null`) e fonte.
- `parametros`: semente, fração de teste, mínimos de avaliações, tamanho da lista e limiar de relevância usados pela implementação atual.
- `entradas`: hashes SHA-256 e tamanhos dos CSVs de origem, quando disponíveis no caminho usado. Em testes com carregador substituído e sem arquivos físicos, esse registro pode ser vazio.
- `arquivos`: inventário obrigatório dos oito resultados, cada um com SHA-256 e tamanho em bytes.

Exemplo completo produzido por preparação **sintética** e validado durante esta etapa. Não representa os dados reais do projeto:

```json
{
  "esquema": "cinematch.movielens.resultados",
  "versao_esquema": 1,
  "execucao_id": "88bb3b85-23c9-46ea-82c8-3c4bd7eba905",
  "criado_em": "2026-10-29T00:02:30.769007+00:00",
  "dataset": {
    "nome": "Fixture",
    "versao": "v1",
    "fonte": "local-sintetico"
  },
  "parametros": {
    "seed": 42,
    "fracao_teste": 0.2,
    "min_avaliacoes_filme_treino": 5,
    "min_avaliacoes_usuario_treino": 5,
    "k": 10,
    "relevante": 4.0
  },
  "entradas": {
    "ratings.csv": {
      "sha256": "1ca2473a3d7d95e0fcc1a48c44b91fad2668dce9f8e35d070aff4ebbf849a7d7",
      "bytes": 608
    },
    "movies.csv": {
      "sha256": "7fc7a9975ebaac218983ac9dea25cb7a2f31306980f585ce61abb11ff7c921ce",
      "bytes": 293
    }
  },
  "arquivos": {
    "treino.csv": {
      "sha256": "3f53192dd2c19e299f3856d1008c2081004ef9731eb067ce58ae65bb1570cdbe",
      "bytes": 536
    },
    "teste.csv": {
      "sha256": "a9f591ec7a3119072b84e52679a915c0c2c89fc67898067f66818b2aac6a082d",
      "bytes": 104
    },
    "filmes.csv": {
      "sha256": "344ba17f5d13ba98e2c9a072b8bb482a2d1ecdd65082b4b07e1650772828a3b9",
      "bytes": 337
    },
    "ranking_treino.csv": {
      "sha256": "64d66c9e12d1f8ae1a3668875387397cc430460aa1b35c4d1e6ad8063bad2072",
      "bytes": 196
    },
    "matriz_treino.npz": {
      "sha256": "c03e9fc96db5e41701049b33a9b3f1013348238a4d313b4331460c6aac8e0066",
      "bytes": 1026
    },
    "indices_matriz.json": {
      "sha256": "407203f5251dce9f6493c6eb17307b70df102f6a489089e42a5326c40322a6ab",
      "bytes": 69
    },
    "metricas_por_usuario.csv": {
      "sha256": "58e6c9a3b30f6f674bb4e736d84ae5d570de23c46a418644f958b88ee236fe02",
      "bytes": 412
    },
    "relatorio.json": {
      "sha256": "6ea84541b5ca1d583198fde53244c47d314292b83624baf43663073009b902d0",
      "bytes": 1186
    }
  }
}
```

## Validação

Quando existe `manifesto.json`, `carregar_modelo()` valida automaticamente o conjunto completo antes de construir `Recomendador`. Não há fallback para legado em caso de manifesto inválido.

São detectados:

- Preparação incompleta e manifesto obrigatório ausente.
- JSON inválido, metadados obrigatórios ausentes, esquema/versão não suportados, UUID/data inválidos.
- Inventário incompleto, artefatos extras no inventário e assinaturas malformadas. Os nomes aceitos são fixos; o manifesto não escolhe caminhos arbitrários.
- Artefato ausente, link simbólico no lugar de artefato, tamanho ou hash divergente.
- Parâmetros diferentes entre manifesto e relatório.
- Colunas essenciais ausentes, contagens divergentes, IDs de matriz incompatíveis e pares duplicados ou sobrepostos.
- Matriz ilegível, dimensão ou número de entradas incompatível, e valores diferentes das notas de treino.
- Incoerências básicas entre catálogo, ranking e avaliações.
- Métricas individuais ilegíveis ou com colunas inválidas; o CSV vazio legítimo quando não há relevantes continua aceito.
- Dataset, versão, fonte ou UUID diferentes dos valores esperados fornecidos pelo chamador.

`dataset_esperado` pode informar um subconjunto de `nome`, `versao` e `fonte`; todos os campos fornecidos precisam coincidir. `execucao_esperada` permite fixar um UUID. O erro específico é `ErroArtefatos`, subclasse de `RuntimeError`; a aplicação atual já trata `RuntimeError` na inicialização.

Os hashes de entrada são registro de procedência, não uma exigência de manter os CSVs originais acessíveis ao carregar resultados portáveis.

## Limitações e cuidados

- Se um manifesto concluído for removido, seus arquivos se tornam indistinguíveis de um legado. Por isso consumidores do modo novo devem usar `exigir_manifesto=True` ou informar expectativas. O modo padrão permanece permissivo para preservar compatibilidade.
- Trocar um único arquivo por conteúdo diferente de outra execução viola os hashes. Trocar o conjunto inteiro, com manifesto íntegro, somente é recusado por identidade quando o chamador informa o dataset/UUID esperado. Conteúdo byte a byte idêntico não pode ser atribuído a outro UUID apenas pelos hashes.
- O manifesto detecta mistura e corrupção acidentais; não é assinatura digital nem prova de autenticidade. Quem reescrever os arquivos e todo o manifesto pode forjar metadados. As verificações estruturais adicionais não equivalem a recalcular todas as métricas ou estatísticas.
- Não há bloqueio contra edição externa durante/depois da carga nem transação de diretório. O marcador protege o fluxo cooperativo de preparação e os diretórios identificados não são reutilizados.
- A carga identificada lê e confere também treino, teste e matriz: tem custo maior que o modo legado.
- `links.csv` e o cache de pôsteres não integram os oito resultados. Continuam separados e não influenciam a recomendação; esta etapa não passa a selecionar automaticamente esses recursos pela origem do manifesto.
- `nome`, `versao` e `fonte` são declarações, acompanhadas dos hashes disponíveis. Não se deduz a edição do dataset pelo nome da pasta.

## Notebook e validação desta etapa

O notebook exporta `carregamento_movielens.py`, `artefatos_resultados.py`, `recomendador.py` e `conversa.py`, com conteúdo sincronizado. A célula de exportação e uma preparação/carga identificada sintética foram testadas em subprocesso temporário. Não foram executadas células de instalação, download ou interação.

Testes automatizados novos: `testes_artefatos.py`. A suíte principal os inclui através de `testes.py`. Os testes usam arquivos sintéticos e temporários, com a rede bloqueada por mock.

Na validação, a suíte anterior registrou 67 testes (66 aprovados, um pulado por socket). Após a etapa, registrou 93 (92 aprovados, um pulado por socket), incluindo 26 testes novos, os 14 da Etapa 1 e os oito da Etapa 2. JavaScript: 11 cenários aprovados antes e depois.

Uma comparação com a cópia do código anterior à Etapa 3 confirmou igualdade dos quatro DataFrames, stdout, sete arquivos textuais, matriz e recomendações em preparação sintética. A classe `Recomendador` e as demais funções fora de `preparar()`/`carregar_modelo()` mantiveram suas ASTs. Os hashes dos 15 arquivos reais de dataset/resultados permaneceram iguais. Não houve publicação ou execução da Etapa 4.
