# Correção do temporizador do autocomplete — 20/10/2026

O JSON fornecido pelo usuário confirmou o funcionamento do endpoint real de busca. Foi identificado um defeito no widget: setTimeout e clearTimeout eram armazenados e chamados como métodos da instância MovieAutocomplete, alterando o receptor de APIs nativas de Window. Isso pode lançar TypeError/Illegal invocation antes da requisição de autocomplete. A correção usa wrappers que chamam explicitamente window.setTimeout/window.clearTimeout por meio do objeto global do widget. Referência técnica: https://html.spec.whatwg.org/multipage/timers-and-user-prompts.html#timers

O teste da página completa foi fortalecido com temporizadores que exigem o receptor Window. Antes da correção, dois cenários falharam com Illegal invocation: setTimeout; depois, os onze cenários JavaScript passaram, incluindo cancelamento da primeira digitação, busca, exibição da lista e seleção por teclado. A suíte principal passou com 44 testes aprovados e 1 pulado por restrição de sockets. Os testes continuam simulando DOM e APIs de navegador, sem afirmar validação visual real.

A URL do JavaScript foi atualizada para v=20261020-3. Como o backend atual lê HTML/JS a cada GET, basta atualizar a página principal com Ctrl+Shift+R para carregar essa correção; o endpoint de busca já demonstrado pelo usuário não exige nova configuração.

Registros anteriores:

---

# Diagnóstico de sugestões ausentes — 20/10/2026

Foi corrigida a falta de orientação quando o script externo do widget não carrega ou a página recebe HTTP 404 do endpoint de busca. A página continua utilizável sem o script e mostra como reiniciar o processo e atualizar o navegador. O JS do widget tem URL versionada para atualização de cache. Não foi determinada a causa específica observada no navegador do usuário.

Onze cenários JavaScript passaram, incluindo três novos testes de integração do código real da página: bootstrap e exibição de sugestão, arquivo do widget ausente sem derrubar a página e backend antigo exibindo orientação. O DOM e o transporte são simulados. O acesso direto à porta 8000 foi impedido pela sandbox; a tentativa de Firefox headless falhou na inicialização, portanto não houve validação visual real.

Registros anteriores:

---

# Verificação do autocomplete — 20/10/2026

- `python testes.py`: 45 testes, 44 aprovados e 1 pulado (socket local bloqueado pela sandbox). Inclui os testes anteriores de pipeline acadêmico, conversa e pôsteres.
- Nove testes adicionais de autocomplete cobrem acentos/caixa, aliases presentes no catálogo, prioridade das correspondências, erros pequenos, consulta sem relação, títulos parecidos/remakes e anos, números no título, limite de oito, IDs únicos, confirmação de mais de cinco filmes, exclusão de assistidos e busca HTTP sem mutação de sessão.
- O teste JavaScript executa o widget real com DOM/rede/relógio simulados: oito cenários passaram para debounce, respostas fora de ordem, cancelamento ignorado pelo transporte, teclado (setas/Enter/Escape), mouse/toque, duplicatas, remoção, excedentes e preservação em falhas. Enter sem destaque não escolhe nenhuma opção nem envia o formulário. Seleções novas durante uma confirmação em andamento são mantidas.
- Busca exercitada também com o catálogo real MovieLens: títulos parciais, erro “Toy Stroy”, remakes, “matrix” e consulta sem relação. Nenhuma chamada TMDB é necessária para buscar títulos.
- Sintaxe Python e dos dois scripts JavaScript validada. O notebook preserva o fluxo de revisão por lote e foi sincronizado com a conversa atualizada.
- Não houve validação visual em navegador real, com leitor de tela ou em Windows; acessibilidade foi verificada pelas propriedades ARIA, comportamento do widget e testes simulados. O aplicativo não exige Node: ele é opcional apenas nos testes JavaScript.
- O motor de recomendação, baselines e split não foram alterados nesta melhoria.

Registros anteriores:

---

# Verificação da melhoria de pôsteres TMDB — 20/10/2026

