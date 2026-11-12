"""Busca local e seleção independente de requisições concorrentes."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
import pandas as pd
from busca import BuscaCatalogo
from conversa import Conversa, Sessao
from app import Handler
from testes_conversa import fixture


class Autocomplete(unittest.TestCase):
    def setUp(self):
        titulos = ['Élite (2000)', 'Toy Story (1995)', 'Toy Story 2 (1999)', 'A Toy Story Documentary (2010)', 'Toy Stony (2011)', 'Solaris (1972)', 'Solaris (2002)', 'City of Lost Children, The (Cité des enfants perdus, La) (1995)']
        self.filmes = pd.DataFrame([(i+1,t,'Drama') for i,t in enumerate(titulos)],columns=['movieId','title','genres'])
        self.busca = BuscaCatalogo(self.filmes)

    def test_acentos_caixa_parcial_e_alias_existente(self):
        self.assertEqual(self.busca.buscar('ELITE')[0]['movieId'], 1)
        self.assertEqual(self.busca.buscar('élite')[0]['movieId'], 1)
        self.assertEqual(self.busca.buscar('CITE DES ENFANTS')[0]['movieId'], 8)
        self.assertEqual(self.busca.buscar('the city of lost')[0]['movieId'], 8)

    def test_prioridade_exato_inicio_parte_aproximado(self):
        filmes = self.busca.buscar('Toy Story')
        ids = [f['movieId'] for f in filmes]
        self.assertLess(ids.index(2),ids.index(3))
        self.assertLess(ids.index(3),ids.index(4))
        self.assertLess(ids.index(4),ids.index(5))
        self.assertEqual(filmes[ids.index(5)]['correspondencia'], 'aproximada')

    def test_erro_de_digitacao_conservador(self):
        self.assertIn(2, [f['movieId'] for f in self.busca.buscar('Toy Stroy')])
        # Títulos igualmente próximos continuam opções distintas, sem escolher por popularidade.
        self.assertIn(5, [f['movieId'] for f in self.busca.buscar('Toy Stroy')])
        self.assertEqual(self.busca.buscar('zzqvxzzz'), [])
        self.assertEqual(self.busca.buscar('x'), [])
        self.assertEqual(self.busca.buscar('!!'), [])

    def test_remakes_distintos_com_ano(self):
        self.assertEqual({f['movieId'] for f in self.busca.buscar('Solaris')}, {6,7})
        self.assertEqual([f['movieId'] for f in self.busca.buscar('Solaris (2002)')], [7])
        self.assertFalse(self.busca.buscar('Solaris (2001)'))

    def test_numero_no_titulo_nao_e_confundido_com_ano(self):
        m = pd.DataFrame([(9,'Blade Runner 2049 (2017)','Sci-Fi')],columns=['movieId','title','genres'])
        self.assertEqual(BuscaCatalogo(m).buscar('Blade Runner 2049')[0]['movieId'],9)

    def test_limite_e_ids_distintos(self):
        m = pd.DataFrame([(i,f'Filme parecido {i} (2000)','Drama') for i in range(1,20)],columns=['movieId','title','genres'])
        r = BuscaCatalogo(pd.concat([m,m])).buscar('Filme')
        self.assertEqual(len(r),8)
        self.assertEqual(len({f['movieId'] for f in r}),8)

    def test_confirmacao_preserva_ids_e_exige_no_maximo_cinco(self):
        conversa, sessao = Conversa(fixture()), Sessao()
        with self.assertRaises(ValueError):
            conversa.executar(sessao, {'acao':'confirmar_selecao','ids':[3,4,5,6,7,8]})
        self.assertEqual(sessao.assistidos, [])
        d = conversa.executar(sessao, {'acao':'confirmar_selecao','ids':[3,3,4,5]})
        self.assertEqual(sessao.referencias,[3,4,5])
        self.assertFalse(set(sessao.assistidos) & {r['movieId'] for r in d['recomendacoes']})
        with self.assertRaises(ValueError):
            conversa.executar(sessao, {'acao':'confirmar_selecao','ids':[999]})

    def test_endpoint_busca_sem_mutacao_da_sessao(self):
        class Transporte:
            def __init__(self):
                self.entrada=io.BytesIO(b'GET /api/filmes?q=Solaris HTTP/1.0\r\n\r\n')
                self.saida=bytearray()
            def makefile(self,*args):return self.entrada
            def sendall(self,dados):self.saida.extend(dados)
        sessao=Sessao(referencias=[3])
        with patch.object(Handler,'modelo',fixture()),patch.object(Handler,'sessoes',{'teste':(sessao,0)}):
            t=Transporte();Handler(t,('127.0.0.1',1234),object())
            dados=json.loads(bytes(t.saida).split(b'\r\n\r\n')[1])
            self.assertEqual(len(dados['sugestoes']),2)
            self.assertEqual(sessao.referencias,[3])
            self.assertEqual(len(Handler.sessoes),1)

    @unittest.skipUnless(shutil.which('node'), 'Node.js não disponível para os testes JavaScript; aplicação não depende dele.')
    def test_widget_javascript_teclado_e_concorrencia(self):
        p=Path(__file__).with_name('testes_autocomplete.cjs')
        r=subprocess.run([shutil.which('node'),'--test',str(p)],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stdout+'\n'+r.stderr)



class TitulosBrasileiros(unittest.TestCase):
    def setUp(self):
        from titulos_alternativos import validar_aliases
        self.filmes = pd.DataFrame([
            (1, 'Original One (2000)', 'Drama'),
            (2, 'Original Two (2010)', 'Drama'),
            (3, 'No Translation (1990)', 'Comedy'),
        ], columns=['movieId','title','genres'])
        self.links = {1: 101, 2: 102}
        self.doc = {'esquema':'cinematch.titulos','versao':1,'idioma':'pt-BR','filmes':[
            dict(movieId=i,tmdbId=self.links[i],titulo_catalogo=self.filmes.iloc[i-1].title,
                 ano=y,titulo_br='Título Brasileiro',alternativos=['Outro Nome', 'Título Brasileiro'],
                 fonte='https://example.org/fixture',verificado_em='2026-11-11')
            for i,y in ((1,2000),(2,2010))
        ]}
        self.validar = validar_aliases
        self.busca = BuscaCatalogo(self.filmes, self.validar(self.doc,self.filmes,self.links))

    def test_original_br_acentos_caixa_e_ano(self):
        self.assertEqual(self.busca.buscar('Original One')[0]['movieId'],1)
        for q in ('TÍTULO BRASILEIRO','titulo brasileiro','Outro Nome'):
            self.assertEqual({f['movieId'] for f in self.busca.buscar(q)},{1,2})
        self.assertEqual([f['movieId'] for f in self.busca.buscar('titulo brasileiro (2010)')],[2])
        self.assertEqual(self.busca.buscar('Original One')[0]['titulo'],'Original One (2000)')
        self.assertEqual(self.busca.buscar('Original One')[0]['titulo_br'],'Título Brasileiro (2000)')

    def test_ausencia_traducao_e_nao_duplicar(self):
        self.assertNotIn('titulo_br',self.busca.buscar('No Translation')[0])
        self.assertEqual(len(self.busca.buscar('Outro Nome')),2)
        self.assertEqual(len(self.busca.buscar('titulo brasileiro')),2)

    def test_associacoes_invalidas(self):
        from copy import deepcopy
        for campo,valor in [('movieId',99),('movieId',True),('tmdbId',999),
                            ('ano',2001),('titulo_catalogo','Outro filme'),
                            ('titulo_br',''),('fonte','http://example.org'),('verificado_em','inválida')]:
            d=deepcopy(self.doc);d['filmes'][0][campo]=valor
            with self.subTest(campo=campo),self.assertRaises(ValueError):
                self.validar(d,self.filmes,self.links)
        d=deepcopy(self.doc);d['filmes'].append(d['filmes'][0])
        with self.assertRaises(ValueError):self.validar(d,self.filmes,self.links)

    def test_indice_ausente_corrompido_e_falha_de_leitura(self):
        from titulos_alternativos import carregar_aliases
        import tempfile
        with tempfile.TemporaryDirectory() as pasta:
            p=Path(pasta)/'titulos.json'
            self.assertEqual(carregar_aliases(self.filmes,self.links,p),{})
            p.write_text('{invalido')
            self.assertEqual(carregar_aliases(self.filmes,self.links,p),{})
            with patch('pathlib.Path.read_text',side_effect=OSError('falha sintética')):
                self.assertEqual(carregar_aliases(self.filmes,self.links,p),{})
        # O índice funciona offline sem cliente TMDB.
        with patch('urllib.request.urlopen',side_effect=AssertionError('Rede proibida')):
            self.assertTrue(self.busca.buscar('titulo brasileiro'))

    def test_interpretacao_tmdb_exige_pt_br_id_e_titulo_unico(self):
        from titulos_alternativos import titulo_br_tmdb
        fixture={'id':101,'translations':[
            {'iso_639_1':'pt','iso_3166_1':'PT','data':{'title':'Nome Portugal'}},
            {'iso_639_1':'pt','iso_3166_1':'BR','data':{'title':'Nome Brasileiro'}}]}
        self.assertEqual(titulo_br_tmdb(fixture,101),'Nome Brasileiro')
        for payload in (None,{}, {'id':102,'translations':[]},
                        {'id':101,'translations':[fixture['translations'][0]]}):
            self.assertIsNone(titulo_br_tmdb(payload,101))
        fixture['translations'].append({'iso_639_1':'pt','iso_3166_1':'BR','data':{'title':'Conflitante'}})
        self.assertIsNone(titulo_br_tmdb(fixture,101))
        with self.assertRaises(ValueError):titulo_br_tmdb({},True)

    def test_endpoint_preserva_id_titulo_e_sessao_com_alias(self):
        from types import SimpleNamespace
        from urllib.parse import quote
        class Transporte:
            def __init__(self):
                self.entrada=io.BytesIO(('GET /api/filmes?q='+quote('Título Brasileiro (2000)')+
                                        ' HTTP/1.0\r\n\r\n').encode())
                self.saida=bytearray()
            def makefile(self,*args):return self.entrada
            def sendall(self,d):self.saida.extend(d)
        aliases=self.validar(self.doc,self.filmes,self.links)
        sessao=Sessao(assistidos=[3])
        with patch.object(Handler,'modelo',SimpleNamespace(filmes=self.filmes)), \
             patch.object(Handler,'busca_modelo',None),patch.object(Handler,'busca',None), \
             patch.object(Handler,'sessoes',{'fixture':(sessao,0)}), \
             patch('app.carregar_links',return_value=self.links), \
             patch('app.carregar_aliases',return_value=aliases):
            t=Transporte();Handler(t,('127.0.0.1',1234),object())
            h,body=bytes(t.saida).split(b'\r\n\r\n',1)
            self.assertIn(b'200 OK',h)
            f=json.loads(body)['sugestoes']
            self.assertEqual([x['movieId'] for x in f],[1])
            self.assertEqual(f[0]['titulo'],'Original One (2000)')
            self.assertEqual(f[0]['titulo_br'],'Título Brasileiro (2000)')
            self.assertEqual(sessao.assistidos,[3])


if __name__=='__main__':unittest.main()
