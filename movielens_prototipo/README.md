# CineMatch — MovieLens com perfil de filmes e conversa local

Adaptação do protótipo Python existente, mantendo pandas, NumPy, SciPy, servidor HTTP da biblioteca padrão e página HTML. O pipeline acadêmico continua separado da demonstração conversacional. Não exige LLM, API paga ou chaves.

## Executar no Linux / Pop!_OS

Recomendado: **Python 3.12**, ambiente usado na verificação. Abra um terminal na pasta `movielens_prototipo`:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-verificado.txt
.venv/bin/python app.py
```

Abra **http://127.0.0.1:8000**. Ctrl+C encerra. Se faltar `venv`, instale `python3-venv` pelo gerenciador do sistema. `requirements-verificado.txt` fixa as versões utilizadas; `requirements.txt` mantém faixas compatíveis para ambientes existentes (Python >=3.10; o pip seleciona versões compatíveis com o interpretador).

## Executar no Windows

Com Python 3.12 instalado, em PowerShell ou CMD, na mesma pasta:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-verificado.txt
.venv\Scripts\python app.py
```

Não precisa ativar o ambiente virtual. Os comandos Windows estão documentados, mas não foram executados neste ambiente Linux.

Na primeira execução, o projeto baixa MovieLens oficial e gera `resultados/`. Depois funciona sem internet. Se já tiver os CSVs, coloque `ratings.csv` e `movies.csv` em `dados/ml-latest-small/`, ou prepare com `python recomendador.py --dados /caminho/ml-latest-small`. Não exige disponibilidade em plataformas e não recomenda séries.

## Testar o fluxo completo na página

1. Digite pelo menos dois caracteres de um filme assistido, como `Toy Story`. Após cerca de 300 ms sem digitar, aparecem até oito sugestões locais com título, ano e miniatura opcional. Refine com o ano quando necessário. O catálogo pode usar nomes em inglês; nomes alternativos existentes na base também são pesquisados. Não há traduções ou sinopses geradas.
2. Escolha cada título/ano por mouse, toque ou setas e Enter. Nenhuma sugestão é selecionada automaticamente. Cada escolha vira um item removível, identificado por movieId; o campo fica livre para o próximo filme. Confira a seleção e clique em “Confirmar filmes selecionados”. Remakes permanecem opções distintas. Buscas sem resultados preservam os itens escolhidos.
3. A seleção inicial usa os primeiros cinco IDs distintos confirmados. A página mostra os usados e os assistidos fora do perfil. Todos os confirmados ficam no histórico e são excluídos das sugestões, mesmo os excedentes. Com um único filme, gera sugestões e avisa que o perfil é abrangente.
4. Veja até dez resultados, com gêneros, justificativa, média e quantidade de avaliações **do treino**. Se houver menos candidatos adequados, o sistema explica; não remove suas restrições para preencher a lista.
5. Use “Quero mais suspense”, “Não gosto de terror”, “Prefiro ficção científica”, “Assisti TÍTULO (ANO), mas não gostei”, “Quero considerar TÍTULO (ANO)” ou “Por que 1?”. Para “Por que você recomendou esse?”, pede título ou posição. Um título na conversa precisa ser exato e único; caso contrário, orienta a busca visual.
6. Use “Considerar” num filme fora do perfil. Se já houver cinco referências, escolha explicitamente qual substituir. A referência retirada continua no histórico. Novos filmes confirmados na busca preenchem as vagas livres, até cinco referências; quando o perfil está cheio, entram apenas no histórico. Um relato “Assisti TÍTULO” na conversa só atualiza o histórico: use “Considerar” para promovê-lo.
7. “Limpar minhas preferências” remove preferências de gênero; mantém histórico, referências e rejeições. “Reiniciar sessão” limpa tudo. Filmes rejeitados não voltam a ser referências positivas automaticamente.

