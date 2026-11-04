# Reprodução histórica selecionada

Esta pasta prepara uma reprodução histórica; não substitui a aplicação atual. Os arquivos foram selecionados e copiados sem alterar bytes. A publicação ainda depende da revisão humana de licença e privacidade.

- `historico_20261029/`: nove módulos cujo SHA-256 coincide com o campo de código do manifesto item–item de 29/10/2026; `carregamento_movielens.py` é uma dependência adicional preservada na verificação de 28/10/2026. Esse décimo arquivo não constava da lista de nove hashes do manifesto item–item; sua procedência é registrada separadamente.
- `referencias/`: cópias exatas dos manifestos de avaliação de perfil, divisão interna final, comparação interna e item–item. São referências documentais; os artefatos individuais que eles descrevem não estão publicados. Não é possível validar essas pastas como execuções completas apenas com os manifestos.
- `configuracao_item_item.json`: cópia da configuração prévia registrada, sem alterar parâmetros ou data.
- [SELECAO.json](SELECAO.json): caminho relativo da origem local, SHA-256 e tipo de cada arquivo selecionado, incluindo os resumos públicos. Os caminhos de origem descrevem evidências locais e não prometem sua distribuição.

O `conversa.py` atual difere do hash histórico. Não substituir arquivos, editar hashes ou combinar controles de uma versão com módulos de outra para contornar a validação. O carregador histórico forma uma dependência de apoio; a correspondência integral do ambiente e dos resultados ainda exige execução autorizada. Não houve reexecução nesta preparação.

O [guia do Checkpoint 2](../docs/REPRODUCAO_CHECKPOINT2.md) apresenta uma cadeia nova com entradas geradas em diretórios separados, usando o código histórico ou o atual. Os manifestos novos terão IDs, horários e hashes próprios; não são cópias binárias das execuções originais. A igualdade de métricas não foi novamente medida aqui.

Não há dataset, avaliações individuais, matrizes ou pacote integral de verificações nesta seleção. Os módulos arquivados não devem ser importados pela aplicação pública. O ambiente de referência é Linux/Python 3.12; a medição `resource` do item–item não foi portada para Windows. A licença do código ainda não foi definida.
