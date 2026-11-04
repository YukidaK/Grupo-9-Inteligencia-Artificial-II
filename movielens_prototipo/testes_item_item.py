"""Similaridades manuais e integração isolada; nunca usa dados reais."""
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

from item_item_experimental import ItemItem
import experimento_item_item as e
import testes_avaliacao_interna as anterior


def tabela(linhas):
    return pd.DataFrame([(u,i,r,1000) for u,i,r in linhas],columns=['userId','movieId','rating','timestamp'])


class SimilaridadesItemItem(unittest.TestCase):
    def setUp(self):
        self.dev = tabela([(1,1,5),(1,2,4),(1,3,1),(2,1,1),(2,2,2),(2,3,5),(3,1,4),(3,4,2)])

    def modelo(self,dev=None,**kw):
        return ItemItem(self.dev if dev is None else dev,min_filme=2,min_comum=2,**kw)

    def test_cosseno_ajustado_e_shrinkage_manualmente(self):
        m = self.modelo()
        a,b = m.indice[1],m.indice[2]
        self.assertAlmostEqual(m.similaridades[a,b],1/6,places=12)
        self.assertEqual(m.suportes[a,b],2)
        self.assertEqual(m.similaridades[a,m.indice[3]],0)
        self.assertEqual(m.similaridades[a,a],0)
        self.assertAlmostEqual(m.similaridades[a,b],m.similaridades[b,a])

    def test_normas_apenas_coavaliadores_e_outro_historico_alvo(self):
        m = self.modelo()
        mudou = self.dev.copy()
        mudou.loc[(mudou.userId==3)&(mudou.movieId==4),'rating'] = 5
        novo = self.modelo(mudou)
        x,_ = m.recomendar([1],[2],[1,4])
        y,_ = novo.recomendar([1],[2],[1,4])
        self.assertEqual(x,y)
        self.assertAlmostEqual(x[0]['pontuacao'],1/6)

    def test_filmes_e_pares_sem_suporte(self):
        m = self.modelo()
        self.assertNotIn(4,m.indice)
        self.assertEqual(m.recomendar([4],[1,2,3],[]),([],0))
        n = ItemItem(self.dev,min_filme=2,min_comum=3)
        self.assertEqual(n.similaridades.nnz,0)
        self.assertEqual(n.recomendar([1],[2],[]),([],0))

    def test_observacao_de_desvio_zero_conta_no_suporte(self):
        dev = tabela([(1,1,3),(1,2,3),(1,3,3),(2,1,5),(2,2,4),(2,3,.5)])
        m = self.modelo(dev)
        self.assertEqual(m.suportes[m.indice[1],m.indice[2]],2)
        self.assertAlmostEqual(m.similaridades[m.indice[1],m.indice[2]],1/6)

    def test_norma_zero_nao_vira_rejeicao_nem_fallback(self):
        m = self.modelo(self.dev.assign(rating=3.))
        self.assertEqual(m.similaridades.nnz,0)
        self.assertEqual(m.recomendar([1],[2,3],[]),([],0))

    def test_historico_e_referencias_sempre_excluidos(self):
        m = self.modelo()
        self.assertEqual(m.recomendar([1],[1,2,3],[2]),([],0))

    def test_uma_a_cinco_referencias_sem_usar_outro_historico_como_perfil(self):
        m = self.modelo()
        for n in range(1,6):
            rec,cont = m.recomendar([1,3,4,5,6][:n],[2],[])
            self.assertEqual(cont,1)
            self.assertAlmostEqual(rec[0]['pontuacao'],1/(6*n))

    def test_desempate_numerico_determinismo_e_blocos(self):
        dev = tabela([(u,i,r) for u,notas in ((1,{1:5,2:4,4:4,3:1}),(2,{1:1,2:2,4:2,3:5})) for i,r in notas.items()])
        a = self.modelo(dev,bloco=1)
        b = self.modelo(dev.sample(frac=1,random_state=9),bloco=128)
        x,_ = a.recomendar([1],{4,2},[])
        y,_ = b.recomendar([1],{2,4},[])
        self.assertEqual(x,y)
        self.assertEqual([i['movieId'] for i in x],[2,4])


class IntegracaoItemItem(unittest.TestCase):
    setUp = anterior.AvaliacaoInterna.setUp

    def executar(self):
        controles = self.raiz/'controles'
        anterior.a.executar(self.divisao,self.treino,self.procedencia,self.filmes,controles)
        registro = self.raiz/'registro'
        registro.mkdir()
        config = registro/'config.json'
        config.write_text(json.dumps(dict(min_filme=5,min_coavaliadores=5,shrinkage=10,
            bloco_itens=128,seed_referencias=201,k=10)))
        saida = self.raiz/'cf'
        ler = pd.read_csv
        def protegido(caminho,*args,**kw):
            nome = Path(caminho).name
            self.assertNotIn(nome,('treino.csv','teste.csv','ranking_treino.csv','ratings.csv'))
            if nome=='validacao.csv':
                self.assertTrue((saida/'listas.csv').exists())
            return ler(caminho,*args,**kw)
        with patch('pandas.read_csv',side_effect=protegido):
            resultado = e.executar(self.divisao,self.treino,self.procedencia,self.filmes,
                controles,config,saida)
        return resultado,saida

    def test_isolamento_coorte_candidatos_e_integridade(self):
        (det,resumo,audit),saida = self.executar()
        self.assertEqual(set(det.metodo),{'popularidade','nota_ponderada','perfil','item_item'})
        for _,g in det.groupby(['userId','n_referencias']):
            self.assertEqual(len(g),4)
            self.assertEqual(g.hash_candidatos.nunique(),1)
            self.assertEqual(g.n_candidatos.nunique(),1)
        self.assertTrue(resumo.usuarios_avaliados.eq(11).all())
        self.assertTrue(audit['controles_conferem_com_avaliacao_anterior'])
        from artefatos_resultados import assinatura
        m = json.loads((saida/'manifesto.json').read_text())
        self.assertTrue(all(assinatura(saida/n)==s for n,s in m['arquivos'].items()))

    def test_sem_relacoes_sem_fallback_com_zeros_justificados(self):
        (det,r,_),_ = self.executar()
        cf = r[r.metodo=='item_item']
        # Desenvolvimento desta fixture é constante (4,5), portanto normas zero.
        self.assertTrue(cf.cobertura_usuarios.eq(0).all())
        self.assertTrue(cf.media_recomendacoes.eq(0).all())
        self.assertTrue(cf.usuarios_sem_candidatos_pontuaveis.eq(12).all())
        self.assertTrue(cf.precision_at_10.eq(0).all())
        sem = det[(det.metodo=='item_item')&(det.userId==3)]
        self.assertTrue(sem[['precision_at_10','recall_at_10','ndcg_at_10']].isna().all().all())


if __name__=='__main__':
    unittest.main()
