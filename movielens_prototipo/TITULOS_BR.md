# Títulos brasileiros na pesquisa

## Implementação e cobertura atual

**Atualização de 13/11/2026:** o índice passou de três para **30 filmes**, com 27 inclusões manuais verificadas em páginas brasileiras de Apple TV, Disney e HBO Max. São 30 de 9.742 filmes (aproximadamente 0,308%); 9.712 permanecem sem alias brasileiro cadastrado. Cada entrada registra a URL consultada e a data. Não houve consulta autenticada ao TMDB, coleta do piloto ou alteração do MovieLens. Para usar o novo índice, reinicie `app.py`: a busca é mantida em memória por processo.

O histórico abaixo descreve a cobertura anterior; a relação completa atual está ao final deste documento.

A pesquisa usa um índice auxiliar local em `titulos_br.json`, esquema `cinematch.titulos`, versão 1. Cada registro contém movieId, tmdbId, título exato do catálogo, ano, título brasileiro, lista de alternativas, URL de fonte e data de verificação. O MovieLens continua sendo o catálogo de identidade e avaliações.

Em 11/11/2026 foram conferidos 3 filmes com título brasileiro cadastrado, de 9.742 filmes no catálogo. Os demais 9.739 conservam a apresentação original. A cobertura é inicial e explícita. Nomes alternativos já presentes em parênteses no MovieLens continuam pesquisáveis. Os três registros novos ainda não contêm alternativas adicionais além do título brasileiro.

| movieId | tmdbId em links.csv | Título do MovieLens | Título brasileiro |
|---|---|---|---|
| 858 | 238 | Godfather, The (1972) | O Poderoso Chefão |
| 318 | 278 | Shawshank Redemption, The (1994) | Um Sonho de Liberdade |
| 3147 | 497 | Green Mile, The (1999) | À Espera de um Milagre |

Os nomes comerciais foram conferidos em fontes públicas brasileiras em 11/11/2026. Trata-se de curadoria manual, com associação aos registros reais de `movies.csv` e `links.csv`. A procedência é registrada por entrada.

