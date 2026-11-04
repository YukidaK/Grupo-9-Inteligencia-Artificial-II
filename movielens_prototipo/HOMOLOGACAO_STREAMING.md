# RF-02E1 — Catálogo e homologação visual

Atividade realizada com auxílio do Codex em 30/10/2026. Nenhuma chamada autenticada TMDB, disponibilidade de filme, instalação ou ativação externa foi realizada.

## Catálogo e evidência

O catálogo público permanece com **zero provedores homologados**. A documentação oficial confirma a operação de lista de provedores de filmes e o parâmetro `watch_region=BR`, mas não foi obtida nesta investigação uma resposta regional verificável com IDs atuais. Exemplos de documentação não foram promovidos a evidência de presença no Brasil. Nenhum ID foi atribuído por nome.

Arquivos novos: `catalogo_streaming.py`, `catalogo_streaming_br.json` e `testes_catalogo_streaming.py`. O módulo valida esquema, região, datas com fuso, IDs distintos, correspondência exata ID/nome numa evidência regional e SHA-256. Só entradas `homologado` são expostas. Entradas `pendente` exigem justificativa e ficam ocultas. A aplicação carrega o catálogo local; erro de leitura/validação resulta em catálogo vazio. A chamada direta ao validador mantém erro explícito para auditoria. Hash assegura integridade local, não autenticidade da origem, atualidade ou aprovação jurídica.

Formato: raiz com `esquema=cinematch.catalogo_streaming`, `versao=1`, `regiao=BR`, `verificado_em` ISO com fuso, `provedores`. Cada entrada contém `id`, `nome`, `regiao`, `estado`, `verificado_em`, `procedencia={url,arquivo,sha256}`. O arquivo relativo de evidência, contido na pasta do catálogo, deve ter somente `url`, `regiao`, `tipo=FILME`, `obtido_em` e `resposta`, cujo `results` comprova o par `provider_id/provider_name`. Não guardar tokens nem cabeçalhos. Exemplos fictícios reproduzíveis estão exclusivamente nos testes, nunca no catálogo público.

Procedimento futuro, sujeito a autorização: revisar termos/configuração; obter no servidor uma resposta oficial de `/3/watch/providers/movie?watch_region=BR&language=pt-BR`, sem consultas de filmes; preservar corpo público e contexto no envelope; calcular hash; revisar manualmente IDs/nomes/região/data; registrar pendências separadamente; validar em arquivo temporário e executar testes antes de promover a configuração. O carregamento ocorre na inicialização: atualização exige reiniciar o processo e implica a conhecida perda de sessões em RAM. Não há atualização automática. Um provedor regional não prova oferta de assinatura de qualquer obra.

## Interface e capturas reais

Firefox instalado conseguiu renderizar com backend X11 e renderização por software, perfil temporário, proxy fechado e fetch simulado. Chromium não foi localizado. A causa exata do erro 139 anterior não foi demonstrada. Houve avisos IPC/políticas e o processo não encerrou normalmente; depois de gerar cada captura, o harness encerrou exclusivamente seu próprio grupo de processos (saída -15). Nenhum sandbox de navegador foi desabilitado.

Foram capturados sete cenários antes e sete depois: catálogo público vazio a 360/768/1366/1920 px, catálogo sintético a 360/1366 px e erro a 360 px. Os screenshots utilizam HTML/JS reais em arquivos locais e dados de API simulados; não comprovam navegação ponta a ponta pelo servidor. Recursos de imagem externos foram substituídos localmente. Provedores fictícios são identificados como fixtures.

Em todas as larguras públicas, `scrollWidth` foi respectivamente 348/756/1354/1908 px, inferior à largura da janela: sem transbordamento horizontal medido. Na fixture móvel, os rótulos de serviços mediram 270×66 px; no notebook cerca de 330,67×66 px, em três colunas. Seleções sintéticas restauradas: duas, com contagem correspondente. Estados de erro oferecem explicação e nova tentativa sem impedir o fluxo de filmes.

Correções mínimas: esconder fieldset de serviços vazio; reduzir e esclarecer os textos sobre catálogo pendente e filtro desativado; acrescentar outline CSS explícito nos controles focados do formulário. Mantidos modos nativos, labels, fieldsets, aria-live e botões existentes. Não houve novo endpoint, mudança de sessão, algoritmo ou transporte.

