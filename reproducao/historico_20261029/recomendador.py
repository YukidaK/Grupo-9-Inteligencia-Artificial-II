"""Preparação, avaliação e recomendação. Python >=3.10; sem API externa."""
from pathlib import Path
import argparse
import json
import re
import unicodedata
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, save_npz

from carregamento_movielens import URL_MOVIELENS as URL, carregar_movielens
from artefatos_resultados import (
    MANIFESTO, PENDENTE, ErroArtefatos, identidade_dataset,
    iniciar_identificacao, gravar_manifesto, validar_resultados,
)
from identidades import conteudo_movielens, usuario_movielens

ROOT = Path(__file__).resolve().parent
SEED = 42

def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto.lower()) if not unicodedata.combining(c))

# Vocabulário transparente: não é um modelo de linguagem nem entende toda frase.
VOCAB = {
 'Action': ['acao', 'action', 'luta', 'lutas', 'super heroi', 'super herois'],
 'Adventure': ['aventura', 'adventure', 'exploracao'],
 'Animation': ['animacao', 'animation', 'anime', 'desenho'],
 'Children': ['infantil', 'criancas', 'children'],
 'Comedy': ['comedia', 'comedy', 'engracado', 'humor'],
 'Crime': ['crime', 'crimes', 'policial', 'investigacao', 'detetive'],
 'Documentary': ['documentario', 'documentary'],
 'Drama': ['drama', 'dramatico'],
 'Fantasy': ['fantasia', 'fantasy', 'magia', 'magico', 'sobrenatural'],
 'Film-Noir': ['noir'],
 'Horror': ['terror', 'horror', 'assustador', 'medo'],
 'Musical': ['musical', 'musicais'],
 'Mystery': ['misterio', 'mystery', 'enigma', 'investigacao'],
 'Romance': ['romance', 'romantico', 'amor'],
 'Sci-Fi': ['ficcao cientifica', 'sci fi', 'scifi', 'espaco', 'futurista', 'alienigena', 'robos'],
 'Thriller': ['suspense', 'thriller', 'tensao'],
 'War': ['guerra', 'war'],
 'Western': ['faroeste', 'western', 'velho oeste'],
}

def interpretar(texto):
    t = re.sub(r'[^a-z0-9 ]', ' ', normalizar(texto))
    t = re.sub(r'\s+', ' ', t).strip()
    return [g for g, palavras in VOCAB.items() if any(re.search(r'\b' + re.escape(p) + r'\b', t) for p in palavras)]

def carregar(pasta=None):
    """Entrada compatível; delega somente a leitura/aquisição do MovieLens."""
    return carregar_movielens(pasta, raiz=ROOT, url=URL)

def limpar(ratings, movies):
    r, m = ratings.copy(), movies.copy()
    for coluna in ['userId', 'movieId', 'rating', 'timestamp']:
        r[coluna] = pd.to_numeric(r[coluna], errors='coerce')
    m['movieId'] = pd.to_numeric(m['movieId'], errors='coerce')
    m = m.dropna(subset=['movieId', 'title']).drop_duplicates('movieId').copy()
    m = m[np.isfinite(m.movieId) & m.movieId.gt(0) & m.movieId.mod(1).eq(0)].copy()
    m['movieId'] = m.movieId.astype(int)
    m['genres'] = m.genres.fillna('(no genres listed)')
    validos = np.isfinite(r[['userId','movieId','rating','timestamp']]).all(axis=1)
    validos &= r.rating.between(.5, 5) & r.rating.mul(2).mod(1).eq(0)
    validos &= r.userId.gt(0) & r.userId.mod(1).eq(0) & r.movieId.mod(1).eq(0) & r.timestamp.ge(0)
    r = r[validos & r.movieId.isin(m.movieId)].copy()
    r[['userId', 'movieId', 'timestamp']] = r[['userId', 'movieId', 'timestamp']].astype('int64')
    r = r.sort_values(['timestamp','userId','movieId'], kind='stable').drop_duplicates(['userId', 'movieId'], keep='last')
    m['ano'] = pd.to_numeric(m.title.str.extract(r'\((\d{4})\)\s*$', expand=False), errors='coerce').astype('Int64')
    return r.reset_index(drop=True), m.reset_index(drop=True), {'ratings_entrada': len(ratings), 'ratings_limpos': len(r), 'ratings_removidos': len(ratings)-len(r), 'filmes_catalogo': len(m)}

