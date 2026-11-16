> Registro histórico: streaming foi definitivamente descontinuado em 11/11/2026. Os módulos e rotas aqui descritos não fazem parte do produto atual. Consulte [encerramento de escopo](../docs/ENCERRAMENTO_ESCOPO_CINEMATCH.md).

# RF-02C — Preferências de sessão e filtragem controlada

Somente fluxo interno com dados sintéticos/transporte simulado. O recomendador e o JSON/endpoints/interface atuais não foram alterados. Nenhum ponto de `app.py` ou `Conversa.atualizar()` chama o filtro. O transporte continua desativado por padrão. RF-02D e Etapa 5 pausadas; revisão integral dos termos ainda pendente. Não está pronto para uso externo.

## Sessão e preferências

`Sessao.streaming` começa em **None**, indicando ausência de configuração, e não escolha de zero provedores. Uma configuração existente é `PreferenciasStreaming(provedores=frozenset(...), regiao='BR', modo=Modo.RESTRITO, ativo=False)`. Ativar exige `ativo=True` explícito. Os objetos são imutáveis, contêm somente IDs, região, modo e ativação, sem token ou cliente HTTP.

`Modo` e `PreferenciasStreaming` foram isolados em `preferencias_streaming.py`, somente stdlib. `disponibilidade.py` reexporta os mesmos nomes, preservando imports e argumentos posicionais anteriores; `ativo` é novo parâmetro opcional ao final. Isso permite que a sessão/notebook use preferências sem importar transporte/pôsteres. A função de classificação `compatibilidade()` continua classificando evidência, independentemente da ativação; só o filtro decide se deve aplicá-la.

`sessao.configurar_streaming(preferencias, provedores_permitidos=..., regiao_catalogo=...)` exige preferências tipadas, IDs positivos inteiros e subconjunto do catálogo daquela região. Rejeita bool, textos, IDs desconhecidos e país divergente antes de atribuir. O chamador futuro deverá obter esse catálogo de fonte validada/vigente; o setter não realiza consultas nem autentica uma lista arbitrária fornecida por código interno.

Alterar/desativar substitui somente a configuração; não modifica histórico, referências, rejeições ou gêneros. Outra sessão permanece independente. `reiniciar` conserva seu significado anterior de limpar a sessão inteira, inclusive a configuração interna nova. O JSON público não inclui o campo streaming, mesmo se um teste o configurar diretamente; nenhuma ação pública nova o altera.

## Entrada e saída do filtro

`filtrar_streaming(candidatos, preferencias, servico, limites=...)` recebe iterável de `CandidatoStreaming(conteudo, dados)`, já pontuado/ordenado pelo chamador. Só aceita identidades FILME e score finito. `CandidatoStreaming.movielens(dados)` adapta explicitamente o movieId legado; identidade e movieId precisam coincidir. Não associa obras por título ou modifica gêneros.

Preserva ordem e todas as pontuações, inclusive empates, sem recalcular ou ordenar. A primeira ocorrência de cada identidade prevalece; repetições são ignoradas e contam no limite de exame, impedindo iteradores de duplicatas ilimitados. Cópias dos dados evitam mutar o candidato original. O filtro não constrói perfis nem exclui histórico: recebe candidatos previamente elegíveis, já sem assistidos/rejeitados. O chamador deve validar 1–5 referências antes de gerar esses candidatos; o caminho público continua fazendo isso como antes.

`ResultadoStreaming` mantém itens separados de suas marcações de disponibilidade, classificação, evidência verificada, estatísticas, limites e mensagem. É resultado interno, não uma alteração no JSON web. Nenhum campo é inserido nos objetos originais da recomendação pública.

### Modos

- **Sem configuração ou desativado:** devolve o prefixo original, sem consultar disponibilidade ou anexar alegações de acesso. Limite de tamanho e remoção de duplicatas continuam protegendo o componente isolado; candidatos normais únicos mantêm o mesmo prefixo.
- **RESTRITO ativo:** aceita somente assinatura vigente, na região e em pelo menos um ID escolhido. Aluguel, compra, free/ads, desconhecido, erro, resposta de outro filme/país e evidência vencida/futura não qualificam. Não há fallback. Lista pode ter menos de dez ou zero itens.
- **RESTRITO ativo sem IDs:** devolve vazio e orientação para escolher serviço, sem ler candidatos nem consultar. Distingue explicitamente essa escolha da ausência de configuração.
- **FLEXIVEL ativo:** não exclui por disponibilidade; mantém os primeiros candidatos elegíveis e anexa evidência/estado. Informação vencida perde ofertas e vira desconhecida, preservando data antiga; desconhecido/erro não significa acesso incluído. Falta de orçamento/prazo produz marcação não verificada. Esse modo não é ativado automaticamente como alternativa ao restrito.

## Consulta atômica e orçamento

`ClienteDisponibilidadeTMDB.obter_controlado(conteudo, regiao, permitir_consulta=False)` usa a trava RF-02B para decidir cache/local/consulta em uma operação. `Disponibilidades.obter_sem_consulta()` inspeciona cache válido ou produz apenas resultado local sem vínculo/tipo. Não há acesso a rede nesse método. Não se faz um peek seguido de uma consulta independente, que poderia competir com outro pedido.

