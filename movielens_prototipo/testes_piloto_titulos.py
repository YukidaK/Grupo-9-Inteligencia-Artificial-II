"""Fixtures sintéticas. Nenhuma rede, credencial real ou dataset é necessário."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

import pandas as pd

from busca import BuscaCatalogo
from transporte_tmdb import FalhaConsulta
from piloto_titulos import (TransporteTraducoesTMDB, autorizar, candidatos,
                            carregar_estado, executar, interpretar, planejar)
from titulos_alternativos import validar_aliases
from testes_transporte_tmdb import Resposta


def resposta(tid, titulo='Nome brasileiro'):
    return {'id': tid, 'translations': [{'iso_639_1': 'pt', 'iso_3166_1': 'BR',
                                        'data': {'title': titulo}}]}


class PilotoTitulos(unittest.TestCase):
    def setUp(self):
        self.filmes = pd.DataFrame([(i, f'Original {i} (2000)', 'Drama') for i in range(1, 106)],
                                   columns=['movieId', 'title', 'genres'])
        self.ratings = pd.DataFrame([(u, i, 4.) for i in range(1, 106)
                                    for u in range(1, (5 if i < 3 else 2))],
                                   columns=['userId', 'movieId', 'rating'])
        self.links = {i: i+100 for i in range(1, 106)}
        self.indice = {'esquema': 'cinematch.titulos', 'versao': 1, 'idioma': 'pt-BR', 'filmes': []}
        self.plano = planejar(self.filmes, self.ratings, self.links, self.indice)
        self.hora = datetime(2026, 11, 11, tzinfo=timezone.utc)
        self.tick = 0.
        self.env = patch.dict('os.environ', {'TMDB_READ_ACCESS_TOKEN': 'TOKEN_SINTETICO_PILOTO'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.rede = patch('socket.create_connection', side_effect=AssertionError('Rede proibida'))
        self.rede.start(); self.addCleanup(self.rede.stop)

    def cliente(self, abrir):
        return TransporteTraducoesTMDB(self.links.values(), habilitado=True, termos_aprovados=True,
                                      abrir=abrir, monotono=lambda: self.tick, relogio=lambda: self.hora,
                                      esperar=lambda x: setattr(self, 'tick', self.tick+x))

    def test_top100_deterministico_desempate_e_reproducao(self):
        self.assertEqual([i['movieId'] for i in self.plano['itens']], list(range(1, 101)))
        shuffled = self.ratings.sample(frac=1, random_state=9)
        self.assertEqual(self.plano, planejar(self.filmes.iloc[::-1], shuffled, self.links, self.indice))
        self.assertEqual(len(self.filmes), 105)

    def test_ids_invalidos_conflitos_e_preexistentes(self):
        links = {**self.links, 2: 0, 3: 101}
        p = planejar(self.filmes, self.ratings, links, self.indice)
        self.assertEqual([i['inicial'] for i in p['itens'][:3]], ['conflito', 'sem_tmdb', 'conflito'])
        indice = deepcopy(self.indice)
        indice['filmes'] = [dict(movieId=1, tmdbId=101, titulo_catalogo='Original 1 (2000)', ano=2000,
                                 titulo_br='Já aprovado', alternativos=[], fonte='https://example.org/fixture',
                                 verificado_em='2026-11-11')]
        p = planejar(self.filmes, self.ratings, self.links, indice)
        self.assertEqual(p['itens'][0]['inicial'], 'preexistente')
        cliente = self.cliente(Mock(side_effect=lambda req, **kw: Resposta(req.full_url, resposta(int(req.full_url.split('/')[-2])))))
        with tempfile.TemporaryDirectory() as d:
            executar(p, d, cliente, agora=lambda: self.hora, max_consultas=1)
            self.assertEqual(cliente._abrir.call_args[0][0].full_url.split('/')[-2], '102')
        self.assertEqual(indice['filmes'][0]['titulo_br'], 'Já aprovado')

    def test_traducoes_vazias_pt_pt_malformadas_e_duplicadas(self):
        self.assertEqual(interpretar(resposta(101, ''), 101)[0], 'sem_traducao')
        self.assertEqual(interpretar({'id':101,'translations':[]},101)[0], 'sem_traducao')
        d = resposta(101);d['translations'][0]['iso_3166_1']='PT'
        self.assertEqual(interpretar(d,101)[0], 'sem_traducao')
        self.assertEqual(interpretar(None,101)[0], 'erro')
        self.assertEqual(interpretar(resposta(102),101)[0], 'conflito')
        d=resposta(101);d['translations']*=2
        self.assertEqual(interpretar(d,101)[0], 'candidato')
        vazio=resposta(101);vazio['translations'].append(resposta(101,'')['translations'][0])
        self.assertEqual(interpretar(vazio,101)[0],'erro')
        d['translations'].append(resposta(101,'Outro')['translations'][0])
        self.assertEqual(interpretar(d,101)[0], 'conflito')

    def test_retomada_sem_repetir_terminais_e_orcamento(self):
        abrir=Mock(side_effect=lambda req, **kw: Resposta(req.full_url, resposta(int(req.full_url.split('/')[-2]))))
        cliente=self.cliente(abrir)
        with tempfile.TemporaryDirectory() as d:
            executar(self.plano,d,cliente,max_consultas=1,agora=lambda:self.hora)
            executar(self.plano,d,cliente,max_consultas=1,agora=lambda:self.hora)
            self.assertEqual([c.args[0].full_url.split('/')[-2] for c in abrir.call_args_list], ['101','102'])
            estado=carregar_estado(d,self.plano)
            self.assertEqual(len(candidatos(estado)['filmes']),2)
            with self.assertRaises(ValueError):validar_aliases(candidatos(estado),self.filmes,self.links)
            indice=candidatos(estado)
            for f in indice['filmes']:f['revisao']='aprovada'
            busca=BuscaCatalogo(self.filmes,validar_aliases(indice,self.filmes,self.links))
            self.assertEqual({r['movieId'] for r in busca.buscar('NOME BRASILEIRO')},{1,2})
            self.assertEqual(busca.buscar('Original 1 (2000)')[0]['movieId'],1)

    def test_429_persistido_e_retomada_com_repeticao_explicita(self):
        abrir=Mock(side_effect=urllib.error.HTTPError('https://example.org',429,'limit',{'Retry-After':'120'},None))
        cliente=self.cliente(abrir)
        with tempfile.TemporaryDirectory() as d:
            r=executar(self.plano,d,cliente,agora=lambda:self.hora)
            self.assertEqual(r['chamadas_rede'],1)
            self.assertEqual(r['estados']['erro'],1)
            self.assertEqual(abrir.call_count,1)
            executar(self.plano,d,cliente,repetir_erros=True,agora=lambda:self.hora)
            self.assertEqual(abrir.call_count,1)
            self.tick=121
            from datetime import timedelta
            hora=self.hora+timedelta(seconds=121)
            abrir.side_effect=lambda req, **kw:Resposta(req.full_url,resposta(101))
            executar(self.plano,d,cliente,repetir_erros=True,agora=lambda:hora,max_consultas=1)
            self.assertEqual(carregar_estado(d,self.plano)['registros']['1']['estado'],'candidato')

    def test_autenticacao_e_rede_nao_viram_ausencia_de_traducao(self):
        for code in (401,403):
            with self.subTest(code=code),tempfile.TemporaryDirectory() as d:
                abrir=Mock(side_effect=urllib.error.HTTPError('https://example.org',code,'erro',{},None))
                r=executar(self.plano,d,self.cliente(abrir),agora=lambda:self.hora)
                self.assertEqual(r['estados']['erro'],1);self.assertEqual(r['estados'].get('sem_traducao',0),0)
                self.assertEqual(abrir.call_count,1)
        for exception in (TimeoutError(),urllib.error.URLError('falha sintética')):
            with self.subTest(exception=type(exception)),tempfile.TemporaryDirectory() as d:
                abrir=Mock(side_effect=exception)
                executar(self.plano,d,self.cliente(abrir),agora=lambda:self.hora)
                estado=carregar_estado(d,self.plano)
                self.assertIn(estado['registros']['1']['motivo'],('TIMEOUT','CONEXAO'))

    def test_falha_apos_sucesso_retoma_apenas_o_item_pendente(self):
        from datetime import timedelta
        calls=[]
        def abrir(req, **kwargs):
            tid=int(req.full_url.split('/')[-2]);calls.append(tid)
            if tid==102 and calls.count(102)==1:
                raise urllib.error.URLError('falha sintética')
            return Resposta(req.full_url,resposta(tid))
        cliente=self.cliente(abrir)
        with tempfile.TemporaryDirectory() as d:
            executar(self.plano,d,cliente,agora=lambda:self.hora,max_consultas=3)
            self.assertEqual(calls,[101,102])
            self.tick=61
            executar(self.plano,d,cliente,repetir_erros=True,
                     agora=lambda:self.hora+timedelta(seconds=61),max_consultas=1)
            self.assertEqual(calls,[101,102,102])
            estado=carregar_estado(d,self.plano)
            self.assertEqual(len(candidatos(estado)['filmes']),2)

    def test_bloqueios_transporte_ids_destino_e_credencial(self):
        abrir=Mock()
        c=TransporteTraducoesTMDB([101],abrir=abrir)
        with self.assertRaises(FalhaConsulta):c.consultar_traducoes(101)
        for tid in (True,0,-1,999,'101'):
            with self.assertRaises(ValueError):self.cliente(abrir).consultar_traducoes(tid)
        with patch.dict('os.environ',{'TMDB_READ_ACCESS_TOKEN':''}):
            with self.assertRaises(FalhaConsulta):self.cliente(abrir).consultar_traducoes(101)
        abrir.assert_not_called()
        abrir.side_effect=lambda req, **kw:Resposta('http://127.0.0.1',resposta(101))
        with self.assertRaises(FalhaConsulta):self.cliente(abrir).consultar_traducoes(101)

    def test_sem_rede_planejamento_e_checkpoint_incompativel(self):
        with tempfile.TemporaryDirectory() as d:
            r=executar(self.plano,d)
            self.assertEqual(r['chamadas_rede'],0)
            self.assertEqual(r['estados']['pendente'],100)
            outro=deepcopy(self.plano);outro['itens'][0]['avaliacoes']=999
            with self.assertRaises(ValueError):carregar_estado(d,outro)
            p=Path(d)/'estado.json';envelope=json.loads(p.read_text());envelope['estado']['registros']['1']['estado']='candidato'
            p.write_text(json.dumps(envelope))
            with self.assertRaises(ValueError):carregar_estado(d,self.plano)

    def test_falha_gravacao_preserva_checkpoint_e_execucao_exclusiva(self):
        from piloto_titulos import salvar, exclusivo
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'estado.json';p.write_text('anterior')
            with patch('os.replace',side_effect=OSError('falha sintética')):
                with self.assertRaises(OSError):salvar(p,{'novo':1})
            self.assertEqual(p.read_text(),'anterior')
            with exclusivo(d):
                with self.assertRaises(FileExistsError):executar(self.plano,d)
            self.assertFalse((Path(d)/'.execucao.lock').exists())

    def test_aprovacoes_e_credenciais_nao_sao_publicadas(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'aprovacoes.json';p.write_text('{}')
            with self.assertRaises(ValueError):autorizar(p)
            p.write_text('null')
            with self.assertRaises(ValueError):autorizar(p)
            doc=Path(d)/'termos.txt';doc.write_text('Fixture sintética de termos.')
            p.write_text(json.dumps({'termos_aprovados':True,'autorizacao_operacional':True,
                                    'escopo':'titulos_filmes_pt_BR','documentos':[
                                        {'arquivo':'termos.txt','sha256':hashlib.sha256(doc.read_bytes()).hexdigest()}]}))
            autorizar(p)
            doc.write_text('mudança')
            with self.assertRaises(ValueError):autorizar(p)


if __name__=='__main__':unittest.main()