def dividir(ratings, fracao=.2, seed=SEED):
    """Holdout aleatório por usuário; mantém pelo menos uma avaliação no treino."""
    if not 0 < fracao < 1:
        raise ValueError('A fração de teste precisa estar entre 0 e 1.')
    rng = np.random.default_rng(seed)
    teste_indices = []
    for _, grupo in ratings.sort_values(['userId','movieId']).groupby('userId', sort=True):
        n = min(len(grupo)-1, max(1, int(np.floor(len(grupo)*fracao)))) if len(grupo)>1 else 0
        if n:
            teste_indices.extend(rng.choice(grupo.index.to_numpy(), n, replace=False))
    mask = ratings.index.isin(teste_indices)
    return ratings.loc[~mask].copy(), ratings.loc[mask].copy()

def ranking(treino, min_filme=5):
    if treino.empty:
        raise ValueError('Treino vazio; confira os filtros.')
    stats = treino.groupby('movieId').rating.agg(contagem='count', media='mean')
    # Média global e contagens calculadas exclusivamente no treino recebido.
    stats['nota_ponderada'] = (stats.contagem*stats.media + min_filme*treino.rating.mean()) / (stats.contagem+min_filme)
    return stats[stats.contagem >= min_filme].reset_index()

def avaliar(treino, teste, stats, k=10, relevante=4.):
    candidatos = set(stats.movieId)
    vistos = {u:set(g.movieId) for u,g in treino.groupby('userId')}
    linhas=[]
    for metodo, coluna in [('popularidade','contagem'), ('nota_ponderada','nota_ponderada')]:
        ordem = stats.sort_values([coluna,'contagem','movieId'], ascending=[False,False,True]).movieId.tolist()
        for u,g in teste.groupby('userId'):
            positivos=set(g.loc[g.rating>=relevante,'movieId'])
            if not positivos:
                continue
            rec=[i for i in ordem if i not in vistos.get(u,set())][:k]
            acertos=[int(i in positivos) for i in rec]
            dcg=sum(v/np.log2(j+2) for j,v in enumerate(acertos))
            ideal=sum(1/np.log2(j+2) for j in range(min(k,len(positivos))))
            linhas.append({'metodo':metodo,'userId':int(u),'precision_at_10':sum(acertos)/k,'recall_at_10':sum(acertos)/len(positivos),'ndcg_at_10':dcg/ideal,'relevantes_teste':len(positivos),'relevantes_elegiveis':len(positivos & candidatos)})
    df=pd.DataFrame(linhas)
    if df.empty:
        return df, {'aviso':'Não há usuários com notas relevantes no teste.'}
    metricas=df.groupby('metodo')[['precision_at_10','recall_at_10','ndcg_at_10']].mean().to_dict('index')
    base=df[df.metodo=='popularidade']
    return df, {'metricas':metricas,'usuarios_avaliados':len(base),'usuarios_sem_relevantes_excluidos':int(teste.userId.nunique()-len(base)),'relevantes_teste':int(base.relevantes_teste.sum()),'relevantes_elegiveis':int(base.relevantes_elegiveis.sum()),'protocolo':'Todos os itens elegíveis, sem amostragem de negativos. Itens relevantes fora do catálogo contam como não recuperados. Precision divide por 10 mesmo quando há menos resultados. Notas >=4 são relevantes.'}

