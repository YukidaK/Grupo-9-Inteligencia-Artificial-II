# Encerramento de escopo e estabilização do CineMatch

## 1. Identificação e motivo

Atividade executada em 11 e 12/11/2026, com auxílio do Codex, para reduzir definitivamente o escopo devido ao prazo acadêmico de Inteligência Artificial II da FIB. Branch `next-updates`; commit-base `b6f9aca2cc4bff57397fd3dfda16e92d90945999`. Não houve commit, push, troca de branch ou alteração da `main`. O working tree já possuía alterações de busca em português e arquivos não rastreados, preservados durante esta atividade.

## 2. Funcionalidades mantidas

Servidor Python local; carregamento MovieLens; busca por título original e aliases brasileiros; autocomplete; seleção de uma a cinco referências; remoção de escolhas antes de confirmar; confirmação e até dez recomendações; justificativas, ano e pôster opcional; restauração da sessão; nova seleção. Zero referências não produz recomendações; uma ou duas recebem orientação adicional, sem promessa de maior precisão.

A nova confirmação substitui as referências e conserva o histórico conhecido para exclusão de candidatos. O botão “Nova seleção” reinicia o estado e as escolhas. Essa operação é explícita, não uma ação de rejeição.

## 3. Funcionalidades descontinuadas

Streaming foi retirado do produto, incluindo painel, catálogo, modos, preferências, filtro e consultas de disponibilidade. A rota `/api/streaming` e o script antigo retornam 404. Não há mensagem “em breve”. Foram retirados conversa textual, comandos de gêneros, rejeição e refinamento posterior. A API essencial aceita `estado`, `confirmar_selecao` e `reiniciar`; ações antigas e campos incompatíveis são rejeitados com HTTP 400.

A retirada neutra posterior à confirmação também deixou de ser um controle do produto. A remoção antes da confirmação permanece disponível, conforme o escopo aprovado.

## 4. Arquivos removidos e alterados

Removidos do diretório ativo `movielens_prototipo/`:

- `disponibilidade.py`, `tmdb_disponibilidade.py`, `catalogo_streaming.py`, `coletar_catalogo.py`;
- `preferencias_streaming.py`, `streaming_web.py`, `filtro_streaming.py`, `catalogo_streaming_br.json`;
- `static/streaming.js`, `testes_streaming.cjs`;
- `testes_disponibilidade.py`, `testes_tmdb_disponibilidade.py`, `testes_filtro_streaming.py`, `testes_streaming_web.py`, `testes_catalogo_streaming.py`.

Alterados nesta atividade: `app.py`, `conversa.py`, `index.html`, `static/autocomplete.js`, `piloto_titulos.py`, `testes.py`, `testes_conversa.py`, `testes_autocomplete.py`, `testes_autocomplete.cjs`, `testes_operacao_externa.py`, `testes_protecao_posteres.py` e `testes_piloto_titulos.py`; README principal, README técnico e `TITULOS_BR.md`. Os seis documentos técnicos de streaming receberam avisos de caráter histórico, preservando seu conteúdo anterior.

Criados: `transporte_tmdb.py`, `testes_transporte_tmdb.py`, `testes_fluxo_essencial.py` e este relatório. Os arquivos de aliases e busca já estavam em desenvolvimento antes desta atividade; seu trabalho foi preservado.

As cópias anteriores dos módulos e testes retirados foram preservadas localmente em `verificacoes/encerramento_escopo_20261111/codigo_antes/`. Documentação acadêmica, métricas e fontes históricas de reprodução não foram apagadas. A seleção antiga `docs/CANDIDATOS_STAGING.txt` é histórica e precisará de nova revisão antes de qualquer publicação; não foi usada para staging nesta atividade.

## 5. Dependências compartilhadas preservadas