**Interpretação local limitada:** comandos de preferência precisam começar com “Quero”, “Quero mais”, “Prefiro”, “Gosto de”, “Não gosto de”, “Quero evitar” ou “Sem”, seguidos por gêneros conhecidos. Pode separar comandos por ponto e vírgula. Não interpreta livremente enredos, atores, pronomes, restrições de ano ou frases complexas; entradas fora da gramática recebem orientação e preservam o estado e a lista. A antiga consulta de gêneros `modelo.recomendar(texto)` foi mantida para compatibilidade, mas não é usada no novo fluxo web.

Os títulos assistidos são referências **provisórias**, sem inferir uma avaliação positiva. Ao rejeitar um filme, ele sai das referências, permanece no histórico e não contribui mais para o perfil. A rejeição de um filme não equivale a rejeitar todos os seus gêneros.

## Motor e critérios de ordenação

Candidatos: filmes com pelo menos `min_filme` avaliações no treino (padrão 5), removendo todo o histórico assistido. Referências podem ser qualquer filme do catálogo, mesmo sem estatísticas suficientes para aparecer como candidato.

Para cada filme candidato com gêneros G e cada referência ativa com gêneros R, usamos Jaccard `|G ∩ R| / |G ∪ R|` (zero se a união for vazia). A similaridade S é a média dessas similaridades, dando o mesmo peso a cada referência. O marcador “no genres listed” não é um gênero positivo.

Preferências positivas P: o candidato precisa atender pelo menos uma, com afinidade `A = |G ∩ P| / |P|`. Se P estiver vazio, A=0. Gêneros negativos são exclusões obrigatórias: qualquer interseção elimina o candidato. Sem preferências positivas, quando há referências ativas, é exigida alguma similaridade de gênero. Sem referências ativas após rejeições, usa as preferências restantes e as estatísticas do treino; a explicação mostra quando a ordenação usa apenas estatísticas.

```text
W = (n × média_filme_treino + m × média_global_treino) / (n + m)
score = 0,65 × S + 0,25 × A + 0,10 × (W / 5)
```

Os pesos são escolhas didáticas fixas, não ajustadas pelo teste. Desempates: maior W, maior número de avaliações do treino, menor movieId. A média exibida é a média simples do treino, não W nem previsão individual. Até dez IDs distintos, com título/ano original, gêneros e justificativas baseadas nos termos realmente utilizados.

## Arquitetura e API

- `recomendador.py`: pipeline acadêmico, baselines e `Recomendador.recomendar_perfil(sessao)`.
- `conversa.py`: `interpretar_mensagem`, `Sessao` e orquestração `Conversa`; IDs são validados contra o catálogo e seleções contra a busca atual.
- `app.py`: transporte HTTP e armazenamento isolado por cookie aleatório HttpOnly/SameSite. Estado em memória, expira após duas horas sem atividade e desaparece ao encerrar o servidor. Abas do mesmo navegador compartilham a sessão; outro navegador/perfil tem outra sessão.
- `index.html`: busca, revisão, referências, substituição, resultados e conversa. Conteúdo do catálogo e mensagens são inseridos como texto.

`POST /api/recomendar` aceita ações JSON. Mantenha o cookie retornado entre requisições:

```json
{"acao":"estado"}
{"acao":"buscar","texto":"Toy Story; Jumanji"}
{"acao":"confirmar","ids":[1,2]}
{"acao":"mensagem","texto":"Não gosto de terror"}
{"acao":"considerar","movieId":260,"substituir":1}
{"acao":"rejeitar","movieId":1}
{"acao":"reiniciar"}
```

Os IDs acima são ilustrativos: só confirme IDs retornados na busca da sua sessão; só considere filmes já no seu histórico. A resposta inclui mensagem, histórico, referências, excedentes, rejeitados, preferências e recomendações. `userId` externo não seleciona nem compartilha sessões no novo endpoint. Servidor apenas para demonstração em `127.0.0.1`, sem persistência ou autenticação de produção.

## Validação e notebook

```sh
python testes.py
python -m unittest testes_conversa -v
python recomendador.py
```

