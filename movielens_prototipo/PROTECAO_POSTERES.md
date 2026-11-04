# RF-02E2-PRE-POSTER — Transporte e cache de pôsteres

Atividade iniciada em 30/10/2026 e retomada em 03/11/2026. Não ativa streaming nem autoriza consultas reais. Implementação verificada somente com transportes sintéticos. O módulo consulta **metadados JSON**, não baixa o arquivo de imagem: entrega URLs do CDN ao navegador.

## Contratos preservados

`Posteres.obter(movie_id)` mantém `poster_url`, `thumbnail_url`, `tmdbId`. Vínculo/credencial ausente, filme sem imagem ou falha na obtenção de metadados continuam usando `/static/poster-placeholder.svg`. O carregamento de vínculos continua sendo por identificador, sem busca por título.

Prioridade de pôster: português, inglês, neutro, demais idiomas; caminho principal como alternativa. Tamanho `w342` quando disponível, senão `w500`; miniatura `w185` quando disponível, senão tamanho principal. Falha de configuração preserva o fallback `w500`. As URLs legítimas diretas do CDN e seus formatos de caminho permanecem iguais.

TTL: sete dias para metadados normais, inclusive ausência de imagem numa resposta 200, e configuração; ausência por HTTP 404 de filme usa 24 horas. Falhas não são persistidas como ausência. Cooldown de 60 s, 401/403 de 600 s e Retry-After com mínimo de 60 s foram mantidos. Suspensões concorrentes não encurtam uma pausa maior já registrada.

A persistência continua opcional, no mesmo arquivo JSON, esquema `versao:1`, mapa `entradas`, chaves `filme:TMDB_ID` e `config`, com até 2000 entradas na gravação. Sem arquivo configurado, o cache continua somente em memória; não se introduziu banco ou limite novo de retenção nesse modo. Entradas válidas carregadas do arquivo antigo não causam regravação em cache hit.

## Auditoria e concorrência

Antes, uma trava da instância cobria leitura, rede e gravação, bloqueando cache hits enquanto outro filme aguardava HTTP. Agora:

- `ConsultasPorChave`, já existente em `operacao_externa.py`, coordena produção por chave. Consultas equivalentes na mesma instância compartilham um produtor; `config` também é deduplicada entre filmes.
- A trava de memória cobre somente consulta/publicação de entradas. Nenhuma operação HTTP ou gravação em disco ocorre com ela adquirida.
- Filmes diferentes podem progredir respeitando o orçamento compartilhado; um hit válido não espera uma consulta externa ou a gravação de outro filme.
- Uma trava curta separada protege reserva do intervalo de 0,2 s e estado de cooldown. A espera e a rede ocorrem fora dela.
- O controlador compartilhado por credencial/processo continua limitando vagas, quota e suspensão após 429. Cache hit não consome admissão. Eventos e vagas são liberados em falha. Não há nova thread de atualização ou repetição automática.

A deduplicação é por instância de serviço, como a instância compartilhada pelo Handler. Instâncias independentes não compartilham produtores HTTP. Escritores do mesmo caminho são coordenados dentro do mesmo processo; não há promessa de coordenação distribuída ou entre processos diferentes.

## Gravação segura

A memória registra somente entradas modificadas. O escritor adquire a trava do arquivo, obtém um snapshot breve sob a trava de memória e libera esta última antes do I/O. Lê o estado persistido mais recente e mescla apenas as modificações, preservando entradas de outra instância do mesmo processo. Publicações novas em memória enquanto o arquivo é escrito têm precedência ao reconciliar o estado local.

A gravação utiliza temporário exclusivo, criado no mesmo diretório, com permissão restrita do mecanismo padrão de arquivos temporários. Depois de escrever: flush, fsync do arquivo, fechamento e substituição atômica do destino. Um erro antes da substituição mantém o arquivo anterior. O temporário criado por aquela tentativa é removido quando possível; arquivos temporários antigos/desconhecidos não são apagados nem carregados como cache válido.

A gravação continua síncrona e de melhor esforço: falha de disco não impede usar metadados já obtidos na memória. Não há retry em segundo plano. Uma gravação posterior pode publicar as alterações ainda pendentes. A política de formato/TTL/limite foi preservada; mudaram a coordenação e a publicação segura.

