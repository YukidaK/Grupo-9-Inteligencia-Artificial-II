# CineMatch — documentação técnica

Protótipo acadêmico de Ciência da Computação, FIB. Para instalação, consulte o [README principal](../README.md); todos os comandos deste documento partem da raiz do repositório.

## Sistema de recomendação de filmes

### Problema e público

Em catálogos com milhares de títulos, o usuário pode perder tempo procurando o que assistir. O protótipo recomenda até dez filmes a partir de uma a cinco referências ativas. Com zero referências, não gera recomendações personalizadas. Uma ou duas referências são aceitas com orientação adicional; de três a cinco, segue o fluxo normal. Mais referências não garantem maior precisão.

Público: pessoas que usam serviços de streaming e querem descobrir filmes de acordo com seus interesses, sem precisar entender Machine Learning.

Entrada: de uma a cinco referências ativas, com preferências de gêneros e refinamento pelos comandos reconhecidos na conversa. Informar que assistiu a um filme não significa necessariamente que gostou dele.

Saída: até dez recomendações com justificativas. A comparação com os baselines de popularidade e nota ponderada pertence à avaliação experimental; o baseline de popularidade e o item–item experimental não geram as recomendações da página. A seleção de plataformas existe, mas a consulta real de disponibilidade e o filtro por assinatura continuam desativados.

### Direitos autorais e utilização

O CineMatch é um projeto acadêmico desenvolvido no contexto do curso de Ciência da Computação da FIB.

Seu código-fonte está disponível publicamente para consulta e conhecimento do projeto. Não é concedida, neste momento, uma licença geral para reutilização, modificação ou redistribuição do código, além dos direitos previstos na legislação aplicável e nos Termos de Serviço do GitHub.

Os direitos dos respectivos autores e as condições de utilização de recursos de terceiros, incluindo o dataset MovieLens, permanecem preservados.


## Aplicação implementada

`app.py` inicia um servidor HTTP local em `127.0.0.1:8000`. `index.html`, `static/autocomplete.js` e `static/streaming.js` compõem a interface. `busca.py` trata a busca e `conversa.py` mantém o perfil e interpreta comandos por regras, sem IA de conversa externa.

O perfil distingue histórico de assistidos, referências ativas e rejeições. Há de uma a cinco referências; zero referências impede recomendações personalizadas, preservando histórico e preferências. Uma ou duas referências são aceitas com orientação sobre a possibilidade de fornecer mais filmes, sem promessa de precisão. Excedentes permanecem no histórico, sem preencher automaticamente vagas. A retirada neutra preserva histórico e gêneros; “Não gostei” mantém seu significado de rejeição. O foco após confirmação ou retirada segue as correções UX-02.

`Recomendador.recomendar_perfil()` calcula a média da similaridade Jaccard dos gêneros com as referências. A pontuação combina 0,65 de similaridade, 0,25 de preferência positiva e 0,10 de nota ponderada dividida por cinco. Preferências negativas filtram gêneros. Desempates usam nota ponderada, contagem e menor `movieId`. Filmes conhecidos não retornam como recomendações. Não se utiliza a matriz colaborativa para calcular essa similaridade.

`recomendador.py` limpa tabelas, divide treino/teste, prepara matriz esparsa, estatísticas e baselines. `carregamento_movielens.py` localiza, lê, extrai ou baixa os arquivos; `carregar()` continua sendo a entrada compatível. `artefatos_resultados.py` oferece saída identificada opcional, manifestos e integridade, mantendo carregamento legado sem alegar verificação completa de artefatos sem metadados. [Detalhes dos artefatos](ARTEFATOS_RESULTADOS.md) e [identidades internas](IDENTIDADES.md).

Os IDs MovieLens continuam públicos no caminho legado. `identidades.py` distingue fonte, tipo e ID original; isso prepara contratos, sem implementar séries. As sessões de visitantes não são usuários históricos do MovieLens. Não há banco de dados; o estado da sessão é temporário em memória.

