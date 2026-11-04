# RF-02B — Transporte seguro de disponibilidade

Implementação isolada em `tmdb_disponibilidade.py`, sem importação por `app.py`, sessão, interface ou recomendador. Construir o cliente não consulta a rede. Está desativado por padrão, inclusive se existir token no ambiente. A RF-02C acrescentou consulta controlada por orçamento em fluxo interno, sem ativação pública; RF-02D e Etapa 5 permanecem pausadas.

## Arquitetura

- `TransporteTMDB`: valida parâmetros e IDs permitidos, constrói GET HTTPS somente nos dois recursos fixos, verifica status/tamanho/formato e sanitiza falhas. Não interpreta oferta ou escolhe filme.
- `ClienteDisponibilidadeTMDB`: fachada de servidor; recebe o mapa de identidades já validado, delega interpretação para `Disponibilidades` e `catalogo_provedores` da RF-02A e devolve objetos internos. Uma trava por instância cobre leitura de cache, eventual consulta e escrita.
- `Disponibilidades`: continua responsável por identidade, região, modalidades, validade e cache de ofertas. A alteração nesta etapa extraiu as operações LRU para `ler_cache`/`gravar_cache` e acrescentou `FalhaConsulta`, com códigos fixos sanitizados; os contratos anteriores continuam passando nos testes.
- `CatalogoRegional`: resultado imutável com região consultada, idioma de apresentação, horário/validade, estado, pares de provider_id/nome, motivo e origem. Reutiliza as mesmas operações de cache e TTLs, com armazenamento separado por finalidade.

Não há plugins, endpoint novo, novo algoritmo, scraping ou correspondência por título. Use `links_movielens()` para ler o CSV já existente; a fachada deriva uma lista permitida de TMDB IDs de identidades FILME. Mesmo um inteiro positivo desconhecido nesse mapa é rejeitado pelo transporte. Tipos futuros SERIE não fazem requisição.

## Credencial e habilitação

O transporte lê exclusivamente `TMDB_READ_ACCESS_TOKEN` do ambiente ao construir a instância. Não recebe token por parâmetro público, não lê `.env`, não o escreve em cache/disco e não registra cabeçalhos. Uma nova instância é necessária após mudança operacional da credencial. Credencial ausente ou com formato inseguro produz motivo sanitizado, sem revelar o valor.

São exigidos AMBOS os argumentos explícitos `habilitado=True` e `termos_aprovados=True` para permitir transporte. O segundo é uma declaração do chamador, não verificação jurídica automática; usá-lo em fixture sintética não aprova termos de produção. Nenhum ponto da aplicação foi alterado para ativá-los. Não considerar pronto para uso externo enquanto termos integrais e configuração não forem aprovados.

A credencial só é adicionada ao cabeçalho Authorization, nunca à URL ou ao corpo. Resultados e exceções públicas usam códigos de uma lista fixa; não conservam erro remoto ou traceback encadeado. Respostas que ecoam a credencial, inclusive por escapes JSON, são rejeitadas. Não serializar o objeto transporte ou seus atributos privados; a interface futura deverá expor apenas o contrato sanitizado. Código Python hostil que inspecione memória não está no escopo dessa proteção.

O opener padrão não utiliza proxy implícito do ambiente e bloqueia redirecionamentos antes de reenviar a autorização. Além disso, o endereço final da resposta deve coincidir com o solicitado. TLS usa a verificação padrão do Python. Adaptar proxy corporativo, se necessário, exigirá revisão futura; não há desativação de certificado.

## Requisições fixas

| Método interno | Requisição sintética, sem credencial na URL |
|---|---|
| `obter(conteudo_movielens(1))`, mapa 1→100 | `GET https://api.themoviedb.org/3/movie/100/watch/providers` |
| `provedores()` | `GET https://api.themoviedb.org/3/watch/providers/movie?watch_region=BR&language=pt-BR` |
| `provedores('BR','en-US')` | Mesmo país BR, nomes solicitados em en-US |