O replace atômico pressupõe as garantias do sistema de arquivos local. O arquivo é sincronizado, mas não se promete durabilidade integral do diretório após queda de energia. Encerramento abrupto pode deixar um temporário órfão, ignorado na leitura. Escritores em processos diferentes ainda podem perder atualizações entre si; esse modo de implantação exige revisão própria.

## Transporte protegido

- Destino fixo HTTPS `api.themoviedb.org`, somente as rotas canônicas de filme/configuração e parâmetros produzidos internamente. IDs inválidos do mapeamento não geram requisições.
- Opener padrão sem proxies implícitos e com redirecionamentos bloqueados antes de reenviar Authorization. A URL final também deve coincidir exatamente com a solicitada. Transportes injetáveis são de confiança e só são usados nos testes/configurações autorizadas.
- Credencial somente em cabeçalho; não é colocada em URL, arquivo, sessão ou saída pública. Tokens malformados são recusados; eco da credencial no JSON, inclusive escapado, é rejeitado.
- Status 200 e MIME `application/json` obrigatórios, com parâmetros de charset aceitos. Corpo UTF-8 e raiz JSON objeto; ID da resposta e configuração do CDN são conferidos antes de aproveitar dados.
- Limite padrão de 1 MiB configurável em `max_bytes`. Content-Length acima do limite é recusado antes da leitura. Sem esse cabeçalho, lê em blocos de até 64 KiB e interrompe ao receber o byte excedente; nunca usa `read()` ilimitado. Comprimento incoerente, interrupção, JSON inválido ou erro do decodificador não são publicados no cache.
- Timeout padrão de três segundos, configurável; quando há prazo operacional no contexto, recebe o restante menor. Leituras cooperativas verificam o contexto entre blocos. Não há garantia de prazo total rígido ou cancelamento imediato de I/O já iniciado.
- Exceções remotas são convertidas em códigos sanitizados; respostas e HTTPError são fechados, e a admissão externa é liberada inclusive nas falhas. Retry-After é aplicado ao orçamento compartilhado antes de liberar a operação que recebeu o 429.

Bloquear redirecionamentos não altera as URLs diretas geradas do CDN. Não se buscou compatibilidade com um destino arbitrário ou redirecionamento novo: uma mudança oficial de endpoint precisará de revisão explícita. Respostas legítimas maiores que 1 MiB também serão recusadas; esse teto conservador poderá ser revisto com evidência e autorização, sem mexer no recomendador.

A validação de MIME refere-se ao JSON efetivamente recebido pelo servidor, não a bytes JPEG/PNG que ele não baixa. Não se certifica o conteúdo binário das imagens. HTTPS depende da validação TLS e do DNS do sistema; não há isolamento de rede independente do sistema operacional.

## Validação e preservação

Os 14 testes antigos mantêm seus oráculos. A fixture HTTP foi atualizada para fornecer status, URL final e MIME, atributos agora obrigatórios; não se relaxaram as verificações de idioma, URLs, TTLs ou placeholders. `testes_protecao_posteres.py` acrescenta 22 testes com subcasos para concorrência, escrita, segurança e recuperação; o agregador `testes.py` inclui essa suíte.

Resultados, comandos, medições simuladas, comparação de hashes e limitações estão em relatório local `verificacoes/rf02e2_pre_poster_20261030/RELATORIO.md` (evidência bruta não distribuída; veja a [preparação de publicação](../docs/GIT02_RELATORIO.md)). O nome da pasta conserva a data de início; as evidências finais indicam a retomada em novembro.

Esta atividade resolve a limitação de serialização de cache/rede dos pôsteres registrada na RF-02E2-PRE, dentro do processo atual. Permanecem bloqueados a coleta/homologação real de provedores, revisão integral dos termos, aprovação de créditos/marcas e autorização operacional da disponibilidade. As demais pendências de implantação, prazo total, publicação versionada e expiração de sessão não foram ampliadas nesta correção. RF-02E2 e Etapa 5 continuam pausadas.