## Pôsteres e streaming

`posteres.py` consulta opcionalmente metadados TMDB com IDs do mapeamento `links.csv`, sem associar títulos por aproximação. As imagens utilizam URLs públicas autorizadas do TMDB; o cache persistido é de metadados JSON, não um repositório de imagens. O TTL normal é sete dias, com políticas específicas para respostas negativas e falhas. Há deduplicação por chave, gravação atômica e orçamento de operações externas compartilhado. Sem credencial, mapeamento ou resposta utilizável, permanece o placeholder. Credenciais são de servidor e opcionais; a instalação básica funciona sem elas. Veja [proteção de pôsteres](PROTECAO_POSTERES.md) e o exemplo público `.env.example`, que não é carregado automaticamente como configuração.

A seção de streaming permite guardar região BR, IDs e modo RESTRITO/FLEXÍVEL na sessão. Provedores retirados do catálogo são preservados para revisão e remoção explícita. **O catálogo público homologado continua vazio, o transporte de disponibilidade não é ativado e as preferências não filtram recomendações de produção.** Não há confirmação de oferta por assinatura na página. O código isolado e os testes simulados não constituem autorização de uso externo. Veja [interface](STREAMING_WEB.md), [contrato](DISPONIBILIDADE.md), [transporte](TRANSPORTE_TMDB.md), [filtro isolado](FILTRO_STREAMING.md), [homologação](HOMOLOGACAO_STREAMING.md) e [preparação operacional](PREPARACAO_STREAMING.md).

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
node --test movielens_prototipo/testes_autocomplete.cjs movielens_prototipo/testes_streaming.cjs
```

A suíte principal reúne testes sintéticos, HTTP simulado e experimentais. Recursos ausentes podem provocar skips condicionais; DOM simulado não comprova acessibilidade completa ou responsividade visual. Os comandos são instruções, não novos resultados de testes da GIT-02. Nenhuma instalação ou consulta externa foi realizada nesta preparação.

## Experimentos acadêmicos

Popularidade e nota ponderada usam avaliações de treino. A avaliação global histórica dos baselines difere da comparação condicionada aos candidatos do perfil. `avaliacao_perfil.py`, `divisao_interna.py` e `avaliacao_interna.py` separam os protocolos. `item_item_experimental.py` e `experimento_item_item.py` implementam filtragem colaborativa independente; **não são usados pela página**. [Guia portátil e parâmetros](../docs/REPRODUCAO_CHECKPOINT2.md), [agregados selecionados](../relatorios/checkpoint2/README.md) e [reprodução histórica](../reproducao/README.md).

As instruções antigas dos documentos de cada etapa podem citar `experimentos/` e `verificacoes/`, que são diretórios locais não distribuídos. O guia portátil explica como gerar uma cadeia nova. Não editar manifestos para adaptar hashes incompatíveis; o `conversa.py` atual difere de versões experimentais históricas.

## Notebook e limites

O notebook acadêmico existente foi preservado: 15 células, sete de código e nenhuma saída incorporada na revisão GIT-02. Contém instalação via pip, exportação de módulos, preparação, avaliação e conversa. Se executado, escreve arquivos e exporta um ZIP de resultados, inclusive individuais; use uma cópia em diretório isolado, revise cada célula e mantenha o ZIP local. Não executa automaticamente toda a cadeia experimental aqui descrita. O notebook foi retirado do índice na GIT-05 e permanece local; sua versão antiga continua acessível no histórico publicado. Não integra os 96 candidatos atuais.

Não há disponibilidade real homologada, streaming operacional, item–item na página, suporte a séries ou avaliação quantitativa da conversa e da UX. Uma única divisão não mede robustez. Não foi concedida licença geral de reutilização do código; a concordância dos titulares e as condições integrais para ativação externa continuam pendentes. O histórico Git original permanece preservado. Dados originais, matrizes, partições e caches não integram a seleção pública.