- 14 testes de integração simulada TMDB passaram: mapeamento, ausências/conflitos, idiomas, resposta sem pôster, timeout/API indisponível, ID incorreto, caminhos inválidos, 429 e Retry-After, cache persistente/expiração/corrupção, 404, variáveis de ambiente, endpoint e funcionamento sem credencial.
- Suíte anterior: 21 testes passaram e 1 de sockets locais foi pulado por restrição da sandbox. Somados aos 14 testes TMDB, são 35 aprovados e 1 pulado. Os testes não realizam chamadas TMDB reais.
- A base real agora está disponível. Recalculei em memória limpeza, split e rankings: treino.csv, teste.csv e ranking_treino.csv correspondem à recomputação. As métricas dos dois baselines coincidem com relatorio.json. Não sobrescrevi os resultados acadêmicos.
- Mapeamento real conferido: movieId 1 → tmdbId 862. Recomendações de um perfil real permaneceram idênticas após consultar placeholders sem token.
- Sintaxe Python/JavaScript validada; carregamento sob demanda e fallback de imagem quebrada exercitados com DOM/fetch simulados em Node, sem introduzir dependências na aplicação.
- Não havia TMDB_READ_ACCESS_TOKEN disponível: autenticação e imagens reais do TMDB **não foram validadas**. Não houve validação visual em navegador ou execução em Windows. O logo usa o asset aprovado vinculado na página oficial, sem recriá-lo; sua exibição depende de conexão pública ao TMDB.
- Documentação oficial de autenticação, detalhes, imagens/configuração, idiomas, limites e atribuição consultada; links estão no README.

Os registros abaixo descrevem verificações anteriores, inclusive limitações da base antes de os CSVs estarem disponíveis.

---

# Verificação da adaptação — 20/10/2026

Ambiente: Pop!_OS 24.04 x86_64, Python 3.12, NumPy 2.5.2, pandas 3.0.5, SciPy 1.18.1. Dependências instaladas de wheels já existentes no cache local, pois o DNS da sandbox impediu instalar pela rede.

`python testes.py`: 22 testes, 20 passaram e 2 foram pulados explicitamente. Cobertura: uma a cinco referências, aviso com uma, excedentes e duplicatas, exclusão de todo histórico, substituição explícita, rejeição sem contribuição positiva, busca ambígua/desconhecida, persistência e mudança efetiva das preferências, ausência de candidatos sem relaxar restrições, mensagens desconhecidas preservando estado, explicação fiel, reinício e isolamento de sessões. Também passaram limpeza, split reproduzível e sem sobreposição, métricas conhecidas e integração do pipeline com matriz CSR e estatísticas exclusivamente do treino usando fixture sintética. As células do notebook de preparação, busca/seleção e refinamento também foram executadas com fixture; módulos embutidos foram conferidos contra os arquivos atuais. Sintaxe Python e JavaScript validada.

O handler HTTP real passou com transporte em memória: busca → confirmação → recomendações → preferência negativa → explicação → reinício; cookies distintos não compartilham estado. Isso valida o contrato e o serviço, mas não equivale a executar a interface em navegador.

## Limitações da verificação atual

- **Base real não reexecutada.** `python recomendador.py` tentou baixar MovieLens, mas falhou com `URLError: Name or service not known`. Não havia CSVs nem resultados preparados neste workspace. O teste de recomendações reais foi pulado por essa ausência.
- **Sockets locais bloqueados pela sandbox.** O teste com servidor HTTP em porta local foi pulado por `PermissionError: Operation not permitted`. A demonstração visual em navegador não foi validada neste ambiente. Em um terminal comum, execute `app.py` após obter os dados.
- Windows foi documentado, não executado. O arquivo de versões fixa o ambiente científico verificado em Python 3.12 no Linux; dependências específicas de outra plataforma são resolvidas pelo pip.
- A conversa é um parser local restrito, sem LLM. A qualidade subjetiva das recomendações e a compreensão textual não foram medidas. Os pesos são didáticos e fixos.
- Nenhuma métrica real nova é apresentada. O novo perfil não foi avaliado offline; não reutilizamos números dos baselines como resultado da conversa.

