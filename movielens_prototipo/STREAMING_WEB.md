> Registro histórico: streaming foi definitivamente descontinuado em 11/11/2026. Os módulos e rotas aqui descritos não fazem parte do produto atual. Consulte [encerramento de escopo](../docs/ENCERRAMENTO_ESCOPO_CINEMATCH.md).

# RF-02D — Interface de preferências de streaming

Configuração de sessão, sem filtro de disponibilidade ativo. A página informa claramente que a seleção não altera as recomendações. Nenhuma oferta fictícia é apresentada. O transporte RF-02B não é construído ou chamado por esta integração; algoritmo, pesos, referências, histórico, rejeições e gêneros seguem o fluxo anterior. RF-02E e Etapa 5 pausadas; termos integrais TMDB ainda pendentes.

## Catálogo público e interface

A inspeção do repositório não encontrou catálogo regional de provider IDs homologado. `streaming_web.CATALOGO_BR` é uma tupla vazia intencional. Não foram inventados IDs nem consultado TMDB. Provedores fictícios só aparecem nas fixtures dos testes e páginas de evidência, nunca no catálogo servido pela aplicação.

A seção inicial “Seus serviços (opcional)” contém região Brasil, área preparada para grade de checkboxes, contagem textual, modos nativos RESTRITO/FLEXÍVEL e botão Salvar. Sem catálogo, mostra “Catálogo de serviços em validação”, sem opções reais; o usuário ainda pode escolher/salvar o modo e continuar com filmes. A escolha não é obrigatória. RESTRITO é a apresentação padrão de uma configuração nova, não uma ativação de filtro.

Quando um catálogo local confiável for aprovado em etapa posterior, o mesmo componente renderiza IDs/nomes recebidos do servidor, sem imagens ou marcas externas. Os rótulos envolvem checkboxes nativos com ID/for e área clicável mínima de 44px mais padding. Fieldset/legend agrupam serviços e modos; contagem/status têm aria-live. Não há eventos que substituam teclado nativo. Estado é indicado por checkbox/rádio e texto, não só cor.

Grid usa auto-fit/minmax com mínimo limitado à largura disponível; opções e modos quebram linhas. Nenhuma biblioteca ou fonte externa foi adicionada. Os textos aproveitam o contraste existente; os pares calculados variam de 8,32:1 a 13,96:1. Isso não comprova todos os requisitos de acessibilidade ou responsividade.

## Salvamento e comportamento

`static/streaming.js` separa preferências do estado de recomendações. Marcar/desmarcar e trocar modo são edições locais, com contagem e aviso de alterações não salvas. Salvar não recarrega a página nem renderiza novamente cartões ou referências. O servidor preserva todo o perfil. Uma resposta de salvamento não sobrescreve edição nova feita enquanto a requisição estava em andamento. Falha mantém as escolhas e permite nova tentativa.

O foco não é redirecionado no carregamento inicial. Salvar conserva inputs/DOM; se o botão perdeu foco apenas por ter sido desabilitado, ele recebe foco de volta, sem roubar foco de outro campo. Repetir carregamento após falha permite retomar no primeiro serviço/modo se o foco ainda estiver no body. São comportamentos exercitados em DOM simulado; navegação física por teclado e leitor de tela ainda precisam de teste em navegador.

O bootstrap espera o estado inicial de recomendações estabelecer o cookie antes de buscar streaming, evitando duas sessões criadas simultaneamente sem cookie. Os botões de streaming são independentes do bloqueio temporário dos botões de conversa. Ao reiniciar a sessão, o painel recarrega o estado zerado. Falha do recurso/endpoint de streaming não impede buscar filmes e recomendar.

## API pública adicionada

`POST /api/streaming` recebe JSON, com os mesmos limites de corpo, cookies HttpOnly/SameSite=Strict, expiração e verificação de Origin do POST existente. Sem CORS novo. As duas operações são locais, sem cliente TMDB:

```json
{"acao":"estado"}
```

```json
{"acao":"salvar","regiao":"BR","provedores":[],"modo":"restrito"}
```

Com catálogo homologado, provedores será uma lista de IDs numéricos distintos pertencentes ao catálogo interno. IDs 10/20 usados nos testes são fictícios e rejeitados no catálogo público vazio. IDs negativos, booleanos, strings, repetidos, desconhecidos, país diferente e modo inválido retornam 400, sem alteração de preferências. Campos extras, incluindo `ativo`, `integracao_ativa`, token ou URLs, são rejeitados; não são ecoados no erro.

Resposta de estado inicial atual:

```json
{"catalogo":{"regiao":"BR","provedores":[],"estado":"pendente_validacao"},"preferencias":null,"integracao_ativa":false,"mensagem":""}
```

Após salvar modo sem serviços:

