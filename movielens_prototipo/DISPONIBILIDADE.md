> Registro histórico: streaming foi definitivamente descontinuado em 11/11/2026. Os módulos e rotas aqui descritos não fazem parte do produto atual. Consulte [encerramento de escopo](../docs/ENCERRAMENTO_ESCOPO_CINEMATCH.md).

# RF-02A — Contrato interno de disponibilidade

O contrato RF-02A está em `disponibilidade.py`, sem transporte HTTP padrão, leitura de token, endpoints ou dependência do recomendador. A RF-02B acrescenta o cliente isolado [TRANSPORTE_TMDB.md](TRANSPORTE_TMDB.md), desativado por padrão. A RF-02C prepara [FILTRO_STREAMING.md](FILTRO_STREAMING.md) somente em fluxo interno. Não há seleção de streaming na página nem filtragem pública; RF-02D e Etapa 5 permanecem pausadas.

## Fonte e investigação oficial

Documentação consultada em 29/10/2026, sem chamar a API autenticada ou consultar disponibilidade real:

- [Watch providers por filme](https://developer.themoviedb.org/reference/movie-watch-providers): rota `/3/movie/{movie_id}/watch/providers`, dados por país fornecidos pela parceria com JustWatch. A resposta não promete links diretos dos serviços; oferece um endereço TMDB de encaminhamento. Atribuição à JustWatch é obrigatória para utilizar esses dados.
- [Catálogo de provedores de filmes](https://developer.themoviedb.org/reference/watch-providers-movie-list): `/3/watch/providers/movie`, com `watch_region` para restringir país e `language` para apresentação. `provider_id` identifica o provedor; nomes são apresentação, não chave de associação.
- [Regiões atendidas](https://developer.themoviedb.org/reference/watch-providers-available-regions): `/3/watch/providers/regions`. O padrão planejado é BR; a lista real de regiões e serviços não foi consultada.
- [Modalidades documentadas](https://developer.themoviedb.org/reference/discover-movie): `flatrate`, `rent`, `buy`, `free` e `ads`, respectivamente assinatura, aluguel, compra, gratuidade e anúncios. A descoberta por provedores também usa região; não foi implementada nesta atividade.
- [OpenAPI oficial](https://developer.themoviedb.org/openapi/tmdb-api.json): referência pública para formato e autenticação por cabeçalho. A consulta ao documento estático não é uma chamada de disponibilidade.

Não inferir disponibilidade de pôster, catálogo de provedores ou filmes encontrados em Discover. Uma plataforma listar filmes no país não comprova que um título específico esteja incluído na assinatura do visitante.

## Representação implementada

Objetos imutáveis (`dataclass(frozen=True)`) e enums, sem hierarquia de plugins:

| Elemento | Significado |
|---|---|
| `Disponibilidade.conteudo` | `IdentidadeConteudo(fonte, tipo, id_original)` existente; impede colisões numéricas entre fontes/tipos |
| `tmdb_id` | Inteiro positivo do mapeamento explícito, ou None sem vínculo utilizável |
| `regiao` | Código de duas letras maiúsculas; padrão BR no serviço/preferências |
| `ofertas` | Tupla de `Oferta(provedor_id, modalidade, nome)`; modalidades do mesmo provedor são separadas |
| `consultado_em` / `expira_em` | Horários com fuso explícito; validade não equivale a garantia em tempo real |
| `estado` | CONFIRMADA, DESCONHECIDA ou ERRO |
| `fonte` | `tmdb.watch_providers/justwatch` para esta normalização |
| `motivo` | Código de diagnóstico sem mensagem arbitrária da rede/credenciais |
| `link_tmdb` | Link HTTPS do host TMDB e do ID de filme correspondente; opcional |
| `ausencia_confirmada` / `evidencia_ausencia` | Reserva explícita para uma fonte futura que realmente comprove ausência; a normalização TMDB nunca produz essa confirmação |

CONFIRMADA significa que a fonte reportou ofertas naquela região/data, não que a conta, o plano ou o catálogo do serviço tenham sido verificados diretamente. Resposta válida vazia, região ausente e nenhum mapeamento são DESCONHECIDA. Falha de transporte ou resposta incompatível são ERRO e não carregam ofertas. Uma região presente com formato nulo é inválida, não ausência válida.

A API consultada não fornece declaração confiável de ausência global de disponibilidade. Portanto não se converte HTTP 404, lista vazia, ausência de plataforma ou falha em “indisponível confirmado”. O contrato impede marcar ausência confirmada com a origem TMDB; outra fonte futura precisaria de evidência explícita, escopo e validade. Nenhuma segunda fonte foi implementada. A avaliação de assinatura distingue INCLUIDO_ASSINATURA, NAO_CONFIRMADO, DESCONHECIDA, ERRO, SEM_SELECAO e essa ausência explícita reservada.

## Identificadores e mapeamento

`links_movielens()` reutiliza `posteres.carregar_links()`, que lê `links.csv` local, ignora vínculos ausentes e remove IDs MovieLens conflitantes. Converte as chaves para identidades completas. Não procura por título, ano ou gênero e não modifica o CSV. `Disponibilidades` aceita apenas chaves de identidade completa e IDs TMDB inteiros positivos; o ID da resposta deve coincidir com o solicitado.

Essa validação comprova consistência estrutural e de IDs, não revisão humana de cada vínculo histórico do dataset. O vínculo externo confiável continua sendo o CSV aprovado. Sem ele, não há consulta por aproximação de título. Séries só permanecem representáveis pelo contrato existente: são devolvidas como tipo não suportado, sem consulta nem reaproveitamento de resposta de filme.

`catalogo_provedores()` normaliza pares ID/nome da lista sintética, sem juntar IDs diferentes com nomes iguais. Conflitos de nome no mesmo ID são rejeitados. A resposta de catálogo não ecoa necessariamente o país; o futuro transporte deverá preservar a região da requisição ao armazená-la. A função atual não confirma que um código sintaticamente válido seja atendido pelo TMDB.

## Preferências preparadas, sem integração de produto

`PreferenciasStreaming` tem conjunto imutável de IDs, região BR, `Modo.RESTRITO` padrão e ativação explicitamente falsa por padrão; `Modo.FLEXIVEL` é representável. Na RF-02C, sua definição canônica foi isolada em `preferencias_streaming.py`, reexportada aqui para manter os imports anteriores. Alterar preferências significa produzir outro objeto. A sessão começa com None (sem configuração), e seu setter interno valida o catálogo da região sem tocar em referências ou histórico. O módulo de disponibilidade não importa `conversa.py` nem escreve estado de visitante.

`compatibilidade()` é uma classificação pura da evidência, não alteração no ranking. Só considera incluído na assinatura se houver oferta CONFIRMADA, vigente, da mesma região, modalidade `flatrate` e ID selecionado. Múltiplos IDs funcionam como alternativa: basta uma assinatura selecionada compatível. Aluguel, compra, gratuito e anúncios não viram assinatura automaticamente. Sem seleção retorna SEM_SELECAO, não “todos os serviços”.

O modo flexível não relaxa a classificação por si só. Uma política futura precisará de escolha explícita e rótulos claros para candidatos fora de assinatura ou sem confirmação; não poderá apresentar essas opções como acesso incluído. O contrato não altera a regra de uma a cinco referências, não completa listas com ranking geral e não exige reiniciar sessão.

Serviços, canais e pacotes podem ter IDs distintos. `flatrate` é a modalidade reportada pela fonte; não valida assinatura ativa, plano individual, complemento de canal, publicidade de um plano ou acesso efetivo do visitante. Não guardar credenciais de serviços do usuário.

## Cache e segurança implementados

`Disponibilidades` exige `consultar(tmdb_id, regiao)` injetado. Não constrói requisição HTTP, lê `.env`, recebe token ou chama TMDB automaticamente. `posteres.py` não foi alterado; só a função local de links é reutilizada.

Cache LRU somente em memória, máximo 512 entradas, com chave `(identidade completa, tmdb_id, região, origem)`. TTLs escolhidos para o protótipo, não impostos pelo TMDB: 24h para ofertas reportadas, 15 minutos para desconhecido e 60 segundos para erro. Clock injetável permite testes. Em expiração exata a consulta é refeita; informação vencida não é servida como confirmação, nem se conserva sucesso antigo após nova falha. Mudança de seleção usa a mesma evidência em cache, sem nova consulta.

Mensagens arbitrárias de exceções não são copiadas para resultados, para evitar vazamento de tokens/URLs. Links são limitados a HTTPS/TMDB/ID correspondente; não há scraping, busca de título ou acesso ao endereço retornado. Ofertas inválidas/parciais falham fechadas, sem aproveitar uma parte positiva de uma resposta incompatível.

O contrato não tem cache em disco ou sincronização própria. Na RF-02B, a fachada serializa consultas por instância, reutiliza as funções LRU deste módulo e acrescenta limites de taxa/tamanho no transporte. Não há sincronização entre processos nem orçamento conjunto com pôsteres. Os 512 registros limitam entradas, não são medição de memória nem limite de bytes de resposta.

## Limites, custo e condições de uso verificados

A documentação de [limitação de taxa](https://developer.themoviedb.org/docs/rate-limiting) informa que o limite legado foi desativado, mas há proteção variável na faixa de 40 requisições/s e deve-se respeitar HTTP 429. Isso não é cota garantida nem meta de consumo. O futuro transporte deve ter orçamento próprio inferior, timeout, tratamento de Retry-After e pausa, considerando conjuntamente chamadas de pôsteres e disponibilidade.

A [FAQ oficial](https://developer.themoviedb.org/docs/faq) informa acesso sem cobrança para uso não comercial com atribuição; uso comercial exige contato/licenciamento. Não há SLA. Ela exige logo aprovado, identificação nos créditos e o aviso: “This product uses the TMDB API but is not endorsed or certified by TMDB.” O crédito TMDB já existe em `index.html`; não foi alterado. O crédito JustWatch terá de ser acrescentado ao exibir suas informações, conforme a documentação de watch providers. Não se deduziu exigência de um logo JustWatch específico a partir dessa página.

Os [termos completos](https://www.themoviedb.org/api-terms-of-use) não puderam ser obtidos pela ferramenta (bloqueio robots). Logo, a verificação é limitada às páginas públicas acima; não é aprovação jurídica/licença completa. Não foi confirmada uma regra contratual específica de retenção/cache por essas páginas. Revalidar termos vigentes, atribuições e uso de logos antes de ativação pública; os TTLs atuais são decisão técnica, não interpretação de permissão contratual de armazenamento.

## Integração de produto — pendente para RF-02D

1. Confirmar termos/atribuições antes de habilitar o transporte já isolado no servidor, sem devolver token ao navegador ou registrá-lo em logs. Preservar mapeamento local; listar provedores para BR pelos IDs, com rótulos distinguindo canais/pacotes. O catálogo já possui cache separado; não inferir ofertas por título a partir dele.
2. Incluir seleção múltipla e modo explícito na sessão, sem apagar referências, histórico, rejeições ou preferências de gêneros. Padrão restrito a assinatura reportada; seleção vazia pede orientação, sem selecionar tudo. A condição de 1–5 referências é validada antes de consultar disponibilidade.
3. Preparar uma forma revisável de percorrer candidatos na ordem atual ANTES de truncar o Top 10, preservando integralmente score e desempates com testes de caracterização. Filtrar só as dez sugestões prontas pode esconder candidatos válidos mais abaixo; não implementar isso como atalho. A mudança de acesso ao conjunto ordenado dependerá de autorização específica, não ocorreu aqui.
4. Percorrer candidatos priorizando cache válido, em pequenos lotes; parar ao obter até dez confirmações ou esgotar candidatos/orçamento. Proposta inicial para revisão: no máximo vinte consultas novas por interação, duas concorrentes, timeout de três segundos, cinco requisições/s compartilhadas e deadline de cinco segundos. São limites de projeto futuros, não métricas medidas nem garantia de dez resultados. Deduplicar consultas concorrentes e respeitar Retry-After, sem retries ilimitados.
5. No modo restrito, retornar menos de dez se não houver confirmações suficientes no universo consultado. Diferenciar candidatos esgotados de orçamento esgotado/fonte indisponível: não alegar que não existem outros títulos quando a busca foi limitada. Nunca relaxar assinaturas ou modalidades automaticamente.
6. No flexível, mediante escolha do usuário, permitir exibir alternativas com modalidade e estado explícitos, sem afirmar inclusão em assinatura quando desconhecida. Definir essa política em revisão própria e testar sessão, falhas, limites, atribuições e UX móvel/teclado. Não usar novos dados de disponibilidade para ajustar pesos ou experimentos acadêmicos já aprovados.

Custo analítico: uma chamada por filme sem cache; o endpoint retorna informação regional, sem consulta separada por provedor. Vinte filmes frios exigiriam até vinte chamadas, não vinte × quantidade de assinaturas. Inspecionar todo o catálogo por interação seria inadequado; cache reduz consultas repetidas a zero enquanto válido. Nenhuma latência, custo faturado, disponibilidade real ou throughput externo foi medido nesta etapa.
