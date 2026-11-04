"""RF-02D: catálogo fictício só nas fixtures, HTTP em memória e DOM simulado."""
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from app import Handler
from conversa import Sessao,Conversa
from streaming_web import executar_streaming,CATALOGO_BR
from testes_conversa import fixture

CATALOGO=((10,'Serviço Alfa — teste'),(20,'Serviço Beta — teste'))


class StreamingWebTests(unittest.TestCase):
    def pedido(self,ids=(10,),modo='restrito',**extras):
        return dict(acao='salvar',provedores=list(ids),regiao='BR',modo=modo,**extras)

    def test_sem_catalogo_publico_nao_expoe_ids_ficticios(self):
        self.assertEqual(CATALOGO_BR,())
        s=Sessao();r=executar_streaming(s,{'acao':'estado'})
        self.assertEqual(r['catalogo']['provedores'],[])
        self.assertIsNone(r['preferencias']);self.assertFalse(r['integracao_ativa'])
        with self.assertRaises(ValueError):executar_streaming(s,self.pedido())
        r=executar_streaming(s,self.pedido((),modo='flexivel'))
        self.assertEqual(r['preferencias']['provedores'],[])
        self.assertEqual(r['preferencias']['modo'],'flexivel')

    def test_salvar_remover_multiplos_modos_e_restaurar(self):
        s=Sessao()
        for ids,modo in (((10,20),'restrito'),((20,),'flexivel'),((),'restrito')):
            r=executar_streaming(s,self.pedido(ids,modo),CATALOGO)
            self.assertEqual(r['preferencias']['provedores'],list(ids))
            self.assertEqual(executar_streaming(s,{'acao':'estado'},CATALOGO)['preferencias'],r['preferencias'])
            self.assertFalse(s.streaming.ativo)

    def test_preserva_perfil_e_recomendacoes(self):
        c=Conversa(fixture());s=Sessao()
        c.executar(s,{'acao':'confirmar_selecao','ids':[1,4]})
        c.executar(s,{'texto':'Não gosto de terror'})
        antes=deepcopy(s.__dict__)
        executar_streaming(s,self.pedido((10,20),'flexivel'),CATALOGO)
        depois=deepcopy(s.__dict__);depois.pop('streaming');antes.pop('streaming')
        self.assertEqual(antes,depois)

    def test_ids_regiao_modo_e_campos_de_ativacao_rejeitados_sem_mutacao(self):
        s=Sessao()
        ruins=[self.pedido((99,)),self.pedido((True,)),self.pedido(('10',)),self.pedido((10,10)),
               self.pedido(ativo=True),self.pedido(token='SEGREDO_SINTETICO'),self.pedido(modo='outro'),
               {**self.pedido(),'regiao':'US'}]
        for r in ruins:
            with self.subTest(r=r),self.assertRaises(ValueError):executar_streaming(s,r,CATALOGO)
            self.assertIsNone(s.streaming)

    def test_reconciliacao_preserva_ausentes_sem_homologar_e_remocao_explicita(self):
        s=Sessao();executar_streaming(s,self.pedido((10,20),'flexivel'),CATALOGO)
        novo=((10,'Alfa atualizado'),(30,'Gama sintético'))
        antigo=s.streaming
        r=executar_streaming(s,{'acao':'estado'},novo)
        self.assertIs(s.streaming,antigo)
        self.assertEqual(r['reconciliacao'],{'provedores_ausentes':[20],'revisao_necessaria':True})
        self.assertNotIn(20,[p['id'] for p in r['catalogo']['provedores']])
        self.assertIn('preservadas para revisão',r['mensagem'])
        r=executar_streaming(s,self.pedido((10,30),'flexivel'),novo)
        self.assertEqual(r['preferencias']['provedores'],[10,20,30])  # cliente legado não apaga ID omitido
        r=executar_streaming(s,self.pedido((10,30),'flexivel',remover_incompativeis=[20]),novo)
        self.assertEqual(r['preferencias']['provedores'],[10,30])
        self.assertFalse(r['reconciliacao']['revisao_necessaria']);self.assertFalse(s.streaming.ativo)
        with self.assertRaises(ValueError):executar_streaming(s,self.pedido((10,20)),novo)

    def test_reconciliacao_ids_iguais_sessoes_e_revisoes_invalidas(self):
        a,b=Sessao(),Sessao();executar_streaming(a,self.pedido((10,20)),CATALOGO)
        igual=executar_streaming(a,{'acao':'estado'},CATALOGO)
        self.assertEqual(igual['reconciliacao']['provedores_ausentes'],[])
        novo=((10,'Alfa sintético'),)
        before=a.streaming
        for dados in [self.pedido((10,99)),self.pedido((10,),remover_incompativeis=[99]),
                      self.pedido((10,20),remover_incompativeis=[20]),self.pedido((10,),remover_incompativeis=[True]),
                      self.pedido((10,),remover_incompativeis=[20,20]),self.pedido((10,),ativo=True)]:
            with self.subTest(dados=dados),self.assertRaises(ValueError):executar_streaming(a,dados,novo)
            self.assertIs(a.streaming,before)
        with self.assertRaises(ValueError):executar_streaming(b,self.pedido((20,)),novo)
        self.assertIsNone(b.streaming)
        r=executar_streaming(a,{'acao':'estado'},())
        self.assertEqual(r['preferencias']['provedores'],[10,20])
        self.assertEqual(r['reconciliacao']['provedores_ausentes'],[10,20])

    def test_http_cookies_origin_isolamento_e_json_legado(self):
        class Transporte:
            def __init__(self,d):self.entrada=io.BytesIO(d);self.saida=bytearray()
            def makefile(self,*a):return self.entrada
            def sendall(self,d):self.saida.extend(d)
        def post(d,cookie='',path='/api/streaming',origin=''):
            body=json.dumps(d).encode()
            req=(f'POST {path} HTTP/1.0\r\nHost: localhost\r\nCookie: {cookie}\r\n'+
                 (f'Origin: {origin}\r\n' if origin else '')+f'Content-Length: {len(body)}\r\n\r\n').encode()+body
            t=Transporte(req);Handler(t,('127.0.0.1',1),object())
            h,b=bytes(t.saida).split(b'\r\n\r\n',1)
            novo=next((x.split(': ',1)[1].split(';')[0] for x in h.decode().split('\r\n') if x.startswith('Set-Cookie:')),cookie)
            return h,json.loads(b),novo
        with patch.object(Handler,'modelo',fixture()),patch.object(Handler,'sessoes',{}),patch.object(Handler,'catalogo_streaming',CATALOGO),patch('socket.create_connection',side_effect=AssertionError('Rede proibida')):
            _,a,ca=post({'acao':'estado'})
            _,b,cb=post({'acao':'estado'});self.assertNotEqual(ca,cb)
            _,perfil,_=post({'acao':'confirmar_selecao','ids':[1,4]},ca,'/api/recomendar')
            h,a,_=post(self.pedido((10,20),'flexivel'),ca)
            self.assertIn(b'200 OK',h);self.assertFalse(a['preferencias']['ativo'])
            _,a,_=post({'acao':'estado'},ca);self.assertEqual(a['preferencias']['provedores'],[10,20])
            _,b,_=post({'acao':'estado'},cb);self.assertIsNone(b['preferencias'])
            _,depois,_=post({'acao':'estado'},ca,'/api/recomendar')
            self.assertEqual(perfil['recomendacoes'],depois['recomendacoes'])
            self.assertNotIn('streaming',depois)
            h,_,_=post(self.pedido(ativo=True),ca);self.assertIn(b'400 Bad Request',h)
            h,_,_=post(self.pedido((99,)),ca);self.assertIn(b'400 Bad Request',h)
            h,_,_=post(self.pedido(),ca,origin='https://outro.test');self.assertIn(b'400 Bad Request',h)
            with patch.object(Handler,'catalogo_streaming',((10,'Alfa — teste'),)):
                h,r,_=post({'acao':'estado'},ca)
                self.assertIn(b'200 OK',h);self.assertEqual(r['reconciliacao']['provedores_ausentes'],[20])
                h,r,_=post(self.pedido((10,),remover_incompativeis=[20]),ca)
                self.assertIn(b'200 OK',h);self.assertEqual(r['preferencias']['provedores'],[10])
                self.assertFalse(r['preferencias']['ativo'])
                h,_,_=post(self.pedido((20,)),cb);self.assertIn(b'400 Bad Request',h)
                _,r,_=post({'acao':'estado'},cb);self.assertIsNone(r['preferencias'])
            post({'acao':'reiniciar'},ca,'/api/recomendar')
            _,a,_=post({'acao':'estado'},ca);self.assertIsNone(a['preferencias'])

    @unittest.skipUnless(shutil.which('node'),'Node não disponível')
    def test_javascript_streaming(self):
        r=subprocess.run([shutil.which('node'),'--test',str(Path(__file__).with_name('testes_streaming.cjs'))],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_html_sem_marcas_credenciais_ou_controle_de_ativacao(self):
        p=Path(__file__).with_name('index.html').read_text()
        js=Path(__file__).with_name('static').joinpath('streaming.js').read_text()
        self.assertIn('streaming-title',p);self.assertIn('aria-live="polite"',p)
        self.assertIn('minmax(min(100%,190px)',p)
        self.assertNotIn('TMDB_READ_ACCESS_TOKEN',p+js)
        self.assertNotIn('api.themoviedb.org',p+js)
        self.assertNotIn('Netflix',p+js)
