"""Testes do protocolo de avaliação, limpeza e contrato da API."""
import unittest
import pandas as pd
from recomendador import limpar, dividir, ranking, avaliar, carregar_modelo, interpretar
from pathlib import Path

class Testes(unittest.TestCase):
    def test_split_sem_intersecao_e_reprodutivel(self):
        r=pd.DataFrame([(u,i,4.,i) for u in range(1,4) for i in range(1,11)],columns=['userId','movieId','rating','timestamp'])
        a,b=dividir(r);a2,b2=dividir(r)
        self.assertEqual(len(a)+len(b),len(r));self.assertFalse(set(a.index)&set(b.index))
        pd.testing.assert_frame_equal(b,b2)
        self.assertTrue(a.groupby('userId').size().ge(1).all())
    def test_limpeza(self):
        m=pd.DataFrame({'movieId':[1],'title':['Filme (2000)'],'genres':['Drama']})
        r=pd.DataFrame([(1,1,3.,1),(1,1,4.,2),(2,1,6.,3),(3,99,4.,3),(4,1,4.,float('inf')),(float('inf'),1,4.,3)],columns=['userId','movieId','rating','timestamp'])
        r,_,_=limpar(r,m)
        self.assertEqual(len(r),1);self.assertEqual(r.iloc[0].rating,4.)
    def test_metricas_conhecidas_e_item_inelegivel(self):
        treino=pd.DataFrame({'userId':[1,2,2], 'movieId':[1,2,3], 'rating':[4.,5.,4.]})
        teste=pd.DataFrame({'userId':[1,1], 'movieId':[2,99], 'rating':[5.,5.]})
        stats=ranking(treino,1)
        _,r=avaliar(treino,teste,stats)
        self.assertAlmostEqual(r['metricas']['popularidade']['precision_at_10'],.1)
        self.assertAlmostEqual(r['metricas']['popularidade']['recall_at_10'],.5)
        self.assertEqual(r['relevantes_elegiveis'],1)
        import math
        self.assertAlmostEqual(r['metricas']['popularidade']['ndcg_at_10'], 1/(1+1/math.log2(3)))
    @unittest.skipUnless((Path(__file__).parent/'resultados/relatorio.json').exists(), 'Base real não preparada; execute recomendador.py para habilitar.')
    def test_recomendacao_real(self):
        modelo=carregar_modelo()
        d=modelo.recomendar('Quero suspense com investigação e mistério',100)
        self.assertEqual(len(d['recomendacoes']),10)
        self.assertIn('Mystery',d['generos_identificados'])
        self.assertEqual(len({x['movieId'] for x in d['recomendacoes']}),10)
        d=modelo.recomendar('aventura',user_id=1)
        self.assertFalse(set(x['movieId'] for x in d['recomendacoes']) & modelo.vistos[1])
        self.assertEqual(interpretar('ficção científica'),['Sci-Fi'])
        self.assertEqual(interpretar('ação'),['Action'])
def load_tests(loader, tests, pattern):
    import testes_conversa
    import testes_posteres
    import testes_autocomplete
    tests.addTests(loader.loadTestsFromModule(testes_conversa))
    tests.addTests(loader.loadTestsFromModule(testes_posteres))
    tests.addTests(loader.loadTestsFromModule(testes_autocomplete))
    return tests

if __name__=='__main__':unittest.main()
