"""Item–item isolado da aplicação; cosseno ajustado apenas nos coavaliadores."""
from time import perf_counter

import numpy as np
from scipy.sparse import csr_matrix

from divisao_interna import _tabela


def bytes_csr(matriz):
    return int(matriz.data.nbytes+matriz.indices.nbytes+matriz.indptr.nbytes)


class ItemItem:
    def __init__(self, desenvolvimento, *, min_filme=5, min_comum=5, shrinkage=10., bloco=128):
        inicio = perf_counter()
        if (any(type(x) is not int or x<1 for x in (min_filme,min_comum,bloco))
                or not np.isfinite(shrinkage) or shrinkage<0):
            raise ValueError('Parâmetros item–item inválidos.')
        dev = _tabela(desenvolvimento)
        self.parametros = dict(min_filme=min_filme,min_comum=min_comum,shrinkage=shrinkage,bloco=bloco)
        usuarios = sorted(dev.userId.unique())
        contagens = dev.groupby('movieId').size()
        self.movie_ids = [int(i) for i in sorted(contagens[contagens>=min_filme].index)]
        self.indice = {i:j for j,i in enumerate(self.movie_ids)}
        self.medias_usuarios = dev.groupby('userId').rating.mean().to_dict()
        elegivel = dev[dev.movieId.isin(self.movie_ids)]
        um = {u:j for j,u in enumerate(usuarios)}
        pos = (elegivel.userId.map(um).to_numpy(),elegivel.movieId.map(self.indice).to_numpy())
        shape = (len(usuarios),len(self.movie_ids))
        self.notas = csr_matrix((elegivel.rating.to_numpy(),pos),shape=shape)
        # A máscara conserva observações de desvio ZERO, distintas de ausência.
        observado = csr_matrix((np.ones(len(elegivel),dtype=np.float64),pos),shape=shape)
        centrado = csr_matrix(((elegivel.rating-elegivel.userId.map(self.medias_usuarios)).to_numpy(),pos),shape=shape)
        centrado.eliminate_zeros()
        quadrado = centrado.multiply(centrado).tocsr()
        linhas, colunas, valores, suportes = [],[],[],[]
        pares_suporte = pares_norma = 0
        maior_temporario = 0
        for inicio_bloco in range(0,len(self.movie_ids),bloco):
            fim = min(inicio_bloco+bloco,len(self.movie_ids))
            b = observado[:,inicio_bloco:fim]
            a = centrado[:,inicio_bloco:fim]
            q = quadrado[:,inicio_bloco:fim]
            comum = (b.T@observado).tocoo()
            produto = (a.T@centrado).tocsr()
            norma_i = (q.T@observado).tocsr()
            norma_j = (b.T@quadrado).tocsr()
            maior_temporario = max(maior_temporario,
                int(comum.data.nbytes+comum.row.nbytes+comum.col.nbytes)+
                sum(bytes_csr(m) for m in (produto,norma_i,norma_j)))
            r,c,n = comum.row,comum.col,comum.data
            mascara = (n>=min_comum)&(r+inicio_bloco!=c)
            r,c,n = r[mascara],c[mascara],n[mascara]
            pares_suporte += len(n)
            if not len(n):
                continue
            denominador = np.sqrt(norma_i[r,c].A1*norma_j[r,c].A1)
            valido = denominador>0
            pares_norma += int(valido.sum())
            if not valido.any():
                continue
            r,c,n,denominador = r[valido],c[valido],n[valido],denominador[valido]
            sim = np.clip(produto[r,c].A1/denominador,-1,1)*n/(n+shrinkage)
            positivo = sim>0
            linhas.extend((r[positivo]+inicio_bloco).tolist())
            colunas.extend(c[positivo].tolist())
            valores.extend(sim[positivo].tolist())
            suportes.extend(n[positivo].astype(int).tolist())
        shape_itens = (len(self.movie_ids),len(self.movie_ids))
        self.similaridades = csr_matrix((valores,(linhas,colunas)),shape=shape_itens,dtype=np.float64)
        self.suportes = csr_matrix((suportes,(linhas,colunas)),shape=shape_itens,dtype=np.int32)
        self.auditoria = {'usuarios':len(usuarios),'filmes_observados':int(dev.movieId.nunique()),
            'avaliacoes_desenvolvimento':len(dev),'filmes_elegiveis':len(self.movie_ids),
            'matriz_shape':list(self.notas.shape),'matriz_nnz':int(self.notas.nnz),
            'bytes_matriz_notas_csr':bytes_csr(self.notas),
            'bytes_similaridades_csr':bytes_csr(self.similaridades),'bytes_suportes_csr':bytes_csr(self.suportes),
            'maior_soma_bytes_produtos_bloco':maior_temporario,
            'pares_nao_direcionados_suporte_suficiente':pares_suporte//2,
            'pares_nao_direcionados_norma_valida':pares_norma//2,
            'relacoes_positivas_nao_direcionadas':int(self.similaridades.nnz//2),
            'relacoes_positivas_direcionadas':int(self.similaridades.nnz),
            'segundos_ajuste':perf_counter()-inicio}

    def recomendar(self, referencias, candidatos, historico, *, k=10):
        if (not 1<=len(referencias)<=5 or len(set(referencias))!=len(referencias)
                or type(k) is not int or not 1<=k<=10):
            raise ValueError('Informe de uma a cinco referências distintas e k entre um e dez.')
        refs = [self.indice[i] for i in referencias if i in self.indice]
        if not refs:
            return [],0
        # Vetor denso de tamanho número de itens, não matriz densa item × item.
        scores = np.asarray(self.similaridades[refs].sum(axis=0)).ravel()/len(referencias)
        possiveis = set(candidatos)-set(historico)-set(referencias)
        pontuados = [(int(i),float(scores[self.indice[i]])) for i in possiveis
                     if i in self.indice and scores[self.indice[i]]>0]
        pontuados.sort(key=lambda x:(-x[1],x[0]))
        return [{'movieId':i,'pontuacao':s} for i,s in pontuados[:k]],len(pontuados)