def preparar(pasta=None, min_filme=5, min_usuario=5, *, diretorio_resultados=None,
             identificar=False, dataset=None):
    saida = Path(diretorio_resultados) if diretorio_resultados is not None else ROOT/'resultados'
    if identificar:
        identidade = identidade_dataset(dataset, URL)
        execucao = iniciar_identificacao(saida)
    else:
        if dataset is not None:
            raise ValueError('Metadados do dataset exigem identificar=True.')
        if (saida / MANIFESTO).exists() or (saida / PENDENTE).exists():
            raise ErroArtefatos('Não é permitido sobrescrever resultados identificados: ' + str(saida))
    bruto,m=carregar(pasta)
    r,m,auditoria=limpar(bruto,m)
    treino_bruto,teste=dividir(r)
    # Elegibilidade é decidida só pelo treino. Não se usa a nota do teste.
    bons=treino_bruto.groupby('userId').size()
    usuarios=set(bons[bons>=min_usuario].index)
    treino=treino_bruto[treino_bruto.userId.isin(usuarios)].copy()
    teste=teste[teste.userId.isin(usuarios)].copy()
    stats=ranking(treino,min_filme)
    saida.mkdir(parents=diretorio_resultados is not None, exist_ok=True)
    treino.to_csv(saida/'treino.csv',index=False); teste.to_csv(saida/'teste.csv',index=False)
    m.to_csv(saida/'filmes.csv',index=False); stats.to_csv(saida/'ranking_treino.csv',index=False)
    users=sorted(treino.userId.unique()); itens=sorted(treino.movieId.unique())
    um={v:i for i,v in enumerate(users)}; im={v:i for i,v in enumerate(itens)}
    matriz=csr_matrix((treino.rating.to_numpy(),(treino.userId.map(um),treino.movieId.map(im))),shape=(len(users),len(itens)))
    save_npz(saida/'matriz_treino.npz',matriz)
    (saida/'indices_matriz.json').write_text(json.dumps({'userIds':[int(x) for x in users],'movieIds':[int(x) for x in itens]}))
    detalhes,resumo=avaliar(treino,teste,stats)
    detalhes.to_csv(saida/'metricas_por_usuario.csv',index=False)
    resumo.update({'auditoria':auditoria,'seed':SEED,'fracao_teste':.2,'min_avaliacoes_filme_treino':min_filme,'min_avaliacoes_usuario_treino':min_usuario,'linhas_treino':len(treino),'linhas_teste':len(teste),'itens_elegiveis':len(stats),'matriz_shape':list(matriz.shape),'matriz_esparsidade':1-matriz.nnz/(matriz.shape[0]*matriz.shape[1]),'observacao':'Métricas avaliam baselines por histórico; não avaliam compreensão de texto. A matriz mantém todas as avaliações dos usuários elegíveis; o corte por filme define o catálogo dos baselines.'})
    (saida/'relatorio.json').write_text(json.dumps(resumo,ensure_ascii=False,indent=2))
    if identificar:
        origem = Path(pasta) if pasta else ROOT/'dados/ml-latest-small'
        parametros = {chave: resumo[chave] for chave in (
            'seed', 'fracao_teste', 'min_avaliacoes_filme_treino',
            'min_avaliacoes_usuario_treino')}
        parametros.update({'k': 10, 'relevante': 4.})
        gravar_manifesto(saida, execucao, identidade, parametros,
                         {nome: origem / nome for nome in ('ratings.csv', 'movies.csv')})
    print(json.dumps(resumo,ensure_ascii=False,indent=2))
    return treino,teste,m,stats