## Relatório histórico recebido com o protótipo

O texto abaixo foi preservado como registro **anterior à adaptação**, sem revalidar seus números nesta execução. `EXEMPLO_SAIDA.json` também é um exemplo do endpoint antigo por gêneros, não do fluxo atual. Não use o trecho técnico histórico sobre a página como descrição da nova interface; consulte o README atualizado.

---

# Verificação com a base real

Execução realizada em 20/10/2026. Não foram usados dados sintéticos para os resultados abaixo.

- Python 3.12.14; NumPy 2.3.5; pandas 2.2.3; SciPy 1.17.0.
- 100.836 avaliações; 610 usuários; 9.742 filmes no catálogo.
- 80.896 avaliações de treino e 19.940 de teste.
- 3.218 filmes elegíveis (mínimo de 5 avaliações no treino).
- Matriz CSR: 610 × 8.960; esparsidade 98,52%.
- 595 usuários avaliados; 15 sem notas relevantes no teste excluídos das médias.
- 9.607 itens relevantes nos testes individuais; 8.520 elegíveis para recuperação. Os demais continuam contando como não recuperados.

| Baseline | Precision@10 | Recall@10 | NDCG@10 |
|---|---:|---:|---:|
| nota_ponderada | 0.058151 | 0.044629 | 0.083118 |
| popularidade | 0.117815 | 0.094891 | 0.158173 |

A popularidade superou a nota ponderada neste protocolo. Isso não mede a qualidade da interpretação textual. Como as métricas dependem do protocolo, não compare diretamente com artigos que usam outros candidatos, filtros ou divisões.

## Exemplo real de saída

Entrada: “Quero suspense com investigação e mistério”. Gêneros identificados: Crime, Mystery, Thriller. Primeiros resultados: The Usual Suspects (1995), Chinatown (1974), Reservoir Dogs (1992). Veja os dez resultados em EXEMPLO_SAIDA.json.

## Verificações

Cinco testes automatizados passaram: separação sem sobreposição e reproduzível; limpeza de duplicados/notas inválidas; métrica de resultado conhecido com item inelegível; recomendações reais com limite de dez e exclusão dos vistos; HTTP da página e da API, incluindo rejeição de entrada vazia.

A interface HTML não foi inspecionada visualmente em navegador neste ambiente. O fluxo HTTP e o retorno JSON foram testados. A qualidade subjetiva das dez recomendações precisa ser discutida pelo grupo.

## Texto técnico que pode ser adaptado ao trabalho

Foi empregado o conjunto MovieLens ml-latest-small para a construção de um protótipo de recomendação de filmes. Após a validação estrutural das avaliações, foi realizado holdout aleatório por usuário com aproximadamente 80% das interações para treino e 20% para teste, utilizando semente 42. Os critérios de elegibilidade e estatísticas dos baselines foram calculados exclusivamente no treino. Foram comparados rankings por popularidade e nota ponderada, com remoção dos itens já avaliados no treino. A avaliação adotou Precision@10, Recall@10 e NDCG@10, considerando relevantes as notas de teste iguais ou superiores a quatro. O protótipo web associa palavras-chave do pedido a gêneros e combina a compatibilidade de gêneros com estatísticas do treino, sem implementar compreensão semântica livre.

## Para explicar oralmente

“Minha parte prepara os dados, esconde uma parte das notas de cada usuário e cria dois rankings simples para comparação. Depois verifico quantos filmes que o usuário avaliou bem no teste aparecem entre as dez sugestões. A interface demonstra o uso com texto, mas reconhece palavras de gêneros; ainda não é um modelo de linguagem.”
## Correção da inicialização após erro SSL

O aplicativo aceita `dados/ml-latest-small.zip` baixado manualmente, registra seu hash e extrai os arquivos conhecidos. Falhas HTTPS agora mostram uma orientação curta. Dois testes adicionais passaram: leitura do ZIP local sem solicitar rede e orientação em falha de certificado simulada. A validação TLS não foi desabilitada. O aviso do endereço agora aparece somente depois de abrir a porta com sucesso.
