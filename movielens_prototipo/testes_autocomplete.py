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

    def test_confirmacao_nao_depende_da_ultima_busca(self):
        conversa, sessao = Conversa(fixture()), Sessao()
        # Outra busca ou aba não invalida os IDs já selecionados pelo autocomplete.
        conversa.executar(sessao, {'acao':'buscar','texto':'Solaris'})
        d = conversa.executar(sessao, {'acao':'confirmar_selecao','ids':[3,3,4,5,6,7,8]})
        self.assertEqual(sessao.referencias,[3,4,5,6,7])
        self.assertEqual(sessao.assistidos,[3,4,5,6,7,8])
        self.assertEqual([f['movieId'] for f in d['excedentes']],[8])
        self.assertFalse(set(f['movieId'] for f in d['recomendacoes']) & set(sessao.assistidos))
        with self.assertRaises(ValueError):
            conversa.executar(sessao, {'acao':'confirmar_selecao','ids':[999]})

    def test_endpoint_busca_sem_mutacao_da_sessao(self):
        class Transporte:
            def __init__(self):
                self.entrada=io.BytesIO(b'GET /api/filmes?q=Solaris HTTP/1.0\r\n\r\n')
                self.saida=bytearray()
            def makefile(self,*args):return self.entrada
            def sendall(self,dados):self.saida.extend(dados)
        sessao=Sessao(pendentes={3})
        with patch.object(Handler,'modelo',fixture()),patch.object(Handler,'sessoes',{'teste':(sessao,0)}):
            t=Transporte();Handler(t,('127.0.0.1',1234),object())
            dados=json.loads(bytes(t.saida).split(b'\r\n\r\n')[1])
            self.assertEqual(len(dados['sugestoes']),2)
            self.assertEqual(sessao.pendentes,{3})
            self.assertEqual(len(Handler.sessoes),1)

    @unittest.skipUnless(shutil.which('node'), 'Node.js não disponível para os testes JavaScript; aplicação não depende dele.')
    def test_widget_javascript_teclado_e_concorrencia(self):
        p=Path(__file__).with_name('testes_autocomplete.cjs')
        r=subprocess.run([shutil.which('node'),'--test',str(p)],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stdout+'\n'+r.stderr)


if __name__=='__main__':unittest.main()
