# Identidades internas — Etapa 4

## Contrato adotado

`identidades.py` é um módulo de domínio sem dependência de pandas, HTTP, arquivos ou banco de dados. Define dois valores imutáveis e utilizáveis como chaves de dicionário/conjunto:

```python
IdentidadeConteudo(fonte, tipo, id_original)
IdentidadeUsuario(fonte, id_original)
```

Conteúdos consideram **todos os três campos** em igualdade e hash. Usuários históricos consideram fonte e ID original. Usuário e conteúdo pertencem a classes distintas e nunca são iguais, mesmo com os mesmos textos. Não há ordenação implícita dessas identidades e o hash Python não é usado como identificador persistido.

`TipoConteudo` possui `FILME` e `SERIE`. `SERIE` está reservado apenas no contrato de identidade: não habilita recomendação, carregamento ou cadastro de séries.

```python
from identidades import IdentidadeConteudo, IdentidadeUsuario, TipoConteudo

filme_a = IdentidadeConteudo('fonte-a', TipoConteudo.FILME, '1')
filme_b = IdentidadeConteudo('fonte-b', TipoConteudo.FILME, '1')
serie_a = IdentidadeConteudo('fonte-a', TipoConteudo.SERIE, '1')
assert len({filme_a, filme_b, serie_a}) == 3

assert IdentidadeUsuario('fonte-a', '7') != IdentidadeUsuario('fonte-b', '7')
```

Fonte é um namespace canônico minúsculo, como `movielens` ou `fonte-a`. Não é a URL de download, o nome descritivo do dataset ou o UUID de preparação. Não se deduz esse namespace dos textos livres do manifesto da Etapa 3. Uma fonte futura que reutilize IDs com outros significados precisará de namespaces explicitamente distintos, sem reutilização acidental do namespace MovieLens.

`id_original` é texto opaco não vazio, sem espaços ou caracteres de controle. Não se normalizam zeros à esquerda ou caixa: `01` e `1`, assim como `ABC` e `abc`, permanecem distintos no contrato genérico. Não existe parsing de uma string concatenada de campos nem associação por título, ano ou gênero.

## Ponte MovieLens

```python
from identidades import (
    conteudo_movielens, movie_id_legado, usuario_movielens, user_id_legado,
)

identidade = conteudo_movielens(42)
assert identidade.fonte == 'movielens'
assert identidade.id_original == '42'
assert movie_id_legado(identidade) == 42
assert user_id_legado(usuario_movielens(7)) == 7
```

A ponte admite inteiros positivos Python/NumPy, rejeitando bool, float, texto numérico e demais entradas ambíguas com `ValueError`. Não faz coerção silenciosa. A conversão inversa exige a fonte `movielens`; para conteúdo, exige também `FILME`. O ID original deve ser decimal canônico positivo: `01`, `+1`, `1.0` e dígitos não ASCII não viram IDs legados. Essas conversões não comprovam existência no catálogo; a validação de pertinência continua nos componentes existentes.

## Integração sem mudança no algoritmo

`Recomendador.__init__()` mantém a assinatura e os atributos anteriores e acrescenta três mapas **somente em memória**:

- `identidades_conteudo`: `movieId` local → `IdentidadeConteudo` MovieLens.
- `identidades_usuarios`: `userId` local → `IdentidadeUsuario` MovieLens.
- `vistos_identificados`: usuário composto → conjunto imutável de conteúdos compostos.

Os dois primeiros mapas são pontes locais de uma única fonte. Não devem ser unidos por suas chaves numéricas para formar um catálogo global; numa coleção entre fontes, as chaves devem ser os próprios valores compostos.

`self.filmes`, `self.catalogo`, `self.vistos`, os DataFrames, as matrizes e os IDs em JSON continuam numéricos. Não se acrescentam colunas aos CSVs ou campos às respostas. As funções de preparação, divisão, baselines, avaliação e todos os métodos de recomendação permanecem iguais à Etapa 3. Somente o construtor ganhou as representações paralelas.

Nenhum cálculo de score, filtro ou desempate consulta os novos mapas. O desempate continua por `movieId` inteiro, sem converter a ordenação para strings ou identidades. As 14 caracterizações independentes continuam protegendo IDs, ordem, pontuações, referências, rejeições e preferências.

As sessões de visitantes continuam identificadas pelo cookie e guardam seus próprios filmes/preferências. Informar o filme 1 não associa o visitante ao `userId=1`. Não existe vinculação automática entre usuários de fontes diferentes ou entre usuários históricos e visitantes.

## Pontos numéricos identificados na auditoria

