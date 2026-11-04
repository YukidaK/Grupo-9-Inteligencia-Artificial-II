# GIT-02 — preparação local para publicação

Atividade de 03/11/2026, com auxílio do Codex. Preparação documental e seleção local; nenhuma publicação foi realizada. A revisão humana de licença, privacidade e histórico ainda é necessária.

## Estado inicial e limites

A inspeção inicial confirmou raiz com `.git`, branch `main`, remoto `origin` configurado, 22 arquivos rastreados, 11 modificados, 377 não rastreados, staging vazio e um commit histórico. Esses são os números anteriores às alterações desta etapa; as regras novas reduzem a listagem dos artefatos brutos, sem excluir arquivos. O remoto não foi acessado nem alterado e sua URL não é reproduzida aqui. A visibilidade e o estado remoto atual não foram consultados.

Não foram executados staging, commit, push, pull, inicialização, limpeza ou reescrita do histórico. Não houve instalação, download, consulta externa, execução do notebook, reexecução de experimentos ou mudança de código de produção. Os testes funcionais Python/JavaScript não foram reexecutados: esta etapa altera documentação, regras de seleção e cópias históricas, e executa validações de leitura.

## Alterações realizadas

Foram criados 31 arquivos nesta etapa: documentação, cópias históricas e agregados selecionados. A lista integral, incluindo arquivos anteriores candidatos a publicação, contém 96 caminhos.

Novos documentos:

- `README.md`: entrada do projeto, contexto acadêmico, execução, testes e limites reais.
- `docs/DATASET.md`: procedência, hash, formato, obtenção e condições locais do MovieLens.
- `docs/REPRODUCAO_CHECKPOINT2.md`: protocolos, sementes, métricas, comandos e limites de reprodução.
- `docs/GIT02_RELATORIO.md`, `docs/GIT02_VALIDACAO.json` e `docs/CANDIDATOS_STAGING.txt`: esta entrega, resultados de validação e lista precisa para revisão futura.
- `reproducao/README.md`, `reproducao/SELECAO.json`, configuração item–item, quatro manifestos documentais e dez módulos históricos selecionados.
- `relatorios/checkpoint2/README.md`, seis resumos CSV/JSON e um relatório agregado dos baselines globais.

Arquivos anteriores modificados exclusivamente nesta etapa:

| Arquivo | Alteração |
|---|---|
| `.gitignore` | Ignorar experimentos/verificações brutos, dependências Node e cobertura. |
| `movielens_prototipo/.gitignore` | Complementar proteção de temporários, logs e checkpoints. |
| `movielens_prototipo/README.md` | Atualizar documentação para o comportamento real. |
| `movielens_prototipo/STREAMING_WEB.md` | Remover link público quebrado para evidência local, preservando referência textual. |
| `movielens_prototipo/PROTECAO_POSTERES.md` | Mesmo ajuste para relatório local de pôsteres. |

As alterações de código e do notebook que já existiam no início foram preservadas. Não são mudanças feitas pela GIT-02.

## Estrutura e proposta de versionamento

```text
README.md
.gitignore
docs/                         guias e preparação de publicação
movielens_prototipo/           código, testes, interface, configurações públicas
relatorios/checkpoint2/        somente agregados selecionados
reproducao/                    fontes históricas mínimas e procedência
```

A lista exata de candidatos está em [CANDIDATOS_STAGING.txt](CANDIDATOS_STAGING.txt), um caminho relativo por linha. Ela inclui código e testes atuais, inclusive módulos ainda não rastreados necessários à aplicação, arquivos estáticos, requisitos, catálogo homologado vazio e `.env.example` sem segredo. Não é uma autorização de staging, publicação ou licenciamento. A seleção de fontes históricas continua sujeita à decisão de licença de código.

A — candidatos a publicação após aprovação: arquivos dessa lista, com dependências locais cobertas e documentação portátil. B — publicação após revisão específica: notebook, exemplo de saída e relatório antigo de verificação. C — manter somente local: `.venv/`, dataset e ZIP, resultados completos, experimentos brutos, verificações brutas, caches, logs, sessões, credenciais, `.env` privados, temporários e documento de trabalho. D — decisão do responsável: licença, visibilidade, divulgação de dados de autoria no histórico e autorização da seleção acadêmica derivada.