class Recomendador:
    def __init__(self, movies, stats, treino=None):
        self.filmes=movies.drop_duplicates('movieId').copy()
        if 'ano' not in self.filmes:
            self.filmes['ano'] = pd.to_numeric(self.filmes.title.str.extract(r'\((\d{4})\)\s*$', expand=False), errors='coerce').astype('Int64')
        self.catalogo=self.filmes.merge(stats.drop_duplicates('movieId'),on='movieId',how='inner')
        self.vistos={} if treino is None else {int(u):set(g.movieId) for u,g in treino.groupby('userId')}
        # Ponte interna para o domínio. As tabelas, IDs públicos e a ordenação
        # numérica MovieLens permanecem intactos; não há catálogo de múltiplas fontes.
        self.identidades_conteudo = {
            int(i): conteudo_movielens(i) for i in self.filmes.movieId
        }
        self.identidades_usuarios = {u: usuario_movielens(u) for u in self.vistos}
        self.vistos_identificados = {
            self.identidades_usuarios[u]: frozenset(conteudo_movielens(i) for i in vistos)
            for u, vistos in self.vistos.items()
        }

    def recomendar_perfil(self, sessao, k=10):
        """Perfil exclusivamente de catálogo + estatísticas do treino; sem acesso ao teste."""
        if not sessao.assistidos:
            return []
        def generos(valor):
            return set(valor.split('|')) - {'(no genres listed)'}
        referencias = [generos(f.genres) for f in self.filmes.itertuples()
                       if f.movieId in sessao.referencias and f.movieId not in sessao.rejeitados]
        # RF-01: histórico ou preferências não substituem uma referência ativa.
        if not 1 <= len(referencias) <= 5:
            return []
        resultados = []
        for f in self.catalogo.itertuples():
            if f.movieId in sessao.assistidos:
                continue
            gs = generos(f.genres)
            if gs & sessao.negativos:
                continue
            comuns_preferidos = gs & sessao.positivos
            if sessao.positivos and not comuns_preferidos:
                continue
            similaridade = sum(len(gs & r) / len(gs | r) if gs | r else 0 for r in referencias) / len(referencias) if referencias else 0
            if referencias and not sessao.positivos and similaridade == 0:
                continue
            preferencia = len(comuns_preferidos) / len(sessao.positivos) if sessao.positivos else 0
            score = .65 * similaridade + .25 * preferencia + .10 * float(f.nota_ponderada) / 5
            comuns = gs & set().union(*referencias) if referencias else set()
            partes = []
            if comuns:
                partes.append('Gêneros em comum com as referências: ' + ', '.join(sorted(comuns)))
            if comuns_preferidos:
                partes.append('Preferências atendidas: ' + ', '.join(sorted(comuns_preferidos)))
            partes.append('A nota ponderada do treino também compõe a pontuação')
            resultados.append({'movieId': int(f.movieId), 'titulo': f.title,
                'ano': int(f.ano) if pd.notna(f.ano) else None, 'generos': f.genres,
                'nota_media_treino': round(float(f.media), 2), 'avaliacoes_treino': int(f.contagem),
                'motivo': '. '.join(partes) + '.', 'pontuacao': score,
                '_nota': float(f.nota_ponderada)})
        resultados.sort(key=lambda f: (-f['pontuacao'], -f['_nota'], -f['avaliacoes_treino'], f['movieId']))
        for f in resultados:
            del f['_nota']
        return resultados[:max(1, min(10, int(k))) ]

    def recomendar(self,texto,k=10,user_id=None):
        k=max(1,min(10,int(k)))
        generos=interpretar(texto)
        c=self.catalogo.copy()
        if user_id is not None:
            c=c[~c.movieId.isin(self.vistos.get(int(user_id),set()))].copy()
        c['acertos']=c.genres.map(lambda s:len(set(s.split('|')) & set(generos)))
        if generos:
            c=c[c.acertos>0].copy()
        c=c.sort_values(['acertos','nota_ponderada','contagem','movieId'],ascending=[False,False,False,True]).head(k)
        resultados=[]
        for _,f in c.iterrows():
            comuns=[g for g in generos if g in f.genres.split('|')]
            resultados.append({'movieId':int(f.movieId),'titulo':f.title,'generos':f.genres,'nota_media_treino':round(float(f.media),2),'avaliacoes_treino':int(f.contagem),'motivo':('Gêneros relacionados ao pedido: '+', '.join(comuns)) if comuns else 'Sem gênero reconhecido: sugestão pela nota ponderada e número de avaliações.'})
        aviso='Protótipo por palavras-chave: não interpreta negações, enredos ou preferências complexas. Não informa disponibilidade em plataformas.'
        if not generos: aviso='Não reconheci gêneros no texto; usei o ranking geral. '+aviso
        return {'generos_identificados':generos,'aviso':aviso,'recomendacoes':resultados}

def carregar_modelo(diretorio_resultados=None, *, exigir_manifesto=False,
                    dataset_esperado=None, execucao_esperada=None):
    p = Path(diretorio_resultados) if diretorio_resultados is not None else ROOT/'resultados'
    validacao = validar_resultados(p, exigir_manifesto=exigir_manifesto,
                                  dataset_esperado=dataset_esperado,
                                  execucao_esperada=execucao_esperada)
    if not (p/'relatorio.json').exists():
        if diretorio_resultados is not None or validacao['integridade_verificada']:
            raise ErroArtefatos('Relatório ausente no diretório solicitado: ' + str(p))
        preparar()
    return Recomendador(pd.read_csv(p/'filmes.csv'),pd.read_csv(p/'ranking_treino.csv'),pd.read_csv(p/'treino.csv'))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--dados',help='Pasta contendo ratings.csv e movies.csv')
    parser.add_argument('--min-filme',type=int,default=5)
    parser.add_argument('--min-usuario',type=int,default=5)
    parser.add_argument('--resultados',help='Diretório opcional de resultados')
    parser.add_argument('--identificar',action='store_true',help='Gera manifesto em diretório vazio')
    args=parser.parse_args()
    if args.min_filme<1 or args.min_usuario<1: parser.error('Os mínimos precisam ser positivos.')
    preparar(args.dados,args.min_filme,args.min_usuario,
             diretorio_resultados=args.resultados, identificar=args.identificar)
