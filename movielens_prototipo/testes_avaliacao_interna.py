"""Integração experimental com dados sintéticos e sentinelas de acesso."""
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import avaliacao_interna as a
import divisao_interna as d
from artefatos_resultados import assinatura
from avaliacao_perfil import metricas_top10


class AvaliacaoInterna(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        entrada = self.raiz/'entrada'
        entrada.mkdir()
        self.treino = entrada/'treino.csv'
        t = pd.DataFrame([(u,i,4.5,1000+i) for u in range(1,13)
            for i in range(1,31) if i%3!=u%3],columns=d.COLUNAS)
        _,val = d.dividir_interno(t)
        pares = set(zip(val.loc[val.userId==3,'userId'],val.loc[val.userId==3,'movieId']))
        t.loc[[p in pares for p in zip(t.userId,t.movieId)],'rating'] = 1.
        t.to_csv(self.treino,index=False)
        self.filmes = entrada/'filmes.csv'
        pd.DataFrame({'movieId':range(1,31),'title':[f'Filme {i} (2000)' for i in range(1,31)],
            'genres':['Drama|Action' if i%2 else 'Drama' for i in range(1,31)]}).to_csv(self.filmes,index=False)
        (entrada/'teste.csv').write_text('SENTINELA PROIBIDA: teste original')
        (entrada/'ranking_treino.csv').write_text('SENTINELA PROIBIDA: ranking completo')
        proc = self.raiz/'procedencia'
        proc.mkdir()
        self.procedencia = proc/'manifesto.json'
        m = {'esquema':'cinematch.experimento.perfil','versao_esquema':1,'execucao_id':'sintetica',
            'dataset':{'nome':'MovieLens Latest Small','versao':'2018-09-26','fonte':'sintética'},
            'parametros':{'seed_divisao_preservada':42,'fracao_teste':.2},
            'entradas':{'resultados/treino.csv':assinatura(self.treino),'resultados/filmes.csv':assinatura(self.filmes)}}
        self.procedencia.write_text(json.dumps(m))
        self.divisao = self.raiz/'divisao'
        d.executar(self.treino,self.procedencia,self.divisao)
        self.saida = self.raiz/'avaliacao'

    def executar(self,saida=None):
        return a.executar(self.divisao,self.treino,self.procedencia,self.filmes,saida or self.saida)

    def test_ordem_acessos_e_sentinelas(self):
        ler = pd.read_csv
        def protegido(caminho,*args,**kw):
            nome = Path(caminho).name
            self.assertNotIn(nome,('treino.csv','teste.csv','ranking_treino.csv','ratings.csv','matriz_treino.npz'))
            if nome=='validacao.csv':
                self.assertTrue((self.saida/'listas.csv').exists())
                listas = ler(self.saida/'listas.csv')
                self.assertEqual(len(listas),12*5*3)
            return ler(caminho,*args,**kw)
        with patch('pandas.read_csv',side_effect=protegido):
            _,resumo,audit = self.executar()
        self.assertTrue(audit['listas_geradas_antes_de_ler_notas_validacao'])
        self.assertEqual(audit['usuarios_coorte_fixa'],12)
        self.assertEqual(audit['usuarios_avaliaveis'],11)
        self.assertEqual(audit['usuarios_sem_positivos_validacao'],[3])
        self.assertTrue(resumo.usuarios_avaliados.eq(11).all())

    def test_reprodutibilidade(self):
        x,r,_ = self.executar()
        y,s,_ = self.executar(self.raiz/'outra')
        pd.testing.assert_frame_equal(x,y)
        pd.testing.assert_frame_equal(r,s)

    def test_referencias_historico_candidatos_e_estatisticas(self):
        det,_,_ = self.executar()
        dev = pd.read_csv(self.divisao/'desenvolvimento.csv')
        filmes = pd.read_csv(self.filmes)
        stats = pd.read_csv(self.saida/'estatisticas_desenvolvimento.csv')
        generos = {f.movieId:set(f.genres.split('|')) for f in filmes.itertuples()}
        for f in stats.itertuples():
            notas = dev.loc[dev.movieId==f.movieId,'rating']
            self.assertEqual(len(notas),f.contagem)
            self.assertAlmostEqual((notas.sum()+5*dev.rating.mean())/(len(notas)+5),f.nota_ponderada)
        for u,g in det.groupby('userId'):
            vistos = set(dev.loc[dev.userId==u,'movieId'])
            positivos = set(dev.loc[(dev.userId==u)&(dev.rating>=4),'movieId'])
            cinco = json.loads(g.loc[g.n_referencias==5].iloc[0].referencias)
            for n,grupo in g.groupby('n_referencias'):
                refs = json.loads(grupo.iloc[0].referencias)
                self.assertEqual(refs,cinco[:n])
                self.assertTrue(set(refs)<=positivos)
                uniao = set().union(*(generos[i] for i in refs))
                c = {i for i in set(stats.movieId)-vistos if generos[i]&uniao}
                self.assertEqual(set(grupo.metodo),set(a.METODOS))
                self.assertEqual(grupo.hash_candidatos.nunique(),1)
                self.assertTrue(grupo.n_candidatos.eq(len(c)).all())
                for lista in grupo.recomendacoes.map(json.loads):
                    self.assertFalse(set(lista)&vistos)
                    self.assertTrue(set(lista)<=c)
                    self.assertEqual(len(lista),min(10,len(c)))

    def test_notas_validacao_nao_influenciam_listas(self):
        ctx = d.carregar_desenvolvimento(self.divisao)
        catalogo = pd.read_csv(self.filmes)
        listas,stats,_ = a.gerar_coorte(ctx,catalogo)
        val = pd.read_csv(self.divisao/'validacao.csv')
        x,_,_ = a.pontuar_coorte(listas,val)
        val['rating'] = .5
        y,resumo,_ = a.pontuar_coorte(listas,val)
        self.assertEqual(x.recomendacoes.tolist(),y.recomendacoes.tolist())
        self.assertEqual(x.referencias.tolist(),y.referencias.tolist())
        self.assertTrue(resumo[list(a.METRICAS)].isna().all().all())
        self.assertTrue(resumo.usuarios_avaliados.eq(0).all())
        novamente,stats2,_ = a.gerar_coorte(ctx,catalogo)
        pd.testing.assert_frame_equal(listas,novamente)
        pd.testing.assert_frame_equal(stats,stats2)

    def test_metricas_calculo_manual_e_sem_positivos(self):
        m = metricas_top10([9,2],{2,3})
        self.assertAlmostEqual(m['precision_at_10'],.1)
        self.assertAlmostEqual(m['recall_at_10'],.5)
        self.assertAlmostEqual(m['ndcg_at_10'],(1/math.log2(3))/(1+1/math.log2(3)))
        self.assertTrue(all(v is None for v in metricas_top10([2],set()).values()))
        self.assertTrue(all(v==0 for v in metricas_top10([],{2}).values()))

    def test_agregacao_manual_coorte_fixa(self):
        linhas = []
        for u in (1,2):
            for n in range(1,6):
                for metodo in a.METODOS:
                    linhas.append({'userId':u,'n_referencias':n,'metodo':metodo,
                        'elegivel':True,'coorte_fixa_5':True,'recomendacoes':'[9, 2]',
                        'n_candidatos':20,'n_recomendacoes':2})
        val = pd.DataFrame({'userId':[1,1,2],'movieId':[2,3,8],'rating':[4.,5.,1.]})
        det,r,usuarios = a.pontuar_coorte(pd.DataFrame(linhas),val)
        self.assertEqual(len(r),15)
        self.assertTrue(r.usuarios_avaliados.eq(1).all())
        self.assertTrue(r.media_recomendacoes.eq(2).all())
        self.assertTrue(r.cobertura_usuarios.eq(1).all())
        for f in r.itertuples():
            self.assertAlmostEqual(f.precision_at_10,.1)
            self.assertAlmostEqual(f.recall_at_10,.5)
            self.assertAlmostEqual(f.ndcg_at_10,(1/math.log2(3))/(1+1/math.log2(3)))
        self.assertTrue(det.loc[det.userId==2,list(a.METRICAS)].isna().all().all())

    def test_restringir_coorte_nao_restringe_estatisticas(self):
        ctx = d.carregar_desenvolvimento(self.divisao)
        dev = ctx.avaliacoes()
        # Usuário fora da coorte ainda contribui para estatísticas globais do desenvolvimento.
        linhas = dev.index[dev.userId==12]
        dev.loc[linhas,'rating'] = .5
        dev.loc[linhas[:4],'rating'] = 4.
        class ContextoSintetico:
            def avaliacoes(self): return dev.copy()
        listas,stats,_ = a.gerar_coorte(ContextoSintetico(),pd.read_csv(self.filmes))
        self.assertNotIn(12,set(listas.userId))
        for f in stats.itertuples():
            notas = dev.loc[dev.movieId==f.movieId,'rating']
            self.assertEqual(f.contagem,len(notas))
            self.assertAlmostEqual(f.nota_ponderada,(notas.sum()+5*dev.rating.mean())/(len(notas)+5))

    def test_hashes_saida_e_nao_sobrescrita(self):
        self.executar()
        a.validar_saida(self.saida)
        with self.assertRaises(FileExistsError): self.executar()
        with (self.saida/'resumo.csv').open('a') as f: f.write('corrupção')
        with self.assertRaises(ValueError): a.validar_saida(self.saida)

    def test_procedencia_corrompida_antes_de_gerar(self):
        with self.treino.open('a') as f: f.write('999,999,5,1000\n')
        with patch('avaliacao_interna.gerar_coorte',side_effect=AssertionError('não deveria gerar')):
            with self.assertRaises(ValueError): self.executar()
        self.assertFalse(self.saida.exists())

    def test_validacao_corrompida_detectada_sem_gerar(self):
        with (self.divisao/'validacao.csv').open('a') as f: f.write('999,999,5,1000\n')
        with patch('avaliacao_interna.gerar_coorte',side_effect=AssertionError('não deveria gerar')):
            with self.assertRaises(ValueError): self.executar()

    def test_usuarios_sem_positivos_nao_recebem_zero_artificial(self):
        det,resumo,_ = self.executar()
        sem = det[det.userId==3]
        self.assertTrue(sem[list(a.METRICAS)].isna().all().all())
        self.assertTrue(resumo.usuarios_sem_positivos_validacao.eq(1).all())
        self.assertTrue(resumo.usuarios_elegiveis.eq(12).all())


if __name__=='__main__':
    unittest.main()