```json
{"catalogo":{"regiao":"BR","provedores":[],"estado":"pendente_validacao"},"preferencias":{"regiao":"BR","provedores":[],"modo":"flexivel","ativo":false},"integracao_ativa":false,"mensagem":"Preferências salvas nesta sessão. A seleção ainda não altera as recomendações."}
```

O servidor fixa ativo=False independentemente do navegador; não há chave de habilitação operacional neste endpoint. O transporte e o filtro não são importados por `streaming_web.py`. A integração de disponibilidade permanece desligada, mesmo com modo restrito ou flexível salvo. Seleção de plataformas não configura credenciais dos serviços.

`GET /static/streaming.js` é o único recurso estático novo. Os endpoints anteriores e o JSON de `/api/recomendar` mantêm os campos/semântica. Foi extraído em `app.py` um helper privado de cookie/expiração, compartilhado pelos dois POSTs sob a mesma trava, preservando o mecanismo anterior.

## Sessão

Reutiliza `Sessao.streaming`/`PreferenciasStreaming`. Sem configuração continua None até salvar; mostrar zero na interface não salva implicitamente uma seleção vazia. Salvar uma lista vazia é uma configuração consciente, sempre inativa. Cada cookie tem seu objeto de sessão; atualizar página restaura IDs/modo enquanto existir a sessão. RAM somente, sem banco/login/persistência permanente; expira após duas horas de inatividade ou ao encerrar/reiniciar o servidor. Reiniciar sessão limpa também streaming, preservando o significado do controle.

## Testes e limitações

`testes_streaming_web.py` verifica catálogo vazio, salvamento/remoção/múltiplos IDs/modos, restauração, preservação do perfil, isolamento e cookie HTTP, Origin, erros, ausência de ativação e código sem credencial. `testes_streaming.cjs` executa o widget e o bootstrap real com DOM/fetch simulados: labels, contagem, mudanças, refresh, falhas, foco, respostas antigas e sequência inicial de sessão. As suítes anteriores continuam disponíveis.

A tentativa de captura local com Firefox headless em página de fixture, sem recursos externos e com fetch simulado, terminou por sinal/erro 139 antes de gerar imagem. Não houve inspeção visual concluída nem prova real de responsividade. A grade foi conferida no código/DOM e o contraste calculado; uso móvel, zoom, leitores de tela e teclado real seguem pendentes. Não confundir DOM simulado com conformidade completa.

Nenhum módulo incorporado ao notebook foi alterado: seus seis literais foram conferidos contra arquivos atuais e ele permaneceu intacto, sem execução. Nenhum resultado experimental/dataset ou arquivo de pontuação foi modificado.

## Pendências RF-02E

Homologar um catálogo local de provedores/IDs BR com procedência confiável e revisão antes de expor opções reais. Concluir termos integrais, atribuições TMDB/JustWatch e configuração operacional antes de considerar ativação externa. Definir orçamento/deadline/global/concorrência HTTP, versionamento de perfil e acesso ao conjunto ordenado antes do Top 10 preservando score. Validar visualmente/por teclado/leitor de tela. Se catálogo mudar durante uma sessão, definir UX explícita para IDs antigos, sem descartar silenciosamente escolhas.

Nada disso foi iniciado automaticamente. Não há oferta real consultada, filtro ativo, nova modalidade de recomendação, série ou integração item–item nesta etapa.


## Atualização RF-02E1

O catálogo agora é lido de `catalogo_streaming_br.json` por `catalogo_streaming.py`, permanecendo vazio por falta de evidência regional. Capturas reais offline foram obtidas com Firefox em quatro larguras; foco interativo e acessibilidade completa seguem pendentes. A tentativa histórica RF-02D acima foi preservada como registro. Veja [relatório RF-02E1](HOMOLOGACAO_STREAMING.md) para procedimento de homologação, alterações mínimas e limitações.


## UX-02 — Reconciliação e foco

O estado/salvamento agora inclui `reconciliacao={provedores_ausentes:[],revisao_necessaria:false}`. IDs salvos fora do catálogo permanecem na preferência e são exibidos separadamente como pendências, sem se tornarem provedores homologados. Para remover, desmarcar e salvar envia a lista opcional `remover_incompativeis`; ela deve ser subconjunto dos IDs ausentes da própria sessão e não estar em `provedores`. Omissão por cliente antigo preserva IDs históricos; inclusão de novos desconhecidos é recusada. O filtro continua sempre inativo.

Após confirmar filmes ou retirar referência, o foco vai ao título estável “Seu perfil”; em erro retorna ao controle inicial quando necessário. Mudanças de foco feitas durante a espera são respeitadas. `api()` não foi alterada. Detalhes, exemplos sintéticos, testes e limitações em relatório local `verificacoes/ux02_20261030/RELATORIO.md` (evidência bruta não distribuída; veja a [preparação de publicação](../docs/GIT02_RELATORIO.md)).