`posteres.py`, `operacao_externa.py`, `estado_sessao.py`, busca, aliases, identidade e artefatos continuam disponíveis. O piloto importava o transporte HTTP do módulo de disponibilidade. Essa dependência foi isolada em `transporte_tmdb.py`, preservando HTTPS, limites, sanitização, autorização explícita e orçamento, sem conservar consultas de streaming. Não há coleta ao iniciar a aplicação ou digitar uma busca.

`Conversa` permanece como nome legado do controlador de seleção. `Sessao` conserva os campos internos `positivos`, `negativos` e `rejeitados` vazios no fluxo público, por compatibilidade com o algoritmo e experimentos existentes; não há ações públicas para preenchê-los.

## 6. Impacto nos algoritmos

`recomendador.py` não foi modificado. Fórmulas, pesos, filtros, baselines, divisão e métricas históricas foram preservados. Foram registrados seis perfis antes e depois: `[318]`, `[858]`, `[318,858]`, `[318,858,3147]`, `[1,318,858,3147]` e `[1,318,858,3147,2571]`. IDs e ordem coincidiram; pontuações coincidiram com tolerância absoluta de `1e-12`.

A avaliação foi uma comparação determinística do fluxo padrão com os artefatos já existentes, não um novo experimento de otimização. Item–item permanece exclusivamente experimental. Os testes de caracterização de pontuação com preferências internas continuam disponíveis para proteger a fórmula, embora esses controles tenham sido retirados da interface.

## 7. Pesquisa em português

Preservados 9.742 filmes MovieLens e três aliases homologados: `318 → 278 → Um Sonho de Liberdade`, `858 → 238 → O Poderoso Chefão` e `3147 → 497 → À Espera de um Milagre`. Os pares numéricos são MovieLens e TMDB, conferidos no mapeamento local. A pesquisa utiliza o índice local e normalização de acentos/caixa, sem tradução automática nem associação aproximada de IDs. A conferência final executou sete consultas locais, cobrindo os três aliases, versões sem acento e títulos originais: todas retornaram o ID esperado. Registro: `checagens_finais.json`, na pasta local de evidências.

O piloto dos 100 filmes e suas evidências permanecem intactos: dois títulos previamente cadastrados no recorte e 98 consultas pendentes. Nenhuma dessas consultas foi realizada. A cobertura pública permanece três de 9.742; 9.739 filmes não têm alias brasileiro cadastrado. Isso não significa que não exista tradução na fonte.

## 8. Situação dos pôsteres

O código utiliza `links.csv`, autenticação Bearer no servidor, metadados de filme e configuração de imagens do TMDB. URLs de imagens são limitadas ao destino autorizado. Permanecem timeout, bloqueio de redirecionamento, limites durante leitura, validação de resposta, cache de metadados por sete dias, deduplicação e escrita atômica. `posteres.py` permaneceu idêntico ao snapshot anterior.

Não foi encontrada credencial de ambiente/configuração local na conferência anterior aos testes. Não houve chamada real autenticada ao TMDB. Assim, obtenção real de novos pôsteres não está homologada nesta entrega. Os testes sintéticos verificam transporte e falhas; o fluxo sem credencial retorna o placeholder, sem impedir recomendações. Credenciais nunca são enviadas ao navegador.

## 9. Testes e evidências

Comandos executados na raiz, sem instalação de dependências:

```sh
.venv/bin/python -B -m unittest discover -s movielens_prototipo -p testes.py
node --test --test-isolation=none movielens_prototipo/testes_autocomplete.cjs
git diff --check
```

| Verificação em 12/11/2026 | Aprovados | Falhos | Ignorados |
|---|---:|---:|---:|
| Suíte Python completa do escopo reduzido | 206 | 0 | 0 |
| Suíte JavaScript/DOM simulado | 19 | 0 | 0 |
| Comparação determinística de perfis | 6 | 0 | 0 |