Os IDs 1, 100, 10 e nomes abaixo são sintéticos, não afirmações de catálogo real. O endpoint de filme devolve países no corpo; BR é selecionado pelo interpretador, não enviado como idioma ou query não documentada. Regiões têm sintaxe de duas letras maiúsculas e idioma usa `pt-BR`/`en-US`. A aceitação sintática não confirma suporte real à região. Não há busca textual ou rota de séries.

Exemplo de corpo sintético recebido:

```json
{"id":100,"results":{"BR":{"flatrate":[{"provider_id":10,"provider_name":"Serviço sintético"}],"rent":[{"provider_id":20,"provider_name":"Aluguel sintético"}]}}}
```

Projeção dos campos internos interpretados (não é endpoint/serializador novo):

```json
{"conteudo":{"fonte":"movielens","tipo":"FILME","id_original":"1"},"tmdb_id":100,"regiao":"BR","estado":"confirmada","ofertas":[{"provedor_id":10,"modalidade":"flatrate"},{"provedor_id":20,"modalidade":"rent"}]}
```

O objeto real também tem datas, validade, origem e motivo. `rent`, `buy`, `free` e `ads` nunca são convertidos em `flatrate`. Presença de provedor não verifica plano/pacote ou assinatura efetiva do visitante.

## Respostas e falhas

| Situação | Resultado/política |
|---|---|
| 200, ID e estrutura válidos, ofertas no país | CONFIRMADA, modalidades reportadas |
| 200 válido sem país ou ofertas | DESCONHECIDA; não prova ausência global |
| Filme sem vínculo / série | DESCONHECIDA, sem HTTP |
| Lista regional de provedores vazia | DESCONHECIDA com lista vazia |
| ID, JSON, MIME ou estrutura inválidos/incompletos | ERRO / RESPOSTA_INVALIDA |
| Corpo acima do limite | ERRO / RESPOSTA_EXCESSIVA |
| 401 / 403 | ERRO com código distinto; pausa do transporte 600s |
| 404 | ERRO / HTTP_404; cache de erro por chave, sem declarar indisponível |
| 429 | ERRO / HTTP_429; respeita Retry-After em segundos ou data HTTP; fallback 60s se ausente/inválido |
| 5xx | ERRO / HTTP_5XX; pausa 60s |
| Timeout / conexão | ERRO / TIMEOUT ou CONEXAO; pausa 60s |
| Consulta durante pausa | ERRO / CONSULTA_SUSPENSA, sem HTTP |
| Redirecionamento | ERRO / REDIRECIONAMENTO_BLOQUEADO |
| Desativado / sem credencial | ERRO específico, sem HTTP |

Não há repetição automática da requisição. A pausa afeta o catálogo e a disponibilidade na mesma instância de transporte. Cache de erro pode adiar uma nova tentativa além de um Retry-After curto; nunca antecipa tentativa enquanto durar a pausa válida. 404 não suspende os demais filmes. Não se modifica cache/sucesso vencido para simular confirmação após falha.

Timeout padrão 3 segundos, configurável, positivo/finito. É timeout da operação HTTP/socket, não deadline absoluto de uma interação inteira. Tamanho máximo padrão 1 MiB, configurável; leitura limitada, Content-Length conferido quando presente e Content-Type JSON exigido. Essa restrição pode rejeitar respostas legítimas maiores, que terão de ser avaliadas sem relaxar automaticamente limites.

## Cache e concorrência

| Finalidade | Chave | Limite |
|---|---|---:|
| Disponibilidade | identidade completa, TMDB ID, região, origem | 512 entradas |
| Catálogo de filmes | finalidade, região, idioma, origem | 32 entradas |