Use o executável do ambiente virtual no lugar de `python`. A suíte principal inclui os testes originais de limpeza, divisão e métricas e os novos testes de perfil, conversa, matriz, integração do pipeline e HTTP. Os dados de fixture são sintéticos e servem para verificar regras, não para medir qualidade. O teste de recomendações reais só roda quando `resultados/relatorio.json` existe. O teste de sockets é explicitamente pulado se o ambiente proibir sockets; há um teste adicional do handler HTTP real com transporte em memória e cookies.

O notebook `Entrega_Matheus_MovieLens.ipynb` inclui os módulos atualizados, experimento acadêmico e demonstração da busca/seleção/conversa. Pode executar no Jupyter ou Colab; o download da base requer internet se os CSVs ainda não estiverem disponíveis. A página web continua destinada à execução local.

**Protocolo offline:** as métricas existentes medem somente os dois baselines, excluindo o histórico do treino por usuário. O novo perfil e a conversa não receberam avaliação de qualidade offline. Não atribuímos a eles métricas dos baselines. Se futuramente avaliar o perfil por histórico, escolha até cinco referências apenas entre os filmes do treino daquele usuário; qualquer escolha por avaliação deve usar exclusivamente notas do treino, nunca as notas escondidas. Mantenha todos os filmes desse treino na exclusão e use o teste apenas como alvo das métricas, com os mesmos candidatos/filtros. A conversa exige avaliação própria com usuários e julgamentos humanos.

Veja `RELATORIO_VERIFICACAO.md` para verificações atuais e limitações do ambiente, separadas dos números históricos do protótipo.

## O que corresponde à parte do Matheus

1. **Limpeza:** conversão dos tipos; descarte de registros sem campos essenciais, notas fora de 0,5–5 em passos de 0,5 e filmes fora do catálogo; remoção de avaliações repetidas usuário/filme mantendo a de timestamp mais recente. Não preenche ausências com notas inventadas.
2. **Divisão:** holdout aleatório por usuário; cerca de 20% para teste, semente 42, mantendo ao menos uma nota no treino. Não é simulação temporal; os timestamps de avaliação não provam quando o filme foi assistido.
3. **Elegibilidade:** usuários com pelo menos 5 notas no treino. Filmes com pelo menos 5 notas no treino entram nos rankings. Ambos os mínimos são configuráveis. Não há filtro por popularidade antes da divisão.
4. **Matriz:** CSR esparsa somente com notas de treino dos usuários elegíveis; inclui todos os filmes avaliados nesse treino. O catálogo dos baselines aplica o corte por filme separadamente. Ausência de entrada significa nota desconhecida, não rejeição. Os IDs e as posições são salvos em JSON.
5. **Baseline A:** número de avaliações por filme no treino (popularidade).
6. **Baseline B:** média ponderada `score = (n * media_filme + m * media_global_treino) / (n + m)`, com `m` igual ao mínimo de avaliações por filme. Não é exatamente a média simples nem um modelo personalizado.
7. **Avaliação:** Precision@10, Recall@10 e NDCG@10 macro por usuário, considerando relevante uma nota de teste >=4. Todos os itens elegíveis concorrem, sem amostragem de negativos. Itens já avaliados no treino são excluídos. Relevantes do teste fora do catálogo permanecem no denominador de Recall e no ideal do NDCG; assim não são apagados casos difíceis. Usuários sem relevantes no teste são excluídos dessas métricas e contabilizados no relatório. Precision divide por 10 mesmo que haja menos resultados.

O treino não recebe notas do teste. A divisão aleatória é reproduzível na mesma base e ambiente. O pacote registra o hash SHA-256 do ZIP de dados e versões das dependências da execução verificada. Mudar filtros exige comparar os mesmos usuários e reportar cobertura; não compare médias isoladas se a população mudou.

## Rodar a sua parte separadamente

```sh
python recomendador.py
python recomendador.py --min-filme 20 --min-usuario 5
python recomendador.py --dados /caminho/ml-latest-small
python testes.py
```

Use o executável do ambiente virtual no lugar de `python`, caso ele não esteja ativado. Pare o servidor e reinicie depois de recalcular os resultados, porque ele carrega os arquivos ao iniciar.