`experimentos/` e `verificacoes/` continuam disponíveis localmente; foram apenas ignorados. O guia público não depende de sua distribuição: apresenta como gerar uma cadeia nova. Não há exceção com `git add -f`. Arquivos agregados necessários foram copiados para diretórios próprios, com hashes e origem em [SELECAO.json](../reproducao/SELECAO.json).

## Histórico, privacidade e segurança

O commit anterior contém e-mail de autoria não anonimizado, cuja divulgação depende de decisão humana. Não é reproduzido neste relatório. O notebook tem nome de arquivo identificável; nenhum nome de participante foi adicionado como crédito nos novos documentos. O documento de trabalho e evidências brutas podem conter caminhos locais e permanecem fora da seleção.

**Os três arquivos sob revisão específica já são rastreados:** notebook acadêmico, `EXEMPLO_SAIDA.json` e `RELATORIO_VERIFICACAO.md`. Deixá-los fora do próximo staging não os remove do conteúdo já commitado nem do histórico que um push pode enviar. A publicação não está liberada enquanto esse ponto não for decidido. Nenhum comando de remoção ou reescrita foi executado; não se presume autorização para fazê-lo.

A revisão por padrões fortes da seleção não substitui auditoria completa de privacidade, revisão semântica ou verificação de todos os tipos de segredo. As evidências anteriores não indicaram credencial real comprometida; não se declara ausência absoluta de segredos. `.env.example` já existe com valor vazio e permanece inalterado; não é necessário criar outro template. Não se reproduzem tokens, cookies, endereços privados ou conteúdo de configuração privada.

Não há arquivo de licença de código definido. A seleção não acrescenta uma licença automaticamente. As condições locais do MovieLens foram documentadas; não se afirma autorização irrestrita para redistribuir derivados. A disponibilização real de streaming continua desativada e depende das condições TMDB/JustWatch e da homologação regional. Nenhum logotipo ou imagem externa foi acrescentado.

## Reprodução e resultados

O [guia de reprodução](REPRODUCAO_CHECKPOINT2.md) separa código atual de [fontes históricas](../reproducao/README.md). Nove módulos históricos coincidem com os hashes do manifesto item–item; o carregador adicional tem procedência separada. O `conversa.py` atual tem hash diferente do histórico e não foi substituído. Não se alterou manifesto para forçar compatibilidade.

Os quatro manifestos preservados são referências, sem partições ou matrizes. Não bastam para verificar integralmente uma execução antiga. Os comandos propostos geram novos artefatos e manifestos próprios em saída nova; a igualdade dos resultados em outra máquina não foi medida nesta etapa. A configuração prévia preservada não é apresentada como hipótese retroativa nem como um novo pré-registro.

Os [relatórios selecionados](../relatorios/checkpoint2/README.md) são cópias exatas de agregados, sem registros por usuário ou filme. Não houve novo cálculo de métricas. A publicação dos agregados continua dependendo da revisão do responsável quanto às condições aplicáveis.

## Notebook e arquivos locais

O notebook foi lido como JSON, sem executar células: 15 células, sete de código e zero saídas incorporadas. A revisão local identificou instalação de dependências, exportação de módulos, geração de resultados e ZIP com informações individuais. Seu código e bytes foram preservados. Para uma futura execução, usar cópia isolada, revisar células e manter exportações locais. Não há homologação integral do notebook numa cópia pública ainda.

As pastas brutas não são necessárias para instalar a aplicação ou executar testes sintéticos. São necessárias evidências históricas completas para validar as execuções antigas integralmente, e elas continuam preservadas localmente. Sem a cópia histórica do dataset não se promete reprodução exata apenas baixando a URL `latest`.

## Validações realizadas

