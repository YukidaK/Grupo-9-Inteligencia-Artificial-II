"""Dados exclusivamente sintéticos e diretórios temporários."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from artefatos_resultados import assinatura
import divisao_interna as d


class DivisaoInterna(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.t = pd.DataFrame([(u,i,float(1+i%5),1000+i) for u in (1,2,3) for i in range(1,21)],columns=d.COLUNAS)
        self.origem = self.raiz/'entrada'
        self.origem.mkdir()
        self.t.to_csv(self.origem/'treino.csv',index=False)
        # Dados proibidos: jamais podem entrar nas partições.
        pd.DataFrame([(999,99999,5.,999)],columns=d.COLUNAS).to_csv(self.origem/'teste.csv',index=False)
        (self.raiz/'procedencia').mkdir()
        self.procedencia = self.raiz/'procedencia'/'manifesto.json'
        self.m = {'esquema':'cinematch.experimento.perfil','versao_esquema':1,'execucao_id':'sintetica',
            'dataset':{'nome':'MovieLens Latest Small','versao':'2018-09-26','fonte':'sintética'},
            'parametros':{'seed_divisao_preservada':42,'fracao_teste':.2},
            'entradas':{'resultados/treino.csv':assinatura(self.origem/'treino.csv')}}
        self.procedencia.write_text(json.dumps(self.m))
        self.saida = self.raiz/'saida'

    def gerar(self):
        return d.executar(self.origem/'treino.csv',self.procedencia,self.saida)

    def manifestar(self,m):
        (self.saida/'manifesto.json').write_text(json.dumps(m))

    def test_reprodutivel_inclusive_entrada_embaralhada(self):
        a,b = d.dividir_interno(self.t)
        c,e = d.dividir_interno(self.t.sample(frac=1,random_state=9))
        pd.testing.assert_frame_equal(a,c)
        pd.testing.assert_frame_equal(b,e)
        self.assertEqual(len(a),48)
        self.assertEqual(len(b),12)

    def test_disjuncao_conservacao_todos_os_valores(self):
        a,b = d.dividir_interno(self.t)
        self.assertFalse(set(zip(a.userId,a.movieId)) & set(zip(b.userId,b.movieId)))
        self.assertEqual(d.identidade_registros(pd.concat([a,b])),d.identidade_registros(self.t))
        b.loc[b.index[0],'rating'] = .5
        with self.assertRaises(d.ErroDivisao): d._auditar(self.t,a,b)

    def test_historicos_um_dois_e_quatro_sem_perda(self):
        t = pd.DataFrame([(u,i,4.,1) for u,n in ((1,1),(2,2),(3,4)) for i in range(1,n+1)],columns=d.COLUNAS)
        a,b = d.dividir_interno(t)
        self.assertEqual(a.groupby('userId').size().to_dict(),{1:1,2:1,3:3})
        self.assertEqual(b.groupby('userId').size().to_dict(),{2:1,3:1})
        self.assertEqual(len(a)+len(b),7)

    def test_so_unitarios_validacao_vazia_legitima(self):
        t = self.t.groupby('userId').head(1)
        t.to_csv(self.origem/'treino.csv',index=False)
        self.m['entradas']['resultados/treino.csv'] = assinatura(self.origem/'treino.csv')
        self.procedencia.write_text(json.dumps(self.m))
        self.gerar()
        self.assertEqual(d.validar_execucao(self.saida)['validacao']['avaliacoes'],0)

    def test_entradas_invalidas_rejeitadas(self):
        for seed,fracao in ((True,.2),(-1,.2),(1,0),(1,1),(1,True)):
            with self.subTest(seed=seed,fracao=fracao),self.assertRaises(d.ErroDivisao):
                d.dividir_interno(self.t,seed=seed,fracao=fracao)
        for t in (self.t.iloc[:0],pd.concat([self.t,self.t.iloc[:1]]),self.t.drop(columns='rating'),
                  self.t.assign(rating=6),self.t.assign(userId=1.5),self.t.assign(timestamp=float('inf'))):
            with self.assertRaises(d.ErroDivisao): d.dividir_interno(t)

    def test_runner_nao_le_teste_original_sentinela(self):
        ler = pd.read_csv
        def protegido(caminho,*args,**kw):
            self.assertNotEqual(Path(caminho).name,'teste.csv')
            return ler(caminho,*args,**kw)
        with patch('pandas.read_csv',side_effect=protegido):
            self.gerar()
        for n in ('desenvolvimento.csv','validacao.csv'):
            self.assertNotIn(99999,set(pd.read_csv(self.saida/n).movieId))

    def test_teste_renomeado_nao_passa_hash_de_treino(self):
        with self.assertRaises(d.ErroDivisao):
            d.verificar_origem(self.origem/'teste.csv',self.procedencia)
        (self.origem/'treino.csv').write_bytes((self.origem/'teste.csv').read_bytes())
        with self.assertRaises(d.ErroDivisao): self.gerar()

    def test_procedencia_incompativel(self):
        self.m['parametros']['seed_divisao_preservada'] = 43
        self.procedencia.write_text(json.dumps(self.m))
        with self.assertRaises(d.ErroDivisao): self.gerar()
        self.assertFalse(self.saida.exists())

    def test_sem_sobrescrita_e_sem_saida_na_origem(self):
        self.gerar()
        antes = assinatura(self.saida/'desenvolvimento.csv')
        with self.assertRaises(FileExistsError): self.gerar()
        self.assertEqual(assinatura(self.saida/'desenvolvimento.csv'),antes)
        with self.assertRaises(d.ErroDivisao):
            d.executar(self.origem/'treino.csv',self.procedencia,self.origem/'subpasta')

    def test_arquivos_ausentes_corrompidos_e_esquema(self):
        m = self.gerar()
        m['versao_esquema'] = 999
        self.manifestar(m)
        with self.assertRaises(d.ErroDivisao): d.carregar_desenvolvimento(self.saida)
        m['versao_esquema'] = 1
        self.manifestar(m)
        caminho = self.saida/'desenvolvimento.csv'
        original = caminho.read_bytes()
        caminho.write_bytes(original+b'corrompido')
        with self.assertRaises(d.ErroDivisao): d.carregar_desenvolvimento(self.saida)
        caminho.unlink()
        with self.assertRaises(d.ErroDivisao): d.carregar_desenvolvimento(self.saida)

    def test_execucao_e_manifesto_de_producao_rejeitados(self):
        m = self.gerar()
        with self.assertRaises(d.ErroDivisao):
            d.carregar_validacao(self.saida,execucao_esperada='outra')
        with self.assertRaises(d.ErroDivisao):
            d.carregar_validacao(self.saida,execucao_esperada=None)
        m['esquema'] = 'cinematch.movielens.resultados'
        self.manifestar(m)
        with self.assertRaises(d.ErroDivisao): d.carregar_desenvolvimento(self.saida)

    def test_preparacao_nao_acessa_validacao_nem_rankings_antigos(self):
        self.gerar()
        abrir = Path.open
        def protegido(caminho,*args,**kw):
            if caminho.name in ('validacao.csv','teste.csv','ranking_treino.csv','ratings.csv'):
                raise AssertionError('Acesso proibido à sentinela: '+caminho.name)
            return abrir(caminho,*args,**kw)
        with patch.object(Path,'open',protegido):
            ctx = d.carregar_desenvolvimento(self.saida)
            p = d.preparar_desenvolvimento(ctx,min_usuario=1,min_filme=1)
        dev = pd.read_csv(self.saida/'desenvolvimento.csv')
        self.assertEqual(p.estatisticas.contagem.sum(),len(dev))
        self.assertAlmostEqual((p.estatisticas.contagem*p.estatisticas.media).sum(),dev.rating.sum())
        for f in p.estatisticas.itertuples():
            notas = dev.loc[dev.movieId==f.movieId,'rating']
            esperado = (notas.sum()+dev.rating.mean())/(len(notas)+1)
            self.assertAlmostEqual(f.nota_ponderada,esperado,places=12)
        for u,refs in p.referencias.items():
            self.assertTrue(set(refs).issubset(set(dev.loc[(dev.userId==u)&(dev.rating>=4),'movieId'])))
            self.assertEqual(p.historicos[u],set(dev.loc[dev.userId==u,'movieId']))

    def test_alterar_notas_validacao_nao_muda_preparacao(self):
        self.gerar()
        ctx = d.carregar_desenvolvimento(self.saida)
        a = d.preparar_desenvolvimento(ctx,min_usuario=1,min_filme=1)
        val = pd.read_csv(self.saida/'validacao.csv')
        val['rating'] = .5
        val.to_csv(self.saida/'validacao.csv',index=False)
        b = d.preparar_desenvolvimento(d.carregar_desenvolvimento(self.saida),min_usuario=1,min_filme=1)
        pd.testing.assert_frame_equal(a.estatisticas,b.estatisticas)
        self.assertEqual(a.referencias,b.referencias)
        self.assertEqual(a.historicos,b.historicos)
        with self.assertRaises(d.ErroDivisao): d.validar_execucao(self.saida)

    def test_tabela_avulsa_e_validacao_rejeitadas_na_preparacao(self):
        m = self.gerar()
        val = d.carregar_validacao(self.saida,execucao_esperada=m['execucao_id'])
        with self.assertRaises(d.ErroDivisao): d.preparar_desenvolvimento(val)
        with self.assertRaises(d.ErroDivisao): d.DesenvolvimentoInterno(val,'falsa',None)

    def test_contexto_entrega_copia_e_preparacao_reprodutivel(self):
        self.gerar()
        ctx = d.carregar_desenvolvimento(self.saida)
        x = ctx.avaliacoes()
        x['rating'] = .5
        a = d.preparar_desenvolvimento(ctx,min_usuario=1,min_filme=1)
        b = d.preparar_desenvolvimento(ctx,min_usuario=1,min_filme=1)
        pd.testing.assert_frame_equal(a.estatisticas,b.estatisticas)
        self.assertEqual(a.referencias,b.referencias)
        self.assertTrue(ctx.avaliacoes().rating.gt(.5).all())

    def test_sem_positivos_e_minimo_sem_fallback(self):
        self.t['rating'] = 1.
        self.t.to_csv(self.origem/'treino.csv',index=False)
        self.m['entradas']['resultados/treino.csv'] = assinatura(self.origem/'treino.csv')
        self.procedencia.write_text(json.dumps(self.m))
        m = self.gerar()
        self.assertEqual(m['contagens']['usuarios_sem_positivos_desenvolvimento'],3)
        p = d.preparar_desenvolvimento(d.carregar_desenvolvimento(self.saida),min_filme=1)
        self.assertTrue(all(not refs for refs in p.referencias.values()))
        with self.assertRaises(d.ErroDivisao):
            d.preparar_desenvolvimento(d.carregar_desenvolvimento(self.saida),min_usuario=999)

    def test_corrupcao_semantica_mesmo_recalculando_hash(self):
        m = self.gerar()
        val = pd.read_csv(self.saida/'validacao.csv')
        val.loc[0,'movieId'] = 99999
        val.to_csv(self.saida/'validacao.csv',index=False)
        m['arquivos']['validacao.csv'] = assinatura(self.saida/'validacao.csv')
        self.manifestar(m)
        with self.assertRaises(d.ErroDivisao): d.validar_execucao(self.saida)

    def test_particoes_trocadas_e_algoritmo_incompativel(self):
        m = self.gerar()
        a,b = [self.saida/n for n in ('desenvolvimento.csv','validacao.csv')]
        dev,val = a.read_bytes(),b.read_bytes()
        a.write_bytes(val)
        b.write_bytes(dev)
        m['arquivos']['desenvolvimento.csv'] = assinatura(a)
        m['arquivos']['validacao.csv'] = assinatura(b)
        self.manifestar(m)
        with self.assertRaises(d.ErroDivisao): d.validar_execucao(self.saida)
        m['parametros_divisao']['algoritmo'] = 'outro'
        self.manifestar(m)
        with self.assertRaises(d.ErroDivisao): d.carregar_desenvolvimento(self.saida)


if __name__ == '__main__':
    unittest.main()