A pasta `resultados` contém:

- `filmes.csv`: catálogo e ano extraído do título.
- `indices_matriz.json`: IDs nas posições da matriz.
- `matriz_treino.npz`: matriz esparsa do treino.
- `metricas_por_usuario.csv`: resultados individuais de cada baseline.
- `ranking_treino.csv`: médias, contagens e notas ponderadas.
- `relatorio.json`: parâmetros, contagens e métricas agregadas.
- `teste.csv`: avaliações escondidas.
- `treino.csv`: avaliações disponíveis para construir o modelo.

## Dados e referências

Fonte dos dados e licença específica: https://files.grouplens.org/datasets/movielens/ml-latest-small-README.html
Download: https://files.grouplens.org/datasets/movielens/ml-latest-small.zip

O README permite redistribuição, inclusive transformações, sob as mesmas condições, exige reconhecimento em publicações e exige permissão para usos comerciais. O pacote não inclui os CSVs: baixa da fonte oficial e mantém `dados/` e `resultados/` fora do Git. Leia o README baixado para os termos completos. Essa versão é uma base de desenvolvimento que pode mudar; fixe a cópia/hash usada pelo grupo para reproduzir os resultados.

Referência do dataset: HARPER, F. Maxwell; KONSTAN, Joseph A. The MovieLens Datasets: History and Context. ACM Transactions on Interactive Intelligent Systems, v. 5, n. 4, artigo 19, 2015. https://doi.org/10.1145/2827872

Referência geral verificada: RICCI, Francesco; ROKACH, Lior; SHAPIRA, Bracha (eds.). Recommender Systems Handbook. 2. ed. Springer, 2015. https://doi.org/10.1007/978-1-4899-7637-6