Ambos usam as mesmas operações LRU extraídas da RF-02A. TTLs preservados: 24h para dados reportados, 15min para ausência válida de informação e 60s para erros. São escolhas técnicas, não regras de licença verificadas. Somente memória; tokens e dados de sessão não são entradas de cache. Não se reaproveita item vencido como confirmado.

A trava da fachada serializa chamadas por instância, inclusive chaves distintas, e faz com que chamadas simultâneas da mesma chave recebam a mesma entrada após uma única consulta. É simples e evita corrupção do LRU; não maximiza paralelismo. Foram testadas oito consultas simultâneas de um filme e quatro do catálogo. Instâncias/processos separados não compartilham cache, pausa ou trava.

No transporte há espaçamento mínimo de 0,2s entre inícios, no máximo cinco requisições/s por instância, sem contar pausas maiores. A espera de rate limiting pode se somar à do lock e ao timeout. A RF-02C acrescentou `obter_controlado()`: sob a mesma trava, devolve cache/local sem custo ou não verificado se não houver permissão de consulta. Retorna também o número de chamadas efetivamente iniciadas no opener. O componente interno [FILTRO_STREAMING.md](FILTRO_STREAMING.md) aplica orçamento; o transporte sozinho não o impõe. Não há orçamento público ou limitador compartilhado com pôsteres, nem filtro ligado à aplicação.

## Custos e limitações

Acerto de cache não faz HTTP; uma consulta fria de filme requer uma requisição, independentemente de quantas assinaturas forem escolhidas. País diferente tem chave distinta e pode refazer a consulta, embora a API de filme traga múltiplos países: esta etapa preserva o isolamento em vez de acrescentar outro cache de envelope global. Uma consulta de catálogo é separada por região/idioma. Limites de quantidade de cache não limitam exatamente memória dos objetos normalizados; não foi medido desempenho real ou faturamento.

As duas instâncias de cache e o limitador locais não bastam para múltiplos workers. Ainda será necessário orçamento/deadline do fluxo de candidatos, deduplicação compartilhada se a arquitetura exigir, e limite conjunto com chamadas de pôsteres. Evitar consultar todo o catálogo por visitante; não preencher lista por popularidade nem relaxar plataformas na falta de confirmação. Nenhuma dessas decisões de produto foi implementada aqui.

## Documentação, atribuição e pendências

Referências oficiais consultadas em 29/10/2026, apenas páginas de documentação, sem chamada autenticada:

- [Watch providers por filme](https://developer.themoviedb.org/reference/movie-watch-providers): origem JustWatch e atribuição obrigatória ao utilizar/exibir esses dados; link de encaminhamento TMDB, não links diretos completos dos serviços.
- [Provedores de filmes](https://developer.themoviedb.org/reference/watch-providers-movie-list): parâmetros watch_region e language.
- [Rate limiting](https://developer.themoviedb.org/docs/rate-limiting): proteção variável, não cota garantida; respeito a 429. Cinco/s é escolha conservadora local, não requisito oficial.
- [FAQ](https://developer.themoviedb.org/docs/faq): condições públicas de uso não comercial/comercial e atribuição TMDB. A aplicação já tem crédito TMDB, mas não se declara conferência integral de licença/branding. O crédito JustWatch deverá existir antes de exibir a disponibilidade.

**A verificação integral dos termos de uso continua pendente.** Não foram homologados retenção/cache, produção, credencial real ou disponibilidade atual em BR. A implementação não está pronta para uso externo e permanece desativada. Não há aprovação jurídica implícita no sucesso dos testes.

Para RF-02D, mediante autorização: concluir termos/atribuições/configuração; planejar eventual teste real autorizado; definir orçamento/deadline compartilhado e a integração HTTP; expor preferências na página sem reiniciar sessão; preservar referências e pontuação; disponibilizar o conjunto ordenado antes do Top 10; expor somente resultados sanitizados e tratar listas menores/falhas com texto honesto. Não implementar isso automaticamente.
