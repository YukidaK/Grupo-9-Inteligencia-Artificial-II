"""Experimento offline isolado do perfil web; não treina nem modifica produção."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from artefatos_resultados import (
    ARQUIVOS, MANIFESTO, PENDENTE, assinatura, iniciar_identificacao, validar_resultados,
)
from conversa import Sessao
from recomendador import Recomendador, avaliar, dividir, limpar, ranking

ROOT = Path(__file__).resolve().parent
K = 10
RELEVANTE = 4.
METODOS = ('popularidade', 'nota_ponderada', 'perfil')
METRICAS = ('precision_at_10', 'recall_at_10', 'ndcg_at_10')
ESQUEMA = 'cinematch.experimento.perfil'


def selecionar_referencias(treino, seed=42):
    """Até cinco positivos do treino, amostra aninhada e independente por usuário."""
    selecao = {}
    for u, grupo in treino.groupby('userId', sort=True):
        ids = sorted(grupo.loc[grupo.rating >= RELEVANTE, 'movieId'].unique())
        rng = np.random.default_rng(np.random.SeedSequence([seed, int(u)]))
        selecao[int(u)] = [int(i) for i in rng.permutation(ids)[:5]]
    return selecao


def metricas_top10(recomendacoes, positivos):
    """Relevância binária; sem positivos, as métricas são indefinidas (None)."""
    if len(recomendacoes) > K or len(recomendacoes) != len(set(recomendacoes)):
        raise ValueError('Lista deve conter até dez IDs distintos.')
    if not positivos:
        return dict.fromkeys(METRICAS, None)
    acertos = [int(i in positivos) for i in recomendacoes]
    dcg = sum(v / np.log2(j+2) for j, v in enumerate(acertos))
    ideal = sum(1 / np.log2(j+2) for j in range(min(K, len(positivos))))
    return dict(zip(METRICAS, (sum(acertos)/K, sum(acertos)/len(positivos), dcg/ideal)))


def _validar_pares(treino, teste, filmes):
    if filmes.movieId.duplicated().any():
        raise ValueError('IDs duplicados no catálogo.')
    for nome, tabela in (('treino', treino), ('teste', teste)):
        if not {'userId', 'movieId', 'rating', 'timestamp'}.issubset(tabela.columns):
            raise ValueError('Colunas ausentes no ' + nome)
        if tabela.duplicated(['userId', 'movieId']).any():
            raise ValueError('Pares duplicados no ' + nome)
        if not tabela.rating.between(.5, 5).all() or not tabela.rating.mul(2).mod(1).eq(0).all():
            raise ValueError('Notas inválidas no ' + nome)
        if not set(tabela.movieId).issubset(set(filmes.movieId)):
            raise ValueError('Avaliações fora do catálogo no ' + nome)
    if set(zip(treino.userId, treino.movieId)) & set(zip(teste.userId, teste.movieId)):
        raise ValueError('Sobreposição de pares entre treino e teste.')
    if not set(teste.userId).issubset(set(treino.userId)):
        raise ValueError('Usuário do teste sem histórico no treino.')


def gerar_listas(treino, filmes, *, min_filme=5, min_usuario=5, seed=42, progresso=None):
    """Não recebe teste: referências, estatísticas e candidatos dependem só do treino.

    C(u,n) = itens com suporte mínimo no treino, menos TODO o histórico do
    usuário, com ao menos um gênero em comum com suas n referências.
    O filtro de gêneros replica apenas elegibilidade S>0, não pontuação.
    """
    if min_filme < 1 or min_usuario < 1 or seed < 0:
        raise ValueError('Mínimos devem ser positivos e semente não negativa.')
    contagens = treino.groupby('userId').size()
    usuarios = sorted(int(u) for u in contagens[contagens >= min_usuario].index)
    disponivel = treino[treino.userId.isin(usuarios)].copy()
    if disponivel.empty:
        raise ValueError('Nenhum usuário atende ao mínimo de treino; avaliação não aplicável.')
    stats = ranking(disponivel, min_filme)
    modelo = Recomendador(filmes, stats, disponivel)
    referencias = selecionar_referencias(disponivel, seed)
    ordens = {metodo: stats.sort_values([coluna, 'contagem', 'movieId'],
        ascending=[False, False, True]).movieId.tolist()
        for metodo, coluna in (('popularidade', 'contagem'), ('nota_ponderada', 'nota_ponderada'))}
    generos = {int(f.movieId): set(f.genres.split('|')) - {'(no genres listed)'}
               for f in filmes.itertuples()}
    elegiveis = set(stats.movieId)
    vistos = {int(u): set(g.movieId) for u, g in disponivel.groupby('userId')}
    linhas = []
    for pos, u in enumerate(usuarios, 1):
        refs = referencias[u]
        for n in range(1, 6):
            apto = len(refs) >= n
            selecionadas = refs[:n] if apto else []
            candidatos = set()
            listas = {}
            if apto:
                uniao = set().union(*(generos[i] for i in selecionadas))
                candidatos = {int(i) for i in elegiveis-vistos[u] if generos[int(i)] & uniao}
                sessao = Sessao(assistidos=sorted(vistos[u]), referencias=selecionadas)
                listas['perfil'] = [f['movieId'] for f in modelo.recomendar_perfil(sessao, k=K)]
                for metodo, ordem in ordens.items():
                    listas[metodo] = [int(i) for i in ordem if i in candidatos][:K]
                for lista in listas.values():
                    if (not set(lista).issubset(candidatos) or set(lista) & vistos[u]
                            or len(lista) != len(set(lista)) or len(lista) != min(K, len(candidatos))):
                        raise AssertionError('Listas não respeitam o universo pareado e histórico.')
            fingerprint = hashlib.sha256(json.dumps(sorted(candidatos)).encode()).hexdigest() if apto else None
            for metodo in METODOS:
                lista = listas.get(metodo)
                linhas.append({'userId': u, 'n_referencias': n, 'metodo': metodo,
                    'elegivel': apto, 'coorte_fixa_5': len(refs) >= 5,
                    'referencias': json.dumps(selecionadas),
                    'recomendacoes': json.dumps(lista) if lista is not None else None,
                    'n_candidatos': len(candidatos) if apto else None,
                    'hash_candidatos': fingerprint,
                    'n_recomendacoes': len(lista) if lista is not None else None,
                    'motivo': 'elegivel' if apto else 'referencias_positivas_insuficientes'})
        if progresso and (pos % 50 == 0 or pos == len(usuarios)):
            progresso(f'{pos}/{len(usuarios)} usuários processados')
    return pd.DataFrame(linhas), stats, {
        'usuarios_treino': int(treino.userId.nunique()),
        'usuarios_minimo_treino': len(usuarios),
        'usuarios_excluidos_minimo_treino': int(treino.userId.nunique())-len(usuarios),
        'filmes_elegiveis_treino': len(stats),
        'usuarios_coorte_fixa_5': sum(len(v) >= 5 for v in referencias.values()),
        'usuarios_referencias_suficientes': {str(n): sum(len(v) >= n for v in referencias.values()) for n in range(1, 6)},
    }


def pontuar_listas(listas, teste):
    """Teste entra somente depois de todas as listas terem sido produzidas."""
    positivos = {int(u): set(g.loc[g.rating >= RELEVANTE, 'movieId'])
                 for u, g in teste.groupby('userId')}
    detalhes = listas.copy()
    for coluna in METRICAS:
        detalhes[coluna] = np.nan
    detalhes['relevantes_teste'] = detalhes.userId.map(lambda u: len(positivos.get(u, set())))
    detalhes['avaliado_metricas'] = detalhes.elegivel & detalhes.relevantes_teste.gt(0)
    for indice, linha in detalhes[detalhes.elegivel].iterrows():
        valores = metricas_top10(json.loads(linha.recomendacoes), positivos.get(linha.userId, set()))
        for coluna, valor in valores.items():
            if valor is not None:
                detalhes.at[indice, coluna] = valor
    resumo = []
    for coorte in ('por_n_disponivel', 'fixa_5'):
        base = detalhes if coorte == 'por_n_disponivel' else detalhes[detalhes.coorte_fixa_5]
        for n in range(1, 6):
            for metodo in METODOS:
                grupo = base[(base.n_referencias == n) & (base.metodo == metodo)]
                aptos = grupo[grupo.elegivel]
                avaliados = aptos[aptos.avaliado_metricas]
                resumo.append({'coorte': coorte, 'n_referencias': n, 'metodo': metodo,
                    'usuarios_base': len(grupo), 'usuarios_elegiveis': len(aptos),
                    'usuarios_referencias_insuficientes': len(grupo)-len(aptos),
                    'usuarios_avaliados': len(avaliados),
                    'usuarios_sem_positivos_teste': len(aptos)-len(avaliados),
                    'usuarios_sem_candidatos': int(aptos.n_candidatos.eq(0).sum()),
                    'media_recomendacoes': float(aptos.n_recomendacoes.mean()) if len(aptos) else None,
                    'cobertura_usuarios': float(aptos.n_recomendacoes.gt(0).mean()) if len(aptos) else None,
                    **{c: float(avaliados[c].mean()) if len(avaliados) else None for c in METRICAS}})
    return detalhes, pd.DataFrame(resumo)


def avaliar_perfil(treino, teste, filmes, **parametros):
    _validar_pares(treino, teste, filmes)
    listas, stats, auditoria = gerar_listas(treino, filmes, **parametros)
    detalhes, resumo = pontuar_listas(listas, teste)
    return detalhes, resumo, auditoria, stats


def _json(caminho, dados):
    with caminho.open('x', encoding='utf-8') as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2, allow_nan=False)


def executar(resultados, dados, saida, *, seed=42):
    """Lê entradas existentes; não prepara, baixa ou sobrescreve resultados."""
    resultados, dados, saida = map(Path, (resultados, dados, saida))
    for entrada in (resultados.resolve(), dados.resolve()):
        if saida.resolve() == entrada or entrada in saida.resolve().parents:
            raise ValueError('Saída experimental deve ficar fora dos diretórios de entrada.')
    arquivos_entrada = {f'resultados/{n}': resultados/n for n in ARQUIVOS}
    arquivos_entrada.update({f'dados/{n}': dados/n for n in ('ratings.csv', 'movies.csv', 'README.txt')})
    if (resultados/MANIFESTO).exists(): arquivos_entrada['resultados/manifesto.json'] = resultados/MANIFESTO
    antes = {nome: assinatura(p) for nome, p in arquivos_entrada.items()}
    validacao = validar_resultados(resultados)
    relatorio = json.loads((resultados/'relatorio.json').read_text())
    treino, teste, filmes = [pd.read_csv(resultados/n) for n in ('treino.csv', 'teste.csv', 'filmes.csv')]
    # Reconstituição em memória apenas para CONFERIR a divisão salva; as listas
    # usarão treino.csv/teste.csv existentes, não uma divisão nova.
    bruto, catalogo = pd.read_csv(dados/'ratings.csv'), pd.read_csv(dados/'movies.csv')
    limpo, catalogo, _ = limpar(bruto, catalogo)
    tr, te = dividir(limpo, fracao=relatorio['fracao_teste'], seed=relatorio['seed'])
    contagem = tr.groupby('userId').size()
    usuarios = set(contagem[contagem >= relatorio['min_avaliacoes_usuario_treino']].index)
    tr, te = tr[tr.userId.isin(usuarios)], te[te.userId.isin(usuarios)]
    for esperado, salvo in ((tr, treino), (te, teste)):
        colunas = list(esperado.columns)
        pd.testing.assert_frame_equal(esperado.sort_values(['userId','movieId']).reset_index(drop=True),
            salvo[colunas].sort_values(['userId','movieId']).reset_index(drop=True), check_dtype=False)
    pd.testing.assert_frame_equal(catalogo.reset_index(drop=True), filmes.reset_index(drop=True), check_dtype=False)
    stats_esperadas = ranking(treino, relatorio['min_avaliacoes_filme_treino'])
    pd.testing.assert_frame_equal(stats_esperadas, pd.read_csv(resultados/'ranking_treino.csv'),
                                 check_dtype=False, rtol=1e-12, atol=1e-12)
    execucao = iniciar_identificacao(saida)
    detalhes, resumo, auditoria, stats = avaliar_perfil(treino, teste, filmes,
        min_filme=relatorio['min_avaliacoes_filme_treino'],
        min_usuario=relatorio['min_avaliacoes_usuario_treino'], seed=seed,
        progresso=lambda s: print(s, flush=True))
    _, baselines = avaliar(treino, teste, stats)
    if baselines.get('metricas') != relatorio.get('metricas'):
        raise ValueError('Baselines recalculados divergem do relatório original.')
    auditoria.update({'divisao_salva_confere_com_origem': True,
        'estatisticas_recalculadas_somente_treino': True,
        'validacao_entrada': {k: v for k, v in validacao.items() if k != 'manifesto'},
        'baselines_globais_recalculados': baselines})
    detalhes.to_csv(saida/'avaliacao_por_usuario.csv', index=False)
    resumo.to_csv(saida/'resumo.csv', index=False)
    # DataFrame converte None em NaN; o JSON representa ausências com null.
    registros = json.loads(resumo.to_json(orient='records', double_precision=15))
    _json(saida/'resumo.json', registros)
    _json(saida/'auditoria.json', auditoria)
    if antes != {nome: assinatura(p) for nome, p in arquivos_entrada.items()}:
        raise RuntimeError('Entradas foram alteradas durante a execução.')
    versao = '2018-09-26' if 'generated on September 26, 2018.' in (dados/'README.txt').read_text() else None
    nomes = ('avaliacao_por_usuario.csv', 'resumo.csv', 'resumo.json', 'auditoria.json')
    _json(saida/MANIFESTO, {'esquema': ESQUEMA, 'versao_esquema': 1,
        'execucao_id': execucao, 'criado_em': datetime.now(timezone.utc).isoformat(),
        'dataset': {'nome': 'MovieLens Latest Small', 'versao': versao, 'fonte': 'arquivos locais verificados'},
        'parametros': {'seed_referencias': seed, 'seed_divisao_preservada': relatorio['seed'],
            'fracao_teste': relatorio['fracao_teste'], 'min_filme': relatorio['min_avaliacoes_filme_treino'],
            'min_usuario': relatorio['min_avaliacoes_usuario_treino'], 'relevante': RELEVANTE, 'k': K,
            'referencias': [1,2,3,4,5], 'selecao': 'amostra aninhada uniforme dos positivos do treino',
            'universo': 'suporte no treino - vistos; interseção de gêneros com referências > 0',
            'preferencias_genero': 'vazias; sem refinamento conversacional'},
        'entradas': antes,
        'codigo': {n: assinatura(ROOT/n) for n in ('avaliacao_perfil.py','recomendador.py','conversa.py','identidades.py')},
        'ambiente': {'python': platform.python_version(), **{n: importlib.metadata.version(n) for n in ('numpy','pandas','scipy')}},
        'arquivos': {n: assinatura(saida/n) for n in nomes}})
    (saida/PENDENTE).unlink()
    print(resumo.to_string(index=False), flush=True)
    return detalhes, resumo, auditoria


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resultados', type=Path, default=ROOT/'resultados')
    parser.add_argument('--dados', type=Path, default=ROOT/'dados/ml-latest-small')
    parser.add_argument('--saida', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    executar(args.resultados, args.dados, args.saida, seed=args.seed)