Nota sobre a nova imagem: o artigo de Pedregosa et al. (2011), *Scikit-learn: Machine Learning in Python*, JMLR 12, p. 2825–2830 (https://www.jmlr.org/papers/v12/pedregosa11a.html) corresponde ao scikit-learn, não ao Surprise. Esta implementação não utiliza essas duas bibliotecas, KNN ou fatoração. Não descreva esses métodos como já implementados. Sarwar e Koren podem permanecer como referências teóricas do trabalho maior, se forem efetivamente usados pelo grupo; esta entrega não é uma revisão bibliográfica completa dessas obras.

## Erro de certificado no download inicial

Se aparecer `CERTIFICATE_VERIFY_FAILED`, o Python não conseguiu validar a cadeia de certificados do download. Isso acontece antes de iniciar o servidor. Baixe o ZIP oficial pelo navegador e salve-o em `dados/ml-latest-small.zip` (sem extrair); o aplicativo agora reconhece e extrai esse arquivo automaticamente. Também continua aceitando os CSVs já extraídos em `dados/ml-latest-small/`. Reinicie com o mesmo comando. A validação HTTPS permanece habilitada.

## Pôsteres opcionais — TMDB

O motor continua inteiramente MovieLens. A presença de pôster **não altera candidatos, ranking, baselines, matriz ou treino/teste**. Sem credencial, sem `links.csv`, sem internet, sem pôster ou com falha da API, o card usa um SVG local. Os títulos, gêneros e notas exibidos continuam vindo da base MovieLens.

### Configuração

1. Crie uma conta no [TMDB](https://www.themoviedb.org/) e solicite acesso em **Configurações → API**, informando o uso do projeto e aceitando os termos. Copie o **API Read Access Token** (token Bearer, não o campo API Key). Veja a [autenticação oficial](https://developer.themoviedb.org/docs/authentication-application).
2. Copie `.env.example` para `.env` **dentro de `movielens_prototipo`** e edite esse arquivo em seu editor:

   ```dotenv
   TMDB_READ_ACCESS_TOKEN=cole_seu_token_aqui
   ```

   Linux/Pop!_OS: `cp .env.example .env`. Windows PowerShell: `Copy-Item .env.example .env`. Também pode exportar a variável no ambiente do processo; ela tem precedência sobre o `.env`. O leitor local aceita as opções simples documentadas no exemplo e não executa comandos ou interpolação.
3. Verifique `dados/ml-latest-small/links.csv`, que acompanha o ZIP MovieLens. Se a preparação usou `--dados` em outra pasta, configure `MOVIELENS_LINKS_CSV` com o caminho absoluto para o `links.csv` correspondente. A ausência desse arquivo não força outro download nem bloqueia recomendações.
4. Reinicie `app.py` com o comando habitual. Busque e confirme filmes: os cards carregam pôsteres conforme entram na área visível. No autocomplete de assistidos, as sugestões já mostram miniaturas opcionais, carregadas separadamente da busca local de títulos.

Não compartilhe `.env`, tokens ou capturas que os mostrem. O `.env` e o cache são ignorados pelo Git. O token é enviado somente pelo backend no cabeçalho `Authorization`; não integra HTML, URLs públicas, respostas JSON, cache ou logs. Nenhuma dependência Python adicional é necessária. O navegador acessa apenas as imagens públicas do CDN do TMDB e o logo oficial; essas imagens não levam credencial.

### Metadados, idioma e cache

`posteres.py` carrega o mapa `movieId → tmdbId` de `links.csv`, descartando IDs vazios, não inteiros, não positivos e mapeamentos conflitantes. Nunca faz busca por título. `GET /api/poster/{movieId}` aceita somente IDs do catálogo e retorna a URL pública ou `/static/poster-placeholder.svg`. Os metadados são consultados apenas para imagens exibidas, em requisições separadas da recomendação; o catálogo inteiro não é consultado no início.

O backend consulta `/3/movie/{tmdbId}?language=pt-BR&append_to_response=images&include_image_language=pt,en,null`. Prioriza imagens marcadas `pt`, depois `en`, depois sem idioma; usa o `poster_path` dos detalhes como alternativa quando não há imagem adequada nessa lista. Valida o ID da resposta e os caminhos antes de montar URLs. Veja [detalhes por ID](https://developer.themoviedb.org/reference/movie-details) e [idiomas das imagens](https://developer.themoviedb.org/docs/image-languages).

A configuração de [endereços e tamanhos](https://developer.themoviedb.org/docs/image-basics) vem de `/3/configuration`, também sob demanda. Usa `https://image.tmdb.org/t/p/`, `w342` nos cards e `w185` nas miniaturas quando disponíveis; `w500`, mostrado na documentação oficial, é a alternativa caso a consulta de configuração falhe. A imagem mantém proporção 2:3, texto alternativo e `loading="lazy"`; imagem quebrada volta ao placeholder local.

O cache JSON em `cache_tmdb/metadados.json` armazena somente caminhos/configuração e validade, por **7 dias**, inclusive respostas válidas sem pôster. HTTP 404 recebe cache negativo de **24 horas**. Limite de 2.000 entradas recentes; para renovar manualmente, encerre o servidor e exclua essa pasta. Falha de leitura/gravação do cache não impede o funcionamento. Sem token, sempre retorna placeholder, mesmo se houver cache antigo.

Timeout de **3 segundos por chamada**, sem retentativas automáticas. Consultas autenticadas são serializadas e espaçadas a no máximo cinco por segundo; o frontend mantém no máximo duas buscas de metadados simultâneas. Erros de rede/JSON/resposta causam pausa global de 60 segundos; 401/403 pausam por 10 minutos. Para **429**, respeita `Retry-After` em segundos ou data HTTP (mínimo de 60 segundos). Durante a pausa, usa cache válido ou placeholder, sem repetir chamadas. O [limite do TMDB pode mudar](https://developer.themoviedb.org/docs/rate-limiting); não pressupomos cota garantida. Uma indisponibilidade do CDN é tratada pelo navegador com placeholder.

### Créditos e testes

A seção **Sobre / Créditos** inclui o logo **Primary short (blue)** aprovado, ligado à fonte oficial, e o aviso exigido. Fontes: [logos oficiais](https://www.themoviedb.org/about/logos-attribution) e [FAQ de atribuição](https://developer.themoviedb.org/docs/faq). O logo remoto pode não carregar sem internet, mas o texto de atribuição permanece disponível.

```sh
python -m unittest testes_posteres -v
python testes.py
```

Os testes TMDB usam somente respostas simuladas: mapeamento/ausências, preferência de idioma, ausência de pôster, falha da API, timeout, resposta inválida, 429, cache persistente/expiração, configuração, ambiente sem credencial, endpoint e preservação do ranking. **Não havia token disponível nesta implementação; a integração autenticada real não foi validada.**

## Autocomplete local de filmes assistidos

`busca.py` cria um índice em memória dos títulos do catálogo, sem chamar TMDB. `GET /api/filmes?q=...` retorna até oito resultados e não altera a sessão nem a busca pendente do fluxo antigo. `static/autocomplete.js` controla debounce de 300 ms, cancelamento com AbortController e um número crescente de consulta: respostas antigas são ignoradas mesmo se o transporte não respeitar o cancelamento. A entrada continua editável durante busca ou falha.

A comparação ignora caixa, acentos, espaços repetidos e pontuação. Ordem: título exato (com ou sem ano), início, trecho e aproximação. Nomes alternativos entre parênteses e artigos finais presentes no MovieLens também são indexados; não são traduções criadas ou obtidas por adivinhação. Se houver ano explícito entre parênteses, só concorrem filmes daquele ano. Números que fazem parte do título, como “Blade Runner 2049”, não são tratados como ano de lançamento. Desempates de buscas diretas são por título e movieId.

Para erros pequenos, usa `difflib.SequenceMatcher` da biblioteca padrão, sem nova dependência. Aproximação somente com pelo menos cinco caracteres, similaridade >=0,85 e diferença limitada de comprimento; compara nomes completos e janelas contíguas de palavras. Nos empates aproximados, prioriza o nome de comprimento mais próximo, depois título/ID. Não é compreensão semântica e pode não recuperar todos os erros; sugestões aproximadas são sinalizadas e sempre exigem escolha. Não se flexibiliza o limite quando nada corresponde.

A interface usa combobox/listbox com label, aria-expanded, aria-controls, aria-activedescendant, aria-selected, aria-busy e mensagens de status. Setas percorrem as opções; Enter escolhe apenas uma opção destacada e nunca envia o formulário da busca; Escape fecha e invalida consultas em andamento. Tab permite sair do campo para os controles. Miniaturas e rede externa são opcionais.

A seleção não tem limite de cinco filmes. Antes de confirmar, mostra quais preencherão as vagas de referência e quais serão excedentes; remover um item reordena esses rótulos. A confirmação `{"acao":"confirmar_selecao","ids":[...]}` valida todos os IDs no catálogo, preserva a ordem e elimina duplicatas. As regras anteriores de uma referência, máximo de cinco ativas e exclusão de todos os assistidos continuam no backend. O endpoint antigo de busca/revisão por lote permanece disponível para notebook e integrações.

Testes adicionais, na pasta do projeto:

```sh
python -m unittest testes_autocomplete -v
# Opcional: executar diretamente os testes do widget real com DOM/rede/relógio simulados:
node --test testes_autocomplete.cjs
```

A suíte principal `python testes.py` inclui esses testes. Node.js >=18 é opcional, usado somente para verificar o JavaScript, sem pacotes npm; sem Node, esse teste é marcado como pulado. A aplicação continua exigindo apenas Python e navegador. Os testes verificam acentos, aproximação conservadora, prioridade, anos/remakes, limite, IDs duplicados, confirmação independente de buscas concorrentes, debounce, respostas fora de ordem, mouse/toque, setas/Enter/Escape, remoção, excesso de cinco e preservação da seleção em falhas. O teste com DOM simulado não substitui uma avaliação com leitor de tela ou navegador real.

### Se as sugestões não aparecerem

O autocomplete mostra uma lista abaixo do campo e só adiciona um filme quando você escolhe uma opção. Teste com `Toy` ou `Matrix`. Use a página em `http://127.0.0.1:8000`, em vez de abrir `index.html` como arquivo.

Ao atualizar o código, encerre o **processo no terminal** com Ctrl+C e execute novamente `.venv/bin/python movielens_prototipo/app.py` a partir da raiz do workspace. O botão “Reiniciar sessão” limpa o perfil, mas não recarrega o código do servidor. Depois atualize o navegador com Ctrl+Shift+R.

Você pode abrir `http://127.0.0.1:8000/api/filmes?q=toy`: o servidor atualizado retorna JSON com `sugestoes`. Uma resposta 404 indica que o backend aberto ainda não possui esse endpoint. A interface agora avisa quando o script do autocomplete não carrega ou o servidor não possui a busca, preservando o restante da página. Se persistir, informe o título digitado e a mensagem exibida abaixo do campo.

Correção de 20/10/2026: o debounce agora chama os temporizadores no contexto do navegador, evitando `Illegal invocation`. Os testes da página simulam essa restrição de Window; os testes antigos com temporizadores genéricos não reproduziam a falha. Para um servidor que já responde ao endpoint `/api/filmes`, atualize a página principal com Ctrl+Shift+R para carregar a revisão `20261020-3` do widget.


## Reprodução e arquivos locais no Git

A partir da raiz do projeto, entre em `movielens_prototipo` e siga a instalação
Linux ou Windows acima. Use Python 3.12 e `requirements-verificado.txt` para o
ambiente fixado. Execute `python recomendador.py` para baixar o ZIP pela fonte
oficial `https://files.grouplens.org/datasets/movielens/ml-latest-small.zip`,
limpar os dados, dividir treino/teste e gerar a matriz, rankings e métricas em
`resultados/`. Depois execute `python app.py` para abrir a aplicação local.
Use o Python do ambiente virtual em todos esses comandos. CSVs já disponíveis
podem ser fornecidos com `python recomendador.py --dados /caminho/ml-latest-small`.

TMDB é opcional. No Linux, configure no ambiente do processo:

```sh
export TMDB_READ_ACCESS_TOKEN='SEU_TOKEN_LOCAL'
# Apenas se links.csv estiver em outra pasta:
export MOVIELENS_LINKS_CSV='/caminho/ml-latest-small/links.csv'
python app.py
```

No PowerShell, use `$env:TMDB_READ_ACCESS_TOKEN = 'SEU_TOKEN_LOCAL'` antes de
executar o servidor. Também é possível usar `.env`, conforme a seção TMDB.
O `.env.example` contém somente configuração vazia e caminhos fictícios.

Permanecem locais: ambientes virtuais, `.env`, credenciais, `dados/`,
`ml-latest-small/`, ZIPs do MovieLens e da exportação do notebook, `resultados/`,
`cache_tmdb/`, caches Python, logs, bancos SQLite e o documento Word de trabalho
na raiz. Bancos de outras extensões e novas exportações devem ficar em `local/`
ou `instance/`. Históricos reais devem ficar em `sessoes/`, `sessions/`,
`conversas/` ou `historicos/`; atualmente a aplicação mantém sessões em memória.
Não salve dados privados em fixtures, código ou documentação.

PDFs, planilhas, CSVs e ZIPs não são bloqueados globalmente por extensão: assets,
templates e fixtures sintéticas legítimas podem ser revisados e versionados.
Antes de adicionar novos arquivos, confira `git status --short --ignored` e
`git check-ignore -v CAMINHO`. O ignore não protege conteúdo sensível que esteja
em arquivos permitidos ou já rastreados.

O notebook versionado deve permanecer sem saídas de avaliações individuais,
CSVs incorporados, entradas pessoais de conversa, tokens ou caminhos privados.
Antes de adicioná-lo ao Git, limpe as saídas e revise os metadados. Preserve o
código e a explicação; mantenha apenas agregados necessários após revisão.
Para testar o projeto: `python testes.py`; Node.js, quando já instalado,
habilita os testes JavaScript incluídos na suíte.