`ConsultaControlada` informa CACHE, LOCAL, CONSULTA ou NAO_VERIFICADO. O transporte conta aberturas efetivas do opener; habilitação, termos e credencial continuam sendo barreiras distintas. `permitir_consulta=True` permite gastar uma tentativa do pedido, mas **não ativa o transporte**. Em teste, esse opener é simulado; chamada de transporte não significa chamada real de internet.

Valores iniciais, configuráveis e fixados antes dos testes, sem otimização:

| Limite | Padrão | Justificativa |
|---|---:|---|
| Tentativas externas potenciais | 20 | Até duas vezes o tamanho final, sem varrer catálogo |
| Candidatos lidos | 50 | Busca limitada de acertos/cache e proteção contra milhares de misses/duplicatas |
| Prazo cooperativo | 5s | Interromper novas consultas em vez de prolongar indefinidamente a interação |
| Tamanho | 10 | Até dez; aceita valor de 1–10 |

São limites técnicos iniciais, não cotas/latências garantidas pelo TMDB. Cache e resultados locais não gastam as vinte tentativas. Após esgotar a cota, ainda se podem aproveitar entradas de cache dentro dos cinquenta candidatos/prazo; misses permanecem não verificados. No modo flexível, após deadline apenas se completam marcações desconhecidas, sem chamar o serviço. Não lê todo o iterável nem procura automaticamente outros milhares de filmes.

### Estatísticas distintas

| Campo | Significado |
|---|---|
| `cache` / `locais` | Respostas atendidas sem consulta potencial externa |
| `consultas_necessarias` | Cache misses identificados que precisariam de consulta, autorizados ou barrados |
| `tentativas_orcadas` | Misses cuja consulta foi autorizada; limite conservador mesmo se transporte desativado/pausado não abrir rede |
| `chamadas_transporte` | Aberturas efetivas do opener nesta solicitação; sempre simuladas nesta atividade |
| `nao_verificados` | Candidatos sem consulta ou com resposta temporal/identidade/região inadequada |
| `confirmados_assinatura` | Candidatos aceitos como incluídos na assinatura pela evidência |
| `desconhecidos` / `erros` | Estados recebidos/normalizados; não são indisponibilidade comprovada |

Um erro da fonte é uma consulta feita sem conseguir confirmar, não candidato jamais consultado. Datas são reavaliadas após retorno do serviço; dado que vence durante uma chamada não se torna confirmação válida. Serviços injetados devem respeitar `permitir_consulta`; o componente rejeita declaração incompatível, mas não pode desfazer rede que um adaptador hostil já tenha disparado.

`parcial=True` e os motivos CONSULTAS/CANDIDATOS/TEMPO registram limitação operacional; erros/evidência inválida também tornam a informação parcial. Se a cota foi toda usada mas o prefixo necessário foi confirmado sem pendências, isso não torna a resposta artificialmente parcial. A mensagem não diz que não existem mais títulos; restringe a conclusão ao conjunto consultado. Nunca preenche vagas desconhecidas no modo restrito.

## Prazo, concorrência e riscos de integração

O prazo é **cooperativo**, verificado antes de novas operações e após respostas. Não cancela uma consulta ou espera de lock já iniciada; uma chamada começada antes de cinco segundos pode terminar depois. O timeout RF-02B limita operações de socket, não toda a solicitação. O item já confirmado pode ser retornado, com indicação de limite, sem iniciar outro pedido. Um teste simula essa ultrapassagem.

A trava da RF-02B elimina duplicações da mesma chave, porém serializa chaves e catálogo na instância. Pedidos independentes têm orçamento próprio e podem somar mais que vinte consultas; não há orçamento compartilhado com pôsteres ou entre processos. Nenhuma arquitetura HTTP foi alterada nesta etapa.

Em `app.py`, a trava global `Handler.trava` engloba a execução da conversa. Inserir rede diretamente nesse trecho bloquearia outras sessões. RF-02D deve definir snapshot/versionamento do perfil, liberação da trava durante I/O e rejeição de resposta obsoleta se preferências mudarem, com testes, antes de integrar. Isso é proposta, não refatoração feita.

O método público `recomendar_perfil()` continua cortando em dez. O novo filtro não pode recuperar candidatos que o chamador já descartou: testes fornecem uma sequência sintética maior e mostram um elegível na posição onze. RF-02D precisará de autorização para expor a ordem completa antes do corte, preservando fórmulas/desempates. Não houve cópia/modificação do algoritmo para contornar esse limite agora.

## Notebook e compatibilidade

O notebook incorpora a versão atual de `conversa.py` e o novo módulo puro `preferencias_streaming.py`, além dos cinco módulos anteriores. Os seis literais foram conferidos contra os arquivos sem executar o notebook, instalar dependências ou acessar dados. A fonte de pontuação e os artefatos experimentais permanecem intactos. O núcleo real do aplicativo e uma requisição HTTP em memória foram testados sem credenciais/configuração de streaming, preservando os campos públicos.

## RF-02D e licenciamento

Continuam pendentes termos integrais, configuração operacional e atribuições TMDB/JustWatch antes de uso externo. Não se testou autenticação ou disponibilidade real. Não existe checkbox, endpoint novo, nova ação pública, filtro ativado, série ou integração item–item.

Próximos passos, somente se autorizados: concluir licenciamento; revisar acesso aos candidatos antes do Top 10 e orçamento global/deadline; definir integração HTTP concorrente e versionamento; expor preferências com UX explícita; apresentar listas menores e estados honestos; manter 1–5 referências, histórico/rejeições e pontuação. Não executar consulta real ou habilitar produção automaticamente.
