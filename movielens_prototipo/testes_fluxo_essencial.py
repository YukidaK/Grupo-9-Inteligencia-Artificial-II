"""Fluxo essencial, HTTP em memória e regressão dos perfis padrão."""
from copy import deepcopy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from conversa import Conversa, Sessao
from app import Handler
from testes_conversa import fixture


class FluxoEssencial(unittest.TestCase):
    def setUp(self):
        self.modelo=fixture();self.c=Conversa(self.modelo);self.s=Sessao()

    def test_zero_uma_duas_e_ate_cinco_referencias(self):
        self.assertEqual(self.c.executar(self.s,{'acao':'estado'})['recomendacoes'],[])
        for n in range(1,6):
            s=Sessao();r=self.c.executar(s,{'acao':'confirmar_selecao','ids':list(range(1,n+1))})
            self.assertTrue(r['recomendacoes']);self.assertLessEqual(len(r['recomendacoes']),10)
            self.assertEqual(len(r['referencias']),n)
            if n<=2:self.assertIn('sem garantir maior precisão',r['mensagem'])
            self.assertFalse(set(range(1,n+1)) & {f['movieId'] for f in r['recomendacoes']})

    def test_nova_selecao_substitui_referencias_e_preserva_historico(self):
        self.c.executar(self.s,{'acao':'confirmar_selecao','ids':[1,2]})
        self.c.executar(self.s,{'acao':'confirmar_selecao','ids':[3]})
        self.assertEqual(self.s.referencias,[3]);self.assertEqual(self.s.assistidos,[1,2,3])
        self.assertFalse({1,2,3} & {r['movieId'] for r in self.s.recomendacoes})
        self.c.executar(self.s,{'acao':'reiniciar'})
        self.assertEqual(self.s.assistidos,[]);self.assertEqual(self.s.recomendacoes,[])

    def test_entradas_invalidas_e_refinamento_rejeitado_sem_mutacao(self):
        for pedido in ({'acao':'confirmar_selecao','ids':[]}, {'acao':'confirmar_selecao','ids':[True]},
                       {'acao':'confirmar_selecao','ids':[99]}, {'acao':'confirmar_selecao','ids':list(range(1,7))},
                       {'acao':'mensagem','texto':'Quero suspense'}, {'acao':'rejeitar','movieId':1},
                       {'acao':'remover_referencia','movieId':1}, {'acao':'considerar','movieId':1},
                       {'acao':'confirmar_selecao','ids':[1],'positivos':['Drama']}):
            before=deepcopy(self.s)
            with self.subTest(pedido=pedido),self.assertRaises(ValueError):self.c.executar(self.s,pedido)
            self.assertEqual(self.s,before)

    def test_comparacao_deterministica_geracao_direta(self):
        for ids in ([1],[1,2],[1,2,3],[1,2,3,4],[1,2,3,4,5]):
            esperado=self.modelo.recomendar_perfil(Sessao(assistidos=list(ids),referencias=list(ids)))
            r=self.c.executar(Sessao(),{'acao':'confirmar_selecao','ids':list(ids)})
            self.assertEqual(r['recomendacoes'],esperado)

    def test_falha_no_motor_nao_publica_estado_parcial(self):
        self.c.executar(self.s,{'acao':'confirmar_selecao','ids':[1]});before=deepcopy(self.s)
        with patch.object(self.modelo,'recomendar_perfil',side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):self.c.executar(self.s,{'acao':'confirmar_selecao','ids':[2]})
        self.assertEqual(self.s,before)

    def test_http_busca_confirmacao_cookie_placeholder_e_rotas_encerradas(self):
        def req(method,path,dados=None,cookie=''):
            body=b'' if dados is None else json.dumps(dados).encode()
            raw=(f'{method} {path} HTTP/1.0\r\nHost: localhost\r\nCookie: {cookie}\r\nContent-Length: {len(body)}\r\n\r\n').encode()+body
            class T:
                def __init__(self):self.entrada=io.BytesIO(raw);self.saida=bytearray()
                def makefile(self,*a):return self.entrada
                def sendall(self,b):self.saida.extend(b)
            t=T();Handler(t,('127.0.0.1',1),object());h,b=bytes(t.saida).split(b'\r\n\r\n',1)
            token=next((l.split(': ',1)[1].split(';')[0] for l in h.decode().split('\r\n') if l.startswith('Set-Cookie:')),cookie)
            return h,b,token
        with patch.object(Handler,'modelo',self.modelo),patch.object(Handler,'posteres',None),patch.object(Handler,'sessoes',{}),patch.object(Handler,'_estados',{}):
            h,b,cookie=req('GET','/api/filmes?q=Solaris');self.assertEqual(len(json.loads(b)['sugestoes']),2)
            h,b,cookie=req('POST','/api/recomendar',{'acao':'confirmar_selecao','ids':[1]})
            self.assertIn(b'200 OK',h);self.assertTrue(json.loads(b)['recomendacoes'])
            _,b,_=req('POST','/api/recomendar',{'acao':'estado'},cookie);self.assertEqual(len(json.loads(b)['referencias']),1)
            _,b,_=req('POST','/api/recomendar',{'acao':'estado'});self.assertEqual(json.loads(b)['referencias'],[])
            h,b,_=req('GET','/api/poster/1');self.assertEqual(json.loads(b)['poster_url'],'/static/poster-placeholder.svg')
            for method,path in [('POST','/api/streaming'),('GET','/static/streaming.js')]:
                h,_,_=req(method,path,{'acao':'estado'} if method=='POST' else None)
                self.assertIn(b'404',h)

    def test_html_sem_controles_descontinuados(self):
        html=Path(__file__).with_name('index.html').read_text()
        for texto in ('streaming-form','/api/streaming','id="chat"','Não gostei','remover_referencia','Preferências:'):
            self.assertNotIn(texto,html)
