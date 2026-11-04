# Avaliação de referência na validação interna

Runner separado: `avaliacao_interna.py`. Não altera métodos de produção nem seleciona pesos, regras ou sementes pelo resultado. A Etapa 5 permanece pausada. A entrada aprovada é `experimentos/divisao_interna_20261029_final/`, com 64.960 avaliações em desenvolvimento e 15.936 em validação, semente interna 101, fração nominal 0,20. Relevância: nota >=4.

## Ordem de execução e procedência

1. Carrega contexto de desenvolvimento pelo carregador isolado. Confere o manifesto da divisão, os hashes/tamanhos dos artefatos como bytes e a cadeia de procedência: treino original semente 42, manifesto aprovado da avaliação anterior, identidade do dataset e assinatura do catálogo. Não abre o treino original como tabela, o teste original, ratings completo, ranking ou matriz de produção.
2. Usa somente o desenvolvimento para gerar listas com `avaliacao_perfil.gerar_listas()`, que chama o `Recomendador.recomendar_perfil()` real e reproduz as ordens existentes dos baselines. Mínimos de usuário e filme: cinco. A semente de referências é **201**, fixada antes dos resultados, conforme a proposta da divisão interna.
3. Calcula estatísticas com TODOS os usuários elegíveis de desenvolvimento. Restringe somente as listas à coorte fixa com pelo menos cinco positivos. Excluir usuários fora dessa coorte antes de calcular ranking mudaria estatísticas globais, portanto isso não é feito.
4. Salva todas as listas da coorte e as estatísticas em um diretório novo. Registra a assinatura das listas antes de abrir notas reservadas.
5. Só então executa a auditoria semântica da divisão, que confere conservação/disjunção sem construir modelos; carrega validação com a identidade de execução esperada e reutiliza `pontuar_listas()` para métricas. Validação nunca é passada para a função de geração. Confere que a assinatura das listas não mudou.
6. Publica resultados e manifesto próprio, confere hashes e preserva as entradas. Não sobrescreve diretórios ocupados nem permite saída dentro dos diretórios de entrada.

O uso do manifesto anterior é apenas para confirmar origem e catálogo por hash; nenhuma métrica anterior é usada, nem seus rankings carregados. A confiança na procedência é externa: hashes detectam divergências, não substituem assinatura autenticada contra adulteração deliberada de toda a cadeia.

## Coorte, referências e candidatos

Coorte fixa: usuários com pelo menos cinco notas >=4 exclusivamente no desenvolvimento (594 na divisão real). O sorteio é independente por usuário com `SeedSequence([201,userId])`, após ordenar IDs dos positivos. As configurações de 1–5 referências são prefixos da mesma amostra de cinco.

Em cada usuário/configuração:

```
C(u,n) = filmes com suporte >=5 no desenvolvimento
         menos todo o histórico de desenvolvimento individual
         com algum gênero em comum com as n referências
```

O marcador `(no genres listed)` é removido. Preferências positivas/negativas explícitas e rejeições ficam vazias; o experimento simula o perfil inicial com referências apreciadas, não conversa ou refinamento. A aplicação aceita assistidos provisórios, portanto a simulação não equivale a qualquer uso humano.

- Popularidade: ordem existente por contagem, contagem e menor movieId, restringida a C.
- Nota ponderada: fórmula existente calculada só no desenvolvimento e ordem por W, contagem e menor movieId, restringida a C.
- Perfil: método de produção intacto, incluindo score, filtros e desempates; todo o desenvolvimento individual é informado como assistido.

Os dois baselines são **condicionados aos candidatos do perfil**, não os baselines globais históricos. Os três métodos compartilham usuários e candidatos dentro de n; C pode mudar entre quantidades de referências. Estatísticas de desenvolvimento são salvas apenas como evidência desta execução; nunca substituem os artefatos da aplicação.

## Métricas e denominadores

Reutilizados `pontuar_listas()` e `metricas_top10()`, sem mudar fórmulas:

- Precision@10: acertos/10, inclusive se a lista tiver menos de dez itens.
- Recall@10: acertos/todos os positivos de validação do usuário.
- NDCG@10: relevância binária, desconto log2(posição+1), ideal com até dez positivos.
- Positivos fora de C permanecem no denominador de Recall e no ideal de NDCG.
- Usuário sem positivos na validação recebe métricas ausentes e não entra em nenhuma das três médias, preservando a política anterior; seu ID consta em `usuarios.csv` e `auditoria.json`. Não se fabrica zero.
- Usuário com positivos e sem candidatos recebe lista vazia e métricas zero; não é descartado da qualidade.
- Médias de qualidade são macro entre usuários avaliáveis. A mesma coorte avaliável é verificada entre todos os métodos e tamanhos.
- Média de recomendações e cobertura usam TODOS os usuários elegíveis da coorte, inclusive sem positivos na validação. Cobertura é a fração que recebeu ao menos uma recomendação, não cobertura do catálogo nem Recall.
- Candidatos mínimo, mediana, média e máximo são calculados entre os usuários elegíveis de cada n, sem triplicar cada usuário por método.

Rótulos `relevantes_teste` dos componentes reutilizados são renomeados para `relevantes_validacao` nas saídas; isso não muda o cálculo. `coorte=fixa_5` identifica a população única do experimento.

## Execução e saídas

Na raiz, com diretório de saída novo:

```sh
.venv/bin/python -B movielens_prototipo/avaliacao_interna.py \
  --divisao experimentos/divisao_interna_20261029_final \
  --treino movielens_prototipo/resultados/treino.csv \
  --procedencia experimentos/avaliacao_perfil_20261028/manifesto.json \
  --filmes movielens_prototipo/resultados/filmes.csv \
  --saida experimentos/NOVA_AVALIACAO_INTERNA
```

Artefatos: `listas.csv`, `estatisticas_desenvolvimento.csv`, `avaliacao_por_usuario.csv`, `usuarios.csv`, `resumo.csv`, `resumo.json`, `auditoria.json` e `manifesto.json`. Reutiliza reserva exclusiva, marcador de preparação e SHA-256/tamanho da Etapa 3. Esquema próprio `cinematch.experimento.avaliacao_interna`, versão 1, não carregável como resultados de produção. O manifesto registra dataset, execução da divisão, hashes das entradas/código/saídas, parâmetros e versões. `validar_saida()` verifica integridade dos sete artefatos; não autentica o autor do manifesto nem substitui uma auditoria semântica independente.

## Limitações

É avaliação de referência, não seleção de um método novo. Uma divisão e uma amostra de referências não demonstram robustez; não há teste de significância ou intervalo de confiança nesta execução. As notas observadas não representam todos os gostos ou exposições; ausência não significa rejeição. Os candidatos mudam com as referências; diferenças entre n não podem ser atribuídas exclusivamente à representação do gosto. O uso de referências positivas é mais específico que informar qualquer filme assistido na página. Não são avaliados UX, conversa, disponibilidade, diversidade ou satisfação.

Não comparar diretamente os valores com os do teste original: partições, estatísticas, amostra de referências e população são diferentes. O teste original permanece fora das decisões. Caso esta validação passe a orientar ajustes, subdivisões de desenvolvimento e uma avaliação final adequada serão necessárias; não apresentá-la como teste intocado após seleção reiterada.

O notebook e os módulos exportados de produção não foram modificados; o runner experimental não é dependência da aplicação. Os testes sintéticos em `testes_avaliacao_interna.py` são registrados na suíte principal.