A suíte inicial tinha 313 testes Python: 312 aprovados e um ignorado por restrição de socket. A comparação por identificador encontrou 196 testes com nomes mantidos, 117 retirados ou renomeados e dez novos ou adaptados. A redução inclui os testes exclusivos de disponibilidade, catálogo, filtro, interface de streaming e conversa/feedback, além da adaptação de testes compartilhados. A relação individual está em `alteracoes_testes.json`, na pasta local de evidências. Não corresponde a 117 defeitos nem a 117 arquivos removidos.

Os 36 casos JavaScript anteriores passaram a 19: retirada da suíte exclusiva de streaming, substituição do caso de excedentes pelo limite de cinco, retirada de ações de feedback e inclusão de casos do fluxo essencial e placeholder. Permanecem navegação no autocomplete, concorrência de buscas, aliases, erros e os quatro casos de foco na confirmação.

Durante a adaptação houve erros nas fixtures dos testes e importações do transporte; foram corrigidos antes da rodada final. Não se alteraram valores esperados da fórmula para obter aprovação.

Logs finais: `verificacoes/encerramento_escopo_20261111/python_final.log` e `javascript_final.log`. Diretórios de verificações são locais e ignorados pelo Git.

### Validação real no Firefox

Em 12/11/2026, o Firefox headless, controlado por WebDriver/Marionette, executou a página e as rotas reais com o catálogo/modelo local, sessão isolada e pôsteres sem token. Passaram busca “O Poderoso Chefao” sem acento, seleção por setas/Enter, remoção antes de confirmar, busca “Um Sonho de Liberdade”, confirmação, dez cartões, foco no título estável do perfil, recarregamento com restauração e nova seleção por “The Green Mile”. Foram usadas teclas WebDriver reais, não apenas eventos de DOM simulado. Não houve consumo de serviços externos: proxy externo fechado, CSP restrita à origem e cliente de pôsteres sem credencial.

As capturas foram obtidas para larguras solicitadas de 360, 768, 1366 e 1920 px; o Firefox impôs mínimo efetivo de 500 px no primeiro caso. Logo, as larguras efetivamente medidas foram 500, 768, 1366 e 1920 px, sem transbordamento horizontal nos estados capturados. As 12 imagens de pôster/miniatura presentes nesses estados carregaram o placeholder. A inspeção visual de capturas em 500 e 1366 px confirmou organização dos controles e foco visível; isso não certifica acessibilidade completa nem 360 px. Evidências: `verificacoes/encerramento_escopo_20261111/visual_final/`, com quatro PNGs, log e `interacoes.json`.

Na tentativa anterior, a automação tentou acessar uma variável lexical pelo sandbox do WebDriver; na retomada, a espera por sugestões antigas ainda no DOM também provocou timeout. O roteiro foi corrigido para observar o estado acessível `aria-expanded`, sem alterar código de produção para fazer o teste passar. A rodada final passou.

## 10. Limitações e preservação

A verificação de 82 arquivos protegidos encontrou zero divergências: dados, resultados, experimentos, fontes históricas selecionadas, notebooks, piloto local e componentes compartilhados especificados no manifesto local. `integridade_final.json` registra a contagem e o HEAD. Também foram conferidos 487 arquivos anteriores de `verificacoes/`, com zero divergências. Não foram reexecutados experimentos históricos, o notebook ou a coleta de títulos.

O notebook original foi preservado e não sincronizado: ele é material histórico, e suas células que exportam módulos antigos não devem ser executadas sobre a aplicação final. Para estudo, usar cópia isolada e revisar essas células. A reprodução histórica continua usando suas próprias versões e hashes, sem editar manifestos para forçar compatibilidade.

Não há homologação de API externa, leitor de tela, todos os navegadores ou acessibilidade completa. Termos e direitos de terceiros continuam aplicáveis; não foi criada licença geral de reutilização do código.

## 11. Estado final do Git e encerramento

Branch `next-updates`, `main` e HEAD preservados; staging vazio. Não houve commit ou push. As alterações anteriores e arquivos não relacionados foram mantidos. O próximo passo é revisão humana desta redução e das limitações documentadas, sem reintroduzir funcionalidades descontinuadas.