O resultado detalhado está em [GIT02_VALIDACAO.json](GIT02_VALIDACAO.json). Resultado final: 654 arquivos anteriores conferidos, cinco alterações autorizadas e 649 hashes iguais; nenhum arquivo anterior ausente. Permaneceram íntegros sete arquivos do dataset, oito dos resultados, 32 dos experimentos, 487 das verificações e 51 metadados Git. As 22 cópias selecionadas coincidem com suas origens e nove módulos com o manifesto histórico. Foram validados 49 links locais; os 96 candidatos não são ignorados. Cinco exemplos de arquivos nos grupos locais protegidos foram confirmados como ignorados. Nenhum padrão forte de segredo, e-mail ou caminho privado foi encontrado na seleção, dentro do alcance da varredura.

Estado Git ao concluir: 22 rastreados, 13 modificados e 77 não rastreados, staging vazio. A diferença de contagens inclui alterações anteriores, arquivos novos e novas regras de ignore; não representa exclusão de evidências. `git diff --check` aprovado. Procedimentos locais:

1. Inspeção Git de leitura: status, arquivos rastreados, staging, branch, remotos sem exposição de credenciais e histórico disponível.
2. SHA-256 dos 654 arquivos anteriores fora do ambiente virtual e `__pycache__`, incluindo metadados Git; comparação com o inventário anterior às escritas. Somente os cinco documentos/regras autorizados acima podem diferir; nenhum arquivo anterior pode desaparecer.
3. Comparação byte a byte por hash das 22 cópias selecionadas com suas origens; confronto dos nove módulos atestados pelo manifesto histórico.
4. Análise sintática AST dos módulos atuais e históricos para conferir fechamento das dependências locais sem executar algoritmos. Dependências externas esperadas: NumPy, pandas e SciPy; bibliotecas padrão verificadas separadamente.
5. Leitura JSON do notebook e das seleções; inspeção dos campos de agregados para evitar registros individuais.
6. Verificação de links Markdown locais contra os próprios candidatos públicos, sem acessar URLs externas.
7. Varredura da seleção por padrões fortes de segredo, e-mail, URL com credencial e caminho privado; verificação de espaços finais e `git diff --check`.
8. `git check-ignore --stdin` sobre candidatos, `git status --short --untracked-files=all` e `git diff --cached --name-only`, confirmando que o staging continua vazio.

Comandos de reprodução e instalação nos guias são instruções futuras; não são resultados de testes desta atividade. A checagem de links confirma arquivos selecionados e caminhos, não disponibilidade das URLs externas. Análise AST e hashes não substituem testes funcionais, execução completa ou aprovação jurídica.

## Checklist para futura aprovação do commit

- [ ] Aprovar a lista exata de candidatos e revisar o diff completo, incluindo alterações anteriores à GIT-02.
- [ ] Decidir a licença do código e os direitos de publicação de fontes e agregados.
- [ ] Decidir sobre notebook e nome identificável, exemplo e relatório antigo já rastreados.
- [ ] Revisar dados de autoria do commit histórico e definir procedimento autorizado, sem reescrita automática.
- [ ] Repetir varredura de segredos e verificar que dados, caches e resultados individuais estão fora da seleção.
- [ ] Validar os comandos de reprodução numa execução futura separada, se for exigida comprovação completa.
- [ ] Autorizar expressamente staging e commit; ainda não autorizados.

## Checklist para futura aprovação do push

- [ ] Aprovar visibilidade pública ou privada do repositório e destino remoto.
- [ ] Revisar todos os objetos/histórico que seriam enviados, incluindo arquivos não selecionados agora mas já commitados.
- [ ] Resolver privacidade e licenciamento; aprovar créditos pertinentes.
- [ ] Confirmar que nenhum dado local ou segredo entrou no commit proposto.
- [ ] Conferir funcionamento a partir da seleção aprovada, sem depender das pastas ignoradas.
- [ ] Autorizar expressamente o push; ainda não autorizado.

A GIT-02 encerra na preparação local. Não autoriza GitHub, ativação de streaming, alteração de algoritmos ou continuidade da Etapa 5.