- [O Poderoso Chefão, Apple TV Brasil](https://tv.apple.com/br/movie/o-poderoso-chefao/umc.cmc.3ew9fykdnpfaq9t2jq5da011c).
- [Um Sonho de Liberdade, HBO Max Brasil](https://www.hbomax.com/br/pt/movie/9b4dacba-2f80-4272-aac7-bb5e2ae91343).
- [À Espera de um Milagre, Apple TV Brasil](https://tv.apple.com/br/movie/a-espera-de-um-milagre/umc.cmc.7hcm0jk7o0ko95ghs171h7v41).

## Carregamento e responsabilidades

`titulos_alternativos.validar_aliases()` exige IDs positivos, associação coincidente com o mapeamento, título e ano do catálogo compatíveis, nomes válidos e procedência com data. IDs desconhecidos, IDs duplicados e vínculos divergentes são rejeitados. Dois filmes distintos podem compartilhar um alias, mantendo IDs e anos separados.

`carregar_aliases()` lê apenas arquivo local. Um índice ausente, corrompido ou incompatível resulta na busca original. Antes de disponibilizar uma atualização, deve-se executar o validador estrito para identificar a causa do erro. O carregamento público falha de modo conservador e não infere associações.

O Handler reutiliza `carregar_links()` e fornece o índice validado a `BuscaCatalogo` na construção da busca. As leituras ocorrem uma vez por modelo em cada processo, junto ao índice de pesquisa existente. A atualização do JSON exige reiniciar o servidor. A importação do módulo não realiza transporte HTTP. A consulta por tecla acessa somente a API local de busca.

`BuscaCatalogo` acrescenta os nomes ao conjunto de variantes de cada filme. A normalização mantém pesquisa sem acentos e sem distinção entre maiúsculas e minúsculas. O limite continua sendo oito sugestões e um resultado por movieId. Um título igual em anos diferentes exige escolha explícita. O parâmetro de ano continua aceitando a forma `Título (2000)`.

## Contrato e apresentação

`GET /api/filmes` conserva movieId, titulo, ano, generos e correspondencia. Quando houver alias validado, acrescenta `titulo_br`, incluindo ano, e `titulo_original`, contendo o título MovieLens original. O valor legado `titulo` é preservado. O autocomplete mostra o brasileiro na primeira linha e o nome do catálogo abaixo, usando nós de texto. As confirmações continuam enviando os IDs existentes.

A preferência visual brasileira aplica-se às sugestões e à seleção a confirmar. O perfil, o histórico retornado pelo backend e as recomendações mantêm os títulos do catálogo. Esta funcionalidade cobre o campo de pesquisa. A conversa por comandos foi descontinuada no escopo final.

Nenhuma alteração foi feita no recomendador, no treino/teste, nas métricas, nos CSVs ou no cache de pôsteres. Os módulos exportados pelo notebook permanecem intactos, portanto esta mudança não exige sincronizar suas cópias incorporadas.

## Possibilidade de expansão pelo TMDB

A documentação oficial disponibiliza detalhes com idioma, traduções e títulos alternativos. Uma futura coleta deverá ocorrer fora do caminho da pesquisa, com credencial de aplicação apenas no servidor, conexão HTTPS e mapeamento MovieLens–TMDB já validado. Não se usa busca por aproximação de título para criar vínculos.

O procedimento proposto é consultar traduções pelo ID, selecionar explicitamente português com país BR e submeter o resultado à revisão e ao validador local antes de atualizar o JSON. `titulo_br_tmdb()` interpreta somente uma resposta já obtida e exige ID coincidente, tradução pt/BR e título único válido. Ele retorna ausência em respostas vazias, inválidas, conflitantes ou sem tradução brasileira. As fixtures dos testes são sintéticas.

O parâmetro de idioma de detalhes pode devolver conteúdo de fallback. A seleção explícita em translations evita tratar automaticamente esse fallback como tradução brasileira. Títulos alternativos podem ser coletados por país BR e revisados separadamente. A expansão controlada implementada em `piloto_titulos.py` é descrita na seção seguinte. O programa realiza transporte somente mediante opção e aprovações explícitas. A indisponibilidade do TMDB não interfere no índice já existente.

Uma futura coleta deve respeitar o orçamento compartilhado de `operacao_externa.py`, validar destinos, limitar tamanhos e tempo, proteger credenciais e registrar procedência. O cache de pôsteres tem outra finalidade e permanece separado. Não foram executadas chamadas autenticadas à API TMDB.

- [Detalhes de filmes](https://developer.themoviedb.org/reference/movie-details).
- [Traduções](https://developer.themoviedb.org/reference/movie-translations).
- [Títulos alternativos](https://developer.themoviedb.org/reference/movie-alternative-titles).

## Condições e atribuição

Segundo a FAQ oficial, o uso não comercial da API requer atribuição. O TMDB pede logotipo aprovado e aviso de não endosso na seção de créditos. O aviso previsto é “This product uses the TMDB API but is not endorsed or certified by TMDB.” Uso comercial exige condições específicas. A revisão integral dos termos e da configuração operacional permanece necessária antes de ampliar a coleta real. A presente curadoria contém nomes confirmados em páginas públicas, sem transcrição de sinopses ou imagens. Não representa uma resposta obtida da API. [FAQ oficial](https://developer.themoviedb.org/docs/faq).

## Validação executada

Os três exemplos foram consultados no catálogo real em memória e retornaram como primeiro resultado os IDs 858, 318 e 3147, respectivamente. A versão sem acento de “À Espera de um Milagre” e a pesquisa “The Godfather” também foram conferidas.

Os testes sintéticos cobrem nomes originais, nomes brasileiros, acentos, caixa, anos diferentes, aliases repetidos, ausência de tradução, IDs e associações incompatíveis, falhas de leitura, operação offline, interpretação regional de resposta TMDB e preservação de ID/título/sessão na rota HTTP. O teste JavaScript verifica a apresentação das duas linhas e seleção por teclado.

As alterações foram realizadas na branch local `dev/proximas-atualizacoes`, no commit-base `b6f9aca`, com preservação das edições locais preexistentes. Não houve commit ou push. A suíte Python completa executou 302 testes, com 301 aprovados e um ignorado por bloqueio de socket local na sandbox. Os 36 testes JavaScript passaram. O módulo de autocomplete executou seus 15 testes sintéticos com sucesso. A verificação de integridade manteve os hashes de 68 arquivos protegidos, incluindo dados, resultados, experimentos, fontes históricas e módulos de recomendação/pôsteres. A validação de interface desta etapa usa DOM simulado; uma nova inspeção visual real em navegador permanece pendente.


## Expansão controlada — piloto de 100 filmes (11/11/2026)

### Branch e preservação

A branch local foi renomeada de `dev/proximas-atualizacoes` para `next-updates` no mesmo HEAD `b6f9aca2cc4bff57397fd3dfda16e92d90945999`. As referências locais e a lista de branches do GitHub foram conferidas antes da operação. O comando Git remoto falhou por resolução de nomes, e a leitura pelo conector GitHub retornou somente `main`. Imediatamente após a renomeação, o HEAD, o status e os hashes dos 641 arquivos anteriores coincidiram. As alterações de desenvolvimento preexistentes foram preservadas. Não houve commit ou push.

### Seleção efetivamente executada

O programa lê `movies.csv`, `ratings.csv` e `links.csv` locais e calcula contagem de todas as avaliações disponíveis por filme. Ordena por contagem decrescente e `movieId` crescente, sem sorteio. Essa prioridade enriquece somente nomes de pesquisa. O treinamento, os rankings do recomendador e a avaliação acadêmica não recebem esses contadores.

Foram selecionados 100 filmes reais. Os primeiros IDs e contagens são 356/329, 318/317, 296/307, 593/279 e 2571/278. Os 100 têm vínculos TMDB válidos. Os IDs 318 e 858 já estão cadastrados e serão pulados na coleta. O terceiro exemplo aprovado, ID 3147, continua cadastrado, embora não pertença ao top 100.

| Medida da execução local | Resultado observado |
|---|---:|
| Filmes selecionados | 100 |
| Vínculos TMDB válidos entre os selecionados | 100 |
| Vínculos ausentes/incompatíveis detectados no piloto real | 0 |
| Títulos já aprovados dentro do piloto | 2 |
| Filmes pendentes de consulta | 98 |
| Filmes efetivamente consultados no TMDB | 0 |
| Chamadas autenticadas executadas | 0 |
| Novos candidatos pt/BR encontrados | 0 |
| Novas homologações | 0 |
| Cobertura pública total | 3 de 9.742 |
| Filmes do catálogo sem alias brasileiro cadastrado | 9.739 |

Traduções ausentes, falhas HTTP e conflitos de respostas externas permanecem **não avaliados** nesta execução. O checkpoint contém zero ocorrências desses estados porque as 98 consultas não ocorreram. Isso não informa quantos filmes realmente têm tradução no TMDB. Os resultados simulados dos testes não entram nas contagens reais acima.

O ambiente verificado não contém `TMDB_READ_ACCESS_TOKEN`. A aprovação integral dos termos e da operação real segue pendente. A etapa executada foi o planejamento offline, sem transporte autenticado. Os três exemplos reais continuam retornando os mesmos IDs na busca local.

### Artefatos e retomada

A saída desta execução fica em `local/piloto_titulos_100_20261111/`, protegida pelo ignore existente. Contém `estado.json`, `candidatos.json` e `resumo.json`. O checkpoint inclui plano, hashes SHA-256 das três fontes, identidade do índice de origem, estados por filme, horários e contadores. Guarda somente candidatos de título e digest da resposta, sem persistir o corpo completo de traduções, sinopses ou credenciais.

O programa reutiliza o transporte seguro existente em uma especialização para `/movie/{id}/translations`. Não altera `posteres.py`. Após o encerramento de streaming, o transporte preservado do piloto fica em `transporte_tmdb.py`; `tmdb_disponibilidade.py` foi removido. Herda HTTPS de destino fixo, bloqueio de redirecionamento, timeout, validação MIME/JSON, teto de resposta, sanitização, quota e concorrência compartilhadas por credencial no processo. São limites internos configurados no projeto, não limites contratuais da API. Processos distintos não compartilham a quota de memória. A coleta deve ser operada de forma coordenada com outros consumidores da credencial.

A cada filme, uma gravação atômica com arquivo temporário e substituição registra o estado. Um hash do envelope detecta corrupção acidental. Retomadas exigem o mesmo plano e hashes de origem. O arquivo `.execucao.lock` impede duas execuções simultâneas na mesma saída. Se o processo for encerrado abruptamente e deixar esse marcador, verificar seu PID e a ausência de coletor ativo antes de autorizar a remoção desse marcador específico. Não realizar limpeza genérica da pasta.

Registros `preexistente`, `sem_tmdb`, `candidato`, `sem_traducao` e `conflito` são terminais. Erros só são repetidos com `--repetir-erros`. A interrupção durante uma consulta registra um erro retomável e pode exigir repetir apenas aquele item. Contadores de rede refletem chamadas registradas após o transporte retornar; encerramento abrupto pode impedir o registro da última chamada. As tentativas de processamento são contadas separadamente das chamadas efetivamente iniciadas pelo transporte.

Uma falha de autenticação, 429, timeout ou conexão encerra as consultas da rodada, preservando resultados anteriores. A pausa é persistida com referência temporal UTC. `Retry-After`, inclusive quando maior que o cooldown conservador, é respeitado entre processos pela pausa registrada. Não existem retries automáticos ilimitados. O orçamento configurável por rodada é no máximo 100 tentativas, e a quota compartilhada do transporte pode interromper antes disso. A retomada pula terminais já concluídos.

### Revisão dos candidatos

Uma tradução `pt/BR` fornecida pelo TMDB é um dado localizado da fonte e não prova, por si só, o título comercial oficial brasileiro. Respostas com outro ID, títulos conflitantes, dados inválidos ou ausência de tradução têm estados separados. Duplicatas idênticas são unificadas. Conflitos de mapeamento entre filmes distintos não geram associação por nomes.

Os novos títulos ficam em `candidatos.json` com `revisao=pendente`, fonte e hash de evidência. O validador do índice público rejeita registros explicitamente pendentes. O arquivo público `titulos_br.json` e seus três exemplos não são sobrescritos pelo piloto. Para homologar, revisar cada associação e sua procedência, aprovar explicitamente o registro e combinar os aprovados com o índice anterior, sem substituir ou perder os registros existentes. A promoção continua sendo uma edição manual revisada. Uma verificação posterior do índice e o reinício do servidor tornam a ampliação disponível offline.

### Comandos e autorização de coleta

Comando offline executado na raiz:

```sh
.venv/bin/python -B movielens_prototipo/piloto_titulos.py --saida local/piloto_titulos_100_20261111
```

Para uma coleta real futura, é necessário exportar uma credencial válida somente no ambiente do servidor e fornecer um arquivo privado de aprovação do escopo `titulos_filmes_pt_BR`. Esse arquivo deve conter `termos_aprovados=true`, `autorizacao_operacional=true`, o escopo e uma lista `documentos` com caminhos relativos e SHA-256 dos documentos revisados. O programa valida os hashes antes de construir o transporte. Não se forneceu esse registro de autorização nesta atividade. O mecanismo registra a decisão operacional e não autentica uma assinatura ou parecer jurídico.

Comando futuro, sujeito à aprovação e configuração dessas condições:

```sh
.venv/bin/python -B movielens_prototipo/piloto_titulos.py \
  --saida local/piloto_titulos_100_20261111 \
  --executar --aprovacoes local/APROVACAO_PRIVADA.json --max-consultas 20
```

Uma retomada após erro, respeitada a pausa, pode acrescentar `--repetir-erros`. O comando sem `--executar` apenas prepara ou revisa o checkpoint e não consulta a fonte. Saídas da CLI devem ficar sob `local/`. Pasta ocupada por arquivos estranhos, checkpoints corrompidos e planos incompatíveis são rejeitados, sem sobrescrever experimentos anteriores.

A FAQ do TMDB exige atribuição para uso não comercial e descreve logotipo aprovado, aviso de não endosso e créditos. A política específica de armazenamento dos metadados e os termos integrais precisam de revisão humana antes da coleta. O piloto minimiza armazenamento, mas essa decisão técnica não concede permissão contratual. [FAQ e atribuição](https://developer.themoviedb.org/docs/faq).

### Testes e próximos passos

Os testes em `testes_piloto_titulos.py` utilizam somente fixtures sintéticas, transportes injetados e relógios controlados. Cobrem top 100 determinístico, empate por ID, mapeamentos conflitantes, registros preexistentes, tradução vazia, idioma/região divergentes, duplicatas, checkpoint, escrita interrompida, exclusão mútua, 401/403, 429/Retry-After, timeout, conexão, ausência de credencial, aprovação de escopo e pesquisa offline após revisão de candidatos. Os casos anteriores de busca, sessão e recomendação permanecem na suíte principal.

Na primeira rodada direcionada, um teste usava um ID que fazia parte do próprio conjunto permitido da fixture. Foi corrigido para um ID realmente externo ao conjunto. Após acrescentar o caso de retomada com sucesso seguido de falha de rede, a rodada direcionada final passou com 11 casos. A suíte Python completa executou 313 testes, com 312 aprovados e um ignorado por bloqueio de socket local na sandbox, em 16,179 segundos. Os 36 testes JavaScript passaram. `git diff --check` passou. Os hashes de 79 arquivos protegidos foram preservados e somente os três documentos/módulos anteriores previstos nesta etapa mudaram. Não houve nova validação visual em navegador nesta expansão. Os logs de testes são locais e não constituem resultados de tradução reais.

A próxima expansão depende de concluir os requisitos de uso externo, executar o piloto autorizado e revisar candidatos antes de aumentar a cobertura pública. O top 100 favorece títulos populares e não mede cobertura uniforme de gêneros, épocas ou nacionalidades.

## Decisão de escopo final — 11/11/2026

A expansão foi retirada das prioridades. O piloto e seu checkpoint foram preservados sem executar as 98 consultas pendentes. Os três aliases homologados continuam sendo a única cobertura pública. Não há coleta na inicialização nem durante a digitação. Os resultados e comandos acima documentam a etapa anterior, sem constituir autorização de coleta futura.

## Expansão manual de 13/11/2026

O nome brasileiro foi conferido na página regional da fonte. O registro de origem foi associado ao título/ano exatos de `movies.csv`; o identificador TMDB foi obtido exclusivamente de `links.csv`, sem busca aproximada de IDs. Nenhuma sinopse, imagem ou oferta foi copiada. Essas páginas servem como evidência do nome, não como confirmação de disponibilidade em assinatura nem como autorização geral de uso de outros materiais. Os direitos das fontes continuam preservados.

A ampliação é uma curadoria limitada, não tradução automática nem cobertura completa do catálogo. O piloto antigo continua preservado com seu checkpoint original; o índice mudou, portanto sua retomada exigirá revisão de procedência/novo planejamento, sem alterar os hashes antigos. Não foi executada coleta de títulos pendentes.

| movieId | TMDB | Título brasileiro | Fonte |
|---|---|---|---|
| 858 | 238 | O Poderoso Chefão | [Página de referência](https://tv.apple.com/br/movie/o-poderoso-chefao/umc.cmc.3ew9fykdnpfaq9t2jq5da011c) |
| 318 | 278 | Um Sonho de Liberdade | [Página de referência](https://www.hbomax.com/br/pt/movie/9b4dacba-2f80-4272-aac7-bb5e2ae91343) |
| 3147 | 497 | À Espera de um Milagre | [Página de referência](https://tv.apple.com/br/movie/a-espera-de-um-milagre/umc.cmc.7hcm0jk7o0ko95ghs171h7v41) |
| 1270 | 105 | De Volta Para o Futuro | [Página de referência](https://tv.apple.com/br/movie/de-volta-para-o-futuro/umc.cmc.1alygfljzpxrofhgpoa6mmjnb) |
| 356 | 13 | Forrest Gump, o Contador de Histórias | [Página de referência](https://tv.apple.com/br/movie/forrest-gump-o-contador-de-historias/umc.cmc.5ov9f55aw8qvmd5pumhgnwu3e) |
| 364 | 8587 | O Rei Leão | [Página de referência](https://tv.apple.com/br/movie/o-rei-leao/umc.cmc.hzw12vgjjoz0tf0jn5m0x8i4) |
| 2959 | 550 | Clube da Luta | [Página de referência](https://tv.apple.com/br/movie/clube-da-luta/umc.cmc.70dbl3043tb6ealg0u12k1pih) |
| 79132 | 27205 | A Origem | [Página de referência](https://tv.apple.com/br/movie/a-origem/umc.cmc.6loas01ow0w4lkatxxloz7a6e) |
| 109487 | 157336 | Interestelar | [Página de referência](https://tv.apple.com/br/movie/interestelar/umc.cmc.1vrwat5k1ucm5k42q97ioqyq3) |
| 58559 | 155 | Batman: O Cavaleiro das Trevas | [Página de referência](https://tv.apple.com/br/movie/batman-o-cavaleiro-das-trevas/umc.cmc.1uf4c3neuc9yxhnjv7t4rd5wa) |
| 5952 | 121 | O Senhor dos Anéis: As Duas Torres | [Página de referência](https://tv.apple.com/br/movie/o-senhor-dos-aneis-as-duas-torres/umc.cmc.3j5r5wkkga96efci96q1kgjhi) |
| 7153 | 122 | O Senhor dos Anéis: O Retorno do Rei | [Página de referência](https://tv.apple.com/br/movie/o-senhor-dos-aneis-o-retorno-do-rei/umc.cmc.57s6i23z9ry0zsgwwc2mxjqi6) |
| 4993 | 120 | O Senhor dos Anéis: A Sociedade do Anel | [Página de referência](https://www.hbomax.com/br/pt/movie/fb9f961f-6302-4776-91d7-f1b7a69fb61d) |
| 4896 | 671 | Harry Potter e a Pedra Filosofal | [Página de referência](https://tv.apple.com/br/movie/harry-potter-e-a-pedra-filosofal/umc.cmc.55wxtmrughu40phd8lgr6qejr) |
| 527 | 424 | A Lista de Schindler | [Página de referência](https://tv.apple.com/br/movie/a-lista-de-schindler/umc.cmc.53hzoo3z0ufjb6wsxgspp2jlf) |
| 2028 | 857 | O Resgate do Soldado Ryan | [Página de referência](https://tv.apple.com/br/movie/o-resgate-do-soldado-ryan/umc.cmc.42f75umn5z16fkpofphe4re85) |
| 589 | 280 | O Exterminador do Futuro 2: O Julgamento Final | [Página de referência](https://tv.apple.com/br/movie/o-exterminador-do-futuro-2-o-julgamento-final/umc.cmc.1zt8xklrl4a6zim4n4iq2qyp2) |
| 6377 | 12 | Procurando Nemo | [Página de referência](https://tv.apple.com/br/movie/procurando-nemo/umc.cmc.6mbogy74hds0btkz7rj83hzhq) |
| 8961 | 9806 | Os Incríveis | [Página de referência](https://www.disneyplus.com/pt-br/browse/entity-850b6e92-07ea-4211-b3c3-cbbf1de045fa) |
| 3578 | 98 | Gladiador | [Página de referência](https://tv.apple.com/br/movie/gladiador/umc.cmc.50lk1pxm803ym8vizumxitxd2) |
| 7361 | 38 | Brilho Eterno de uma Mente sem Lembranças | [Página de referência](https://tv.apple.com/br/movie/brilho-eterno-de-uma-mente-sem-lembrancas/umc.cmc.4sao10xsyfeqf1t185lhrvo65) |
| 6539 | 22 | Piratas do Caribe: A Maldição do Pérola Negra | [Página de referência](https://www.disneyplus.com/pt-br/browse/entity-2d6036d7-f3b4-42c3-b1d3-cd5dd79bf307) |
| 2762 | 745 | O Sexto Sentido | [Página de referência](https://www.disneyplus.com/pt-br/browse/entity-219a5dfc-1b65-4644-9415-044c7d3a425d) |
| 586 | 771 | Esqueceram de Mim | [Página de referência](https://www.disney.com.br/novidades/onde-ver-online-todos-os-filmes-de-esqueceram-de-mim) |
| 2671 | 509 | Um Lugar Chamado Notting Hill | [Página de referência](https://tv.apple.com/br/movie/um-lugar-chamado-notting-hill/umc.cmc.3qn8yq9tq2vm3zizigtmls0ou) |
| 5816 | 672 | Harry Potter e a Câmara Secreta | [Página de referência](https://tv.apple.com/br/movie/harry-potter-e-a-camara-secreta/umc.cmc.69sq804vqp3dy39oxiajnr3ux) |
| 8368 | 673 | Harry Potter e o Prisioneiro de Azkaban | [Página de referência](https://www.hbomax.com/br/pt/movie/73553a76-1658-45f6-9e26-1b9c4443b0d6) |
| 68954 | 14160 | Up - Altas Aventuras | [Página de referência](https://tv.apple.com/br/movie/up---altas-aventuras/umc.cmc.7hyl1e1p1ihe8aiij3fzjwwyc) |
| 50872 | 2062 | Ratatouille | [Página de referência](https://tv.apple.com/br/movie/ratatouille/umc.cmc.2i8p6l6cpu6zxmcpqao7bs147) |
| 4886 | 585 | Monstros S.A. | [Página de referência](https://tv.apple.com/br/movie/monstros-sa/umc.cmc.3ilsdzy6ghi4adtg3tnwf6jcb) |

### Verificações desta ampliação

Em 13/11/2026 foram executados:

- `.venv/bin/python -B -m unittest discover -s movielens_prototipo -p testes.py`: **209 aprovados**, zero falhas e zero ignorados.
- `node --test --test-isolation=none movielens_prototipo/testes_autocomplete.cjs`: **19 aprovados**, zero falhas e zero ignorados.
- Validação estrita das 30 entradas contra o catálogo MovieLens e `links.csv`, seguida de 30 pesquisas pelo título brasileiro completo: todas retornaram o `movieId` esperado em primeiro lugar.
- Os três registros anteriores foram preservados integralmente. A comparação SHA-256 de 81 arquivos protegidos de dados, resultados, experimentos, reprodução e componentes compartilhados encontrou zero divergências.
- `git diff --check`: aprovado. Não houve novo teste visual, consulta autenticada, commit ou push nesta ampliação.

Foram acrescentados três testes do índice público em memória, sem exigir avaliações reais: novos nomes sem acentos/caixa, títulos originais/ano/referências anteriores e distinção entre obras das franquias. Os demais testes de ambiguidades, IDs inválidos e indisponibilidade da fonte permanecem na suíte. Os registros locais estão em `verificacoes/aliases_br_20261113/`, ignorados pelo Git.
