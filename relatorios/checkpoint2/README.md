# Checkpoint 2 — resultados agregados selecionados

Preparação local para revisão humana. Os resumos CSV/JSON e o relatório de baselines globais são cópias exatas das evidências anteriores; não foram recalculados, arredondados ou substituídos. Origem e hashes constam em [SELECAO.json](../../reproducao/SELECAO.json). A preparação documental contou com auxílio do Codex; não implica conferência manual adicional pelo grupo.

| Seleção | Experimento histórico |
|---|---|
| [Baselines globais](baselines_globais.json) | Estatísticas e avaliação no teste original, provenientes do relatório local de produção. |
| [Perfil — CSV](avaliacao_perfil/resumo.csv) / [JSON](avaliacao_perfil/resumo.json) | Avaliação de 28/10/2026 no teste original; inclui as coortes registradas. |
| [Comparação interna — CSV](avaliacao_interna/resumo.csv) / [JSON](avaliacao_interna/resumo.json) | Três controles, divisão interna, 29/10/2026. |
| [Item–item — CSV](item_item/resumo.csv) / [JSON](item_item/resumo.json) | Quatro métodos na mesma comparação interna, 29/10/2026. |

As tabelas preservam todos os algarismos registrados e incluem quantidades de candidatos, cobertura e tamanho médio quando disponíveis. O [protocolo](../../docs/REPRODUCAO_CHECKPOINT2.md) explica as diferenças de população, referências e candidatos. Não comparar diretamente o teste externo com a validação interna.

Na comparação interna: 594 usuários elegíveis, 586 com positivos na validação e oito excluídos das médias de qualidade, sem zeros artificiais. Popularidade superou nota ponderada e perfil nas três métricas em todas as quantidades de referências. Item–item superou o perfil por gêneros, mas permaneceu abaixo da popularidade. Não se conclui superioridade universal, nem se autoriza substituir o algoritmo da página. A relação entre item–item e nota ponderada varia conforme a métrica e a quantidade de referências.

Não foram selecionados ratings individuais, listas por usuário, partições, matrizes, logs brutos ou capturas. As contagens e métricas agregadas não dispensam a revisão humana de licenciamento e privacidade antes da publicação. Reconhecimento da fonte e condições locais do MovieLens estão em [DATASET.md](../../docs/DATASET.md); o código não recebeu licença geral de reutilização, e a concordância dos titulares continua sujeita à revisão humana.