A inspeção visual das imagens confirmou organização sem sobreposição aparente na seção, textos legíveis e grade adaptada. O painel ainda exige rolagem no celular: melhoria opcional futura seria compactá-lo após configuração. Não foi feita navegação física por Tab/leitor de tela. Embora `activeElement` identifique o rádio focado, o Firefox headless retornou `outline=none` mesmo após regra CSS explícita; portanto o foco visual **não está homologado** nesta execução. Não se conclui conformidade de acessibilidade, zoom ou todos os estados visuais com base nesses resultados. Contraste numérico registrado na RF-02D (8,32:1 a 13,96:1 para pares selecionados) não substitui auditoria completa.

## Fontes e atribuições — revisão pública

- [Lista oficial TMDB](https://developer.themoviedb.org/reference/watch-providers-movie-list): origem dos IDs; consultar com região, sem inferir modalidades.
- [Watch providers de filme](https://developer.themoviedb.org/reference/movie-watch-providers): dados de disponibilidade fornecidos pela JustWatch, com atribuição obrigatória; não oferece todos os deep links. A futura apresentação deve utilizar o link fornecido conforme a documentação.
- [FAQ TMDB](https://developer.themoviedb.org/docs/faq): exige logo aprovado e crédito sem sugerir endosso; uso não comercial condicionado à atribuição; uso comercial requer contato/licença. O crédito conhecido é “This product uses the TMDB API but is not endorsed or certified by TMDB.” O rodapé existente não constitui certificação de conformidade de marca.
- [Documentação oficial JustWatch Content Partner API](https://apis.justwatch.com/docs/api/): descreve links de marca junto à integração, links regionais por título e identificação acessível/visual JustWatch, além de requisitos próprios de contrato e autenticação. Essa API direta não é a integração TMDB; seus requisitos contratuais não foram automaticamente transpostos. Confirmar as obrigações específicas aplicáveis à parceria TMDB antes da ativação.
- [Termos TMDB](https://www.themoviedb.org/api-terms-of-use) e [logos/atribuição](https://www.themoviedb.org/about/logos-attribution): acesso automatizado bloqueado por robots nesta investigação. Texto integral e aprovação do uso dos logotipos permanecem pendentes. Não foi comprovada revisão integral de contrato JustWatch aplicável ao nosso caso.

Nenhuma nova marca/imagem foi adicionada. Integração externa continua imprópria para ativação até revisão integral dos termos, atribuições e configuração operacional. Não há disponibilidade real ou simulada apresentada ao público.

## Validação e preservação

Comandos: `.venv/bin/python -B -m unittest discover -s movielens_prototipo -p testes.py`; `node --test --test-isolation=none movielens_prototipo/testes_autocomplete.cjs movielens_prototipo/testes_streaming.cjs`; `.venv/bin/python -B verificacoes/rf02e1_20261030/validar_visual.py --pasta visual_depois`; `git diff --check`.

Antes: 247 testes Python, 246 aprovados e um omitido. Depois: 254, 253 aprovados e um omitido; JavaScript 24/24 aprovados. O omitido depende de socket local bloqueado pelo ambiente; contratos HTTP também são exercitados em memória. Sete testes novos cobrem catálogo vazio, evidência sintética, pendências, IDs/região/hash inválidos, duplicatas, arquivos ausentes, escape de diretório e envelope com campos indevidos; incluem salvamento/restauração sintéticos e rejeição de desconhecidos. Suites anteriores verificam múltiplas escolhas, modos, perfil e impossibilidade de ativação pelo navegador.

Arquivos existentes alterados nesta atividade: `streaming_web.py`, `index.html`, `static/streaming.js`, `testes.py`, `testes_streaming.cjs`, `STREAMING_WEB.md`. Novos módulos/configuração/testes citados acima e este documento. Evidências novas ficam separadas em `verificacoes/rf02e1_20261030/`; não confundir o diff total do repositório, que já continha trabalho aprovado, com estas alterações.

Logs, capturas antes/depois, métricas de navegador e hashes estão na pasta da execução. `integridade.json` compara SHA-256 com snapshot anterior, incluindo datasets, resultados, experimentos, documentos anteriores, algoritmo e notebook. Nenhum módulo incorporado ao notebook foi alterado nesta atividade; não houve necessidade de sincronizar nem executar o notebook.

## Bloqueios para RF-02E2

Obter evidência regional oficial mediante autorização futura, revisar e promover catálogo real; concluir termos/logotipos/créditos; verificar foco por teclado em navegador interativo e acessibilidade; aprovar orçamento, concorrência e configuração operacional do transporte. Catálogo ainda não homologado e UX homologada apenas parcialmente. Nenhuma RF-02E2 ou Etapa 5 foi iniciada. Desenvolvimento interrompido para revisão.
