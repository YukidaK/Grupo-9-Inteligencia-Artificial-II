# RF-02E2-PRE — Preparação sem ativação

A coleta autenticada, a promoção do catálogo e o uso externo não estão autorizados por este documento. RF-02E2 e Etapa 5 permanecem pausadas. Procedimento 1, esquema de catálogo local 1. Nenhuma credencial deve integrar arquivos, comandos de exemplo, relatórios ou logs.

## A — Coleta oficial e homologação humana

O catálogo público `catalogo_streaming_br.json` permanece vazio, com evidência regional pendente. A [referência oficial](https://developer.themoviedb.org/reference/watch-providers-movie-list) documenta `GET /3/watch/providers/movie`, `watch_region=BR` e `language=pt-BR`. Documentação e exemplos não são uma resposta regional atual. Nenhum ID real foi coletado ou homologado nesta atividade.

`coletar_catalogo.py` é um comando independente, sem importação pela aplicação e sem rede na inicialização. Sem `--executar`, apenas informa o bloqueio. Antes de construir `TransporteTMDB` ou ler a credencial, exige arquivo de aprovação com exatamente:

- `termos_aprovados` e `autorizacao_operacional`: booleanos verdadeiros somente após decisão humana real;
- `responsavel`: identificação da revisão;
- `aprovado_em`: data ISO com fuso, não futura;
- `escopo`: lista contendo somente `catalogo_filmes_BR`;
- `documentos`: referências `{arquivo,sha256}` a documentos locais da revisão, cujo hash é conferido.

Isso verifica existência, escopo e integridade de um registro; não autentica uma assinatura humana nem comprova que um contrato foi interpretado corretamente. O arquivo-modelo na pasta de evidências mantém aprovações falsas. Não há aprovação efetiva documentada para coletar nesta execução.

Procedimento posterior, condicionado à autorização:

1. Obter e revisar os termos aplicáveis integralmente, registrar documento/fonte/data/hash e obter aprovação humana para esta única coleta regional. Resolver política de armazenamento antes de guardar a resposta.
2. Configurar `TMDB_READ_ACCESS_TOKEN` exclusivamente no ambiente do servidor; nunca passá-lo na URL, argumento de shell ou arquivo de evidência.
3. Executar o comando abaixo com um diretório que ainda não exista. **O comando não foi executado com autorização real nesta atividade.**

```sh
.venv/bin/python -B movielens_prototipo/coletar_catalogo.py --executar --aprovacoes CAMINHO_DA_APROVACAO --saida DIRETORIO_NOVO
```

4. Preservar `evidencia.json`: corpo público JSON reserializado com URL fixa, região BR, tipo FILME e instante UTC. O hash identifica essa representação JSON; não é hash dos bytes HTTP originais ou de cabeçalhos. Não armazena Authorization.
5. Conferir `candidatos.json` e `manifesto.json`: versão do procedimento, fonte, horário, candidatos, zero homologados, hashes dos arquivos e do registro de aprovação. A coleta rejeita estrutura inválida, IDs não positivos, booleanos, nomes inválidos, duplicatas inclusive idênticas e conflitos. Não associa nomes semelhantes.
6. Revisar candidatos manualmente, incluindo procedência/autenticidade e validade regional. Todas as entradas geradas ficam `pendente`; `catalogo_streaming.carregar_catalogo()` não as expõe.
7. Somente em atividade posterior aprovada, promover entradas selecionadas, conservando evidência imutável e caminhos relativos aceitos pelo validador. Nunca sobrescrever o histórico de coletas. Não há promoção automática ou alteração do catálogo público pelo comando.

Falhas são sanitizadas. Diretório existente é recusado. Uma falha de disco após criar a saída pode deixar coleta parcial: não promover, preservar para diagnóstico e usar outra saída. Não há manifesto completo que legitime evidência parcial.

A presença regional de um provedor não comprova contratação por assinatura ou uma oferta de qualquer filme. Apenas `flatrate` confirmada para a obra/região pode satisfazer RESTRITO. `rent`, `buy`, `free`, `ads`, ausência de informação e erro continuam distintos.

Atualizações e remoções devem passar pela mesma revisão. A UX-02 conserva IDs antigos como pendências e requer remoção explícita. O catálogo atual é carregado na inicialização; o procedimento não reinicia o servidor nem introduz atualização em tempo real. A estratégia de promoção em processo, preservando sessões em RAM, precisa ser aprovada antes de utilizá-la; reiniciar o processo perderia sessões conforme a política atual.

## B — Revisão documental limitada

| Situação | Evidência oficial e consequência |
|---|---|
| Confirmado | A [FAQ TMDB](https://developer.themoviedb.org/docs/faq) admite uso não comercial com atribuição e considera comercial o propósito principal de gerar receita. Não documenta exceção acadêmica autônoma. Exige logo aprovado nos créditos/sobre, menos proeminente que a marca principal, sem sugerir endosso e sem alterações indevidas de cor, proporção ou orientação. A classificação concreta do projeto depende de revisão humana. |
| Confirmado | A documentação de [watch providers](https://developer.themoviedb.org/reference/movie-watch-providers) exige atribuir disponibilidade à JustWatch e permite usar o link TMDB fornecido para acesso às ofertas. Esse endpoint não entrega todos os deep links. |
| Confirmado, para outro produto | A documentação da [JustWatch Content Partner API](https://apis.justwatch.com/docs/api/) descreve contratação e token próprios, links regionais de marca junto à integração e identificação JustWatch. Não se deve transpor automaticamente essas condições de contratação direta ao uso indireto pelo TMDB. |
| Bloqueado | [Termos TMDB](https://www.themoviedb.org/api-terms-of-use) e [logos/atribuição](https://www.themoviedb.org/about/logos-attribution) foram novamente bloqueados por robots na consulta automatizada. Não houve acesso integral aos termos aplicáveis TMDB/JustWatch. |
| Não verificado | Prazo contratual de cache/retenção, direito de redistribuição, exibição fora da aplicação, remoção obrigatória, condições de sublicença e eventuais restrições específicas da parceria. Ausência de texto não é permissão. TTLs técnicos não são homologação jurídica. |

A [documentação de limites TMDB](https://developer.themoviedb.org/docs/rate-limiting) informa limites sujeitos a mudança e pede respeito ao HTTP 429. Os parâmetros internos desta implementação não são limites oficiais ou direitos contratuais de consulta.

Proposta textual de seção **Créditos e fontes**, ainda não publicada:

> Metadados e imagens: TMDB. [Inserir somente logo aprovado após revisão.]
>
> This product uses the TMDB API but is not endorsed or certified by TMDB.
>
> [Somente ao exibir disponibilidade real:] Dados de disponibilidade: JustWatch, via TMDB. [Link de origem fornecido pela resposta, região e data da consulta.]

Recomendação de implementação: seção acessível de créditos/sobre, linkada da página; atribuição de disponibilidade próxima à informação; nenhuma marca ou afirmação de disponibilidade enquanto desativada. Validar desenho/logotipos e obrigações específicas com responsável humano. O rodapé existente não certifica conformidade completa. Nenhum novo logo ou crédito foi publicado nesta atividade.

## C — Controles internos implementados

### Sessões

`app.py` conserva endpoints, JSON, cookie, expiração e dicionário `sessoes[sid]=(Sessao,instante)`. A trava global, agora `TravaRegistro`, cobre somente localização/expiração e atualização do registro, não o cálculo de conversa. Operações da mesma sessão são protegidas por `EstadoSessao.trava`; sessões diferentes podem progredir em paralelo. Operações em andamento são contadas para impedir expiração durante sua execução. Respostas são copiadas sob a proteção da sessão, evitando referências mutáveis ao estado após liberar a trava.

`EstadoSessao.snapshot()` fornece cópia independente, versão e identidade privada do registro. `aplicar(snapshot,funcao)` recusa versão antiga ou snapshot de outra sessão. Sucesso e possíveis mutações parciais em erro invalidam snapshots anteriores. Leitura `estado` não incrementa versão. Não se alterou a classe pública `Sessao`, nem o notebook.

Padrão para a futura integração: obter o registro sob proteção breve, tirar snapshot sob a trava da sessão, consultar fora dessas travas e aplicar somente se a versão ainda corresponder. A ligação desse padrão a uma recomendação pública com disponibilidade continua proibida nesta etapa; será preciso também validar associação/expiração do registro antes de publicar, sem ressuscitar sessão encerrada. Nenhum resultado externo é aplicado hoje à página.

Os clientes conhecidos verificam `TravaRegistro` antes de admitir rede e falham fechados se chamados naquela seção crítica. Isso não intercepta qualquer chamada arbitrária de bibliotecas terceiras: futuras integrações deverão passar pelos controles. Não há alteração no cálculo das recomendações, nas referências ou na UX-01/UX-02.

### Cache e deduplicação de disponibilidade

`ConsultasPorChave` protege somente consulta/atualização de cache e registro de operações equivalentes. O produtor executa HTTP fora dessa trava. A mesma chave de conteúdo/região tem um único produtor; seguidores esperam evento por prazo limitado ou recebem erro temporal, sem fabricar sucesso. Chaves diferentes podem progredir em paralelo. Hits válidos não consomem orçamento ou ficam atrás de uma consulta lenta. Catálogo usa chave própria por país/idioma/fonte. Identidades e TTLs anteriores são preservados.

Cada produção utiliza um cache privado transitório de `Disponibilidades`, com o mesmo contrato, sem persistência nova. Só o resultado validado é gravado no cache compartilhado sob trava curta. A contagem HTTP é local à thread, impedindo atribuir ao usuário chamadas concorrentes de outro filme. O contador acumulado do transporte permanece disponível.

### Orçamento compartilhado por credencial/processo

`ControleExterno`, injetável, adota os padrões conservadores:

| Parâmetro | Padrão | Justificativa |
|---|---:|---|
| Operações externas concorrentes | 2 | Limita pressão e permite operação independente; decisão interna |
| Admissões por janela móvel | 60 em 60 s | Teto inicial conservador; uma reserva pode não chegar a iniciar HTTP |
| Espera por vaga | Até 3 s, ou prazo restante menor | Evita fila infinita; configurável no controlador |
| Espera por mesma chave | Até 3 s, ou prazo restante menor | Não duplicar consulta quando produtor demora; limite de espera, não do produtor |
| Timeout HTTP | Até 3 s, ou prazo restante menor | Mantém teto do transporte anterior |
| Registro de credenciais | Até 64 chaves por processo | Falha fechada ao exceder; não expulsa quota ativa para contorná-la |

Clientes reais de disponibilidade e pôsteres com o mesmo token obtêm o mesmo controlador por hash SHA-256; o registro não guarda o token bruto. Isso não torna o hash apropriado para publicação: o registro é privado e não é exportado. Transportes injetados usam controladores isolados por padrão para não contaminar testes; simulações de quota compartilhada injetam explicitamente a mesma instância. Credenciais continuam privadas nos transportes; nunca são colocadas na sessão ou no JSON.

Cache não consome admissão. Não há retry automático. HTTP 429 suspende o controlador compartilhado conforme Retry-After; mantém-se também o cooldown local já existente. Valores inválidos/não finitos de Retry-After dos pôsteres agora usam 60 s, evitando suspensão infinita. A contagem de admissão é conservadora e pode exceder a quantidade de requisições HTTP realmente iniciadas; os contadores do filtro distinguem as duas coisas. O intervalo local de 0,2 s continua como precaução de transporte, não como limite oficial.

Os limites funcionais do filtro permanecem **20 tentativas, 50 candidatos, até 10 resultados e 5 segundos cooperativos**. Não há relaxamento de RESTRITO nem preenchimento com desconhecidos. Erros/orçamento esgotado mantêm resultados confirmados e indicam verificação parcial.

### Prazos: o que é e não é garantido

`Prazo` usa relógio monotônico e é propagado em contexto síncrono do filtro ao serviço/transporte. A espera por vaga/chave e o timeout de I/O são limitados pelo restante. Um prazo que expira antes da rede evita a chamada. Não se prometem cinco segundos rígidos: I/O já iniciado, leitura em etapas, DNS, escalonamento ou um transporte injetado não cooperativo podem ultrapassar o prazo. Não há thread de abandono que continue consultando em segundo plano.

Separar: espera por trava curta de cache/registro; espera por outro produtor da mesma chave; fila por vaga de rede; intervalo local entre inícios; transporte/leitura; tempo total. A fila tem timeout próprio e o transporte recebe o restante; ambos não devem ser interpretados como prazo total adicional permitido ao filtro. Um futuro executor precisaria propagar explicitamente o contexto de prazo.

### Riscos remanescentes

- O cache de **pôsteres** mantém sua trava por instância durante rede e persistência. Foi conectado ao orçamento compartilhado, mas separar esse ciclo exige revisão específica para não introduzir gravações concorrentes/inconsistentes. Não se afirma cache de pôsteres paralelo.
- O cliente legado de pôsteres ainda precisa de revisão defensiva específica de redirecionamentos e tamanho da resposta antes de alegar equivalência com o transporte estrito de disponibilidade.
- Quota e deduplicação são por processo/instância conforme documentado, não distribuídas entre vários processos. O servidor HTTP pode criar muitas threads sob carga; não houve teste de carga de produção.
- Esperas por travas curtas não constituem garantia de latência sob qualquer condição do sistema; não há prazo total rígido.
- Publicação de resultados externos, tratamento de sessão expirada, promoção do catálogo e condições jurídicas precisam de aprovação posterior. Não ampliar automaticamente esta atividade para resolver esses itens.
