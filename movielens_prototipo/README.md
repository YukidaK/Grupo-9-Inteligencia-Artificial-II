# CineMatch — documentação técnica

Protótipo acadêmico de Ciência da Computação, FIB. Para instalação, consulte o [README principal](../README.md); todos os comandos deste documento partem da raiz do repositório.

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


## Aplicação implementada

`app.py` inicia um servidor HTTP local em `127.0.0.1:8000`. `index.html` e `static/autocomplete.js` compõem a interface. `busca.py` trata a busca e `conversa.py` mantém a seleção e a sessão; o nome do módulo foi preservado, mas não há conversa interativa.

O fluxo aceita de uma a cinco referências, rejeita confirmações fora desse limite e não recomenda com zero. Uma ou duas referências recebem orientação adicional, sem promessa de precisão. O autocomplete permite remover escolhas antes da confirmação. Uma nova confirmação substitui as referências e exclui o histórico já conhecido da sessão; “Nova seleção” reinicia a sessão e o conjunto de escolhas. A confirmação preserva navegação lógica de foco e não o rouba caso o usuário tenha navegado durante a requisição. Não há controles posteriores de rejeição ou preferência de gênero.

`Recomendador.recomendar_perfil()` calcula a média da similaridade Jaccard dos gêneros com as referências. A pontuação combina 0,65 de similaridade, 0,25 de preferência positiva e 0,10 de nota ponderada dividida por cinco. Preferências negativas filtram gêneros. Desempates usam nota ponderada, contagem e menor `movieId`. Filmes conhecidos não retornam como recomendações. Não se utiliza a matriz colaborativa para calcular essa similaridade.

`recomendador.py` limpa tabelas, divide treino/teste, prepara matriz esparsa, estatísticas e baselines. `carregamento_movielens.py` localiza, lê, extrai ou baixa os arquivos; `carregar()` continua sendo a entrada compatível. `artefatos_resultados.py` oferece saída identificada opcional, manifestos e integridade, mantendo carregamento legado sem alegar verificação completa de artefatos sem metadados. [Detalhes dos artefatos](ARTEFATOS_RESULTADOS.md) e [identidades internas](IDENTIDADES.md).

Os IDs MovieLens continuam públicos no caminho legado. `identidades.py` distingue fonte, tipo e ID original; isso prepara contratos, sem implementar séries. As sessões de visitantes não são usuários históricos do MovieLens. Não há banco de dados; o estado da sessão é temporário em memória.

## Pesquisa por títulos brasileiros

O autocomplete pesquisa aliases locais associados aos IDs MovieLens, com apresentação brasileira quando cadastrada. A cobertura inicial é de três filmes. Consulte [Títulos brasileiros](TITULOS_BR.md) para fontes, validação e limites.

## Pôsteres e dependências preservadas

`posteres.py` consulta opcionalmente metadados TMDB com IDs do mapeamento `links.csv`, sem associar títulos por aproximação. As imagens utilizam URLs públicas autorizadas do TMDB; o cache persistido é de metadados JSON, não um repositório de imagens. O TTL normal é sete dias, com políticas específicas para respostas negativas e falhas. Há deduplicação por chave, gravação atômica e orçamento de operações externas compartilhado. Sem credencial, mapeamento ou resposta utilizável, permanece o placeholder. Credenciais são de servidor e opcionais; a instalação básica funciona sem elas. Veja [proteção de pôsteres](PROTECAO_POSTERES.md) e o exemplo público `.env.example`, que não é carregado automaticamente como configuração.

Streaming foi retirado definitivamente do produto: não há painel, catálogo, preferências, filtro, cliente de disponibilidade ou rota `/api/streaming`. Os documentos das RF anteriores são registros históricos, não instruções para habilitar funcionalidades atuais. Consulte o [relatório do encerramento](../docs/ENCERRAMENTO_ESCOPO_CINEMATCH.md).

## Ambiente e comandos

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r movielens_prototipo/requirements-verificado.txt
.venv/bin/python -B movielens_prototipo/recomendador.py
.venv/bin/python -B movielens_prototipo/app.py
```

Ambiente de referência Python 3.12; versões registradas em `requirements-verificado.txt`. `requirements.txt` descreve dependências de forma mais ampla, sem garantir o mesmo ambiente. Obtenha antes os CSVs pelo [procedimento do dataset](../docs/DATASET.md). A preparação acima escreve no diretório padrão local `movielens_prototipo/resultados/`; preserve resultados anteriores. O carregamento reutiliza artefatos existentes, sem recalcular necessariamente a cada início. A opção `--resultados DIRETORIO_NOVO --identificar` permite saída separada; os experimentos devem usar diretórios novos.

```sh
.venv/bin/python -B -m unittest discover -s movielens_prototipo -p testes.py
node --test --test-isolation=none movielens_prototipo/testes_autocomplete.cjs
```

A suíte principal reúne testes sintéticos, HTTP simulado e experimentais. Recursos ausentes podem provocar skips condicionais; DOM simulado não comprova acessibilidade completa ou responsividade visual. Os comandos são instruções, não novos resultados de testes da GIT-02. Nenhuma instalação ou consulta externa foi realizada nesta preparação.

## Experimentos acadêmicos

Popularidade e nota ponderada usam avaliações de treino. A avaliação global histórica dos baselines difere da comparação condicionada aos candidatos do perfil. `avaliacao_perfil.py`, `divisao_interna.py` e `avaliacao_interna.py` separam os protocolos. `item_item_experimental.py` e `experimento_item_item.py` implementam filtragem colaborativa independente; **não são usados pela página**. [Guia portátil e parâmetros](../docs/REPRODUCAO_CHECKPOINT2.md), [agregados selecionados](../relatorios/checkpoint2/README.md) e [reprodução histórica](../reproducao/README.md).

As instruções antigas dos documentos de cada etapa podem citar `experimentos/` e `verificacoes/`, que são diretórios locais não distribuídos. O guia portátil explica como gerar uma cadeia nova. Não editar manifestos para adaptar hashes incompatíveis; o `conversa.py` atual difere de versões experimentais históricas.

## Notebook e limites

O notebook acadêmico existente foi preservado: 15 células, sete de código e nenhuma saída incorporada na revisão GIT-02. Contém instalação via pip, exportação de módulos, preparação, avaliação e conversa. Se executado, escreve arquivos e exporta um ZIP de resultados, inclusive individuais; use uma cópia em diretório isolado, revise cada célula e mantenha o ZIP local. Não executa automaticamente toda a cadeia experimental aqui descrita. O notebook foi retirado do índice na GIT-05 e permanece local; sua versão antiga continua acessível no histórico publicado. Não integra os 96 candidatos atuais.

Streaming e refinamento interativo foram descontinuados. Não há item–item na página, suporte a séries ou avaliação quantitativa da UX. Uma única divisão não mede robustez. Não foi concedida licença geral de reutilização do código; a concordância dos titulares e as condições integrais para ativação externa continuam pendentes. O histórico Git original permanece preservado. Dados originais, matrizes, partições e caches não integram a seleção pública.

## Estabilização do escopo final

Consulte o [relatório de encerramento](../docs/ENCERRAMENTO_ESCOPO_CINEMATCH.md). O piloto de títulos de 100 filmes foi preservado, sem executar as 98 consultas pendentes. A pesquisa com os três aliases funciona localmente. Sem credencial TMDB, o pôster usa o placeholder; testes simulados não homologam a API real. O notebook histórico não deve exportar seus módulos antigos sobre a aplicação atual; utilize uma cópia isolada.