| Local | Uso atual | Risco ao misturar fontes diretamente |
|---|---|---|
| `carregamento_movielens.py` | Colunas originais dos CSVs | IDs são locais ao domínio MovieLens. |
| `recomendador.py`: limpeza | Conversão e deduplicação por usuário/filme | IDs iguais de fontes diferentes seriam tratados como o mesmo par. |
| `recomendador.py`: divisão, estatísticas e avaliação | Agrupamentos, conjuntos e vistos numéricos | Misturariam usuários, contagens e alvos de avaliação. |
| `recomendador.py`: matriz | Índices ordenados a partir dos IDs numéricos | Mapas de posição não carregam fonte/tipo por item. |
| `Recomendador.__init__()` | Deduplicação e junção por `movieId` | Catálogos mistos não podem ser fornecidos como se fossem MovieLens. |
| `recomendar_perfil()` / `recomendar()` | Exclusões e desempates por IDs | Identidades compostas não devem substituir números nesses métodos nesta etapa. |
| `busca.py` | Índice, deduplicação e retorno por `movieId` | Fora do escopo local, resultados poderiam colidir. |
| `conversa.py` | Histórico, referências, rejeições e pendentes | Uma sessão mista exigirá tradução explícita em etapa posterior. |
| `app.py` | IDs de requisições e rota `/api/poster/{movieId}` | Rotas atuais não identificam fonte ou tipo. |
| `static/autocomplete.js` / `index.html` | Duplicatas, seleção, remoção e conversão `Number(...)` | Contrato público permanece numérico e exclusivo de filmes. |
| `posteres.py` | Mapa `movieId → tmdbId`, rota de filme e cache `filme:tmdbId` | O tipo e a origem externos precisam ser considerados antes de ampliar o serviço. |
| `indices_matriz.json` | `userIds` e `movieIds` por posição | Persistência permanece no esquema MovieLens aprovado. |

O cookie `cinematch`, o UUID do manifesto e posições de matriz são outros identificadores, com significados diferentes. Não são IDs de usuário histórico nem de obra. O manifesto identifica o conjunto de resultados, não substitui a identidade de cada conteúdo.

`tmdbId` pertence ao TMDB e `imdbId` ao IMDb. O contrato genérico permite representá-los em namespaces próprios, sem converter um ID em outro. Nesta etapa os módulos de pôsteres e os vínculos explícitos já existentes em `links.csv` não foram modificados. O `imdbId` continua não utilizado pelo motor; zeros à esquerda não devem ser descartados numa conversão futura.

## Impactos e limites

- Busca, conversa, pôsteres, API e navegador não foram alterados; recebem/devolvem os mesmos IDs e campos.
- O recomendador atual é a ponte de um catálogo MovieLens, não um motor de catálogo misto. **Não é seguro concatenar CSVs de fontes distintas e entregá-los a esse caminho numérico.** As representações novas impedem colisão quando usadas como chaves, mas não migram automaticamente todos os consumidores antigos.
- As identidades novas não criam um adaptador para outro dataset nem habilitam séries. Não há fonte nova registrada, catalogada ou carregada.
- Metadados de fonte do manifesto não mudam automaticamente o namespace do modelo: seu esquema continua explicitamente MovieLens. Fazer essa vinculação exige contrato futuro, não inferência por URL ou nome.
- Nenhuma correspondência de obras é criada por título/ano/gênero. Resolver uma obra presente em duas fontes exige um vínculo explícito e validado no futuro.
- IDs numéricos continuam na persistência. Uma migração futura precisará de versão própria do esquema e compatibilidade de carga; não foi realizada agora.
- Há custo adicional de memória e inicialização pelos mapas paralelos. Os mapas em si são dicionários locais; os valores de identidade e os conjuntos de vistos compostos são imutáveis.
- Os conversores internos são deliberadamente estritos; entradas arbitrárias devem respeitar o contrato. Não foram alteradas as validações HTTP ou as conversões do navegador.

## Notebook e evidências da etapa

O notebook exporta cinco módulos sincronizados: `carregamento_movielens.py`, `artefatos_resultados.py`, `identidades.py`, `recomendador.py` e `conversa.py`. A exportação, importação e preparação/carga identificada com arquivos sintéticos foram verificadas em subprocesso temporário. O notebook completo não foi executado.

`testes_identidades.py` contém 21 testes sintéticos: colisões entre fontes e tipos, igualdade/hash, imutabilidade, usuários históricos, ida e volta de IDs legados, entradas inválidas, preservação dos dados e dos campos públicos, desempates numéricos e independência do visitante. A suíte principal inclui esse módulo.

Resultados medidos: antes, 93 testes Python (92 aprovados, um pulado); depois, 114 (113 aprovados, um pulado por socket). Os 11 cenários JavaScript passaram antes e depois. Os 21 testes novos e os 14 de caracterização foram também executados juntos, com 35 aprovações.

A comparação com a cópia do código da Etapa 3 confirmou igualdade de quatro DataFrames, stdout, sete arquivos textuais, matriz, vistos legados e recomendações para sessões sintéticas. Todas as funções e métodos, exceto `Recomendador.__init__()`, conservaram suas ASTs. Os hashes dos 15 arquivos reais de dados/resultados permaneceram iguais. Nenhuma recomendação de séries foi implementada e a Etapa 5 não foi iniciada.
