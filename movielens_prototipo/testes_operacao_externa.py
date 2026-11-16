"""Controles compartilhados de operações externas e sessões essenciais."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
import threading
import time
import unittest
from unittest.mock import Mock, patch
from operacao_externa import (ControleExterno, LimiteOperacional, Prazo, usar_prazo, controle_credencial)
from estado_sessao import EstadoSessao
from conversa import Sessao, Conversa
from app import Handler
from posteres import Posteres, PLACEHOLDER
from testes_conversa import fixture
from piloto_titulos import TransporteTraducoesTMDB
from transporte_tmdb import FalhaConsulta
from testes_transporte_tmdb import Resposta, TOKEN


class OperacaoExternaTests(unittest.TestCase):
    def setUp(self):
        env=patch.dict('os.environ',{'TMDB_READ_ACCESS_TOKEN':TOKEN})
        env.start();self.addCleanup(env.stop)
        rede=patch('socket.create_connection',side_effect=AssertionError('Rede externa proibida'))
        rede.start();self.addCleanup(rede.stop)
    def cliente(self, abrir, **kwargs):
        return TransporteTraducoesTMDB([100],abrir=abrir,habilitado=True,termos_aprovados=True,**kwargs)

    def test_limite_concorrencia_fila_prazo_e_recuperacao(self):
        c=ControleExterno(concorrencia=1);entrou=threading.Event();liberar=threading.Event()
        def ocupar():
            with c.admitir():entrou.set();liberar.wait(2)
        with ThreadPoolExecutor(max_workers=1) as pool:
            f=pool.submit(ocupar)
            try:
                self.assertTrue(entrou.wait(1));inicio=time.monotonic()
                with usar_prazo(Prazo(inicio,.03)),self.assertRaises(LimiteOperacional):
                    with c.admitir():self.fail('Não deveria entrar')
                print('SIMULACAO '+json.dumps({'fila_timeout_simulado_segundos':time.monotonic()-inicio}))
            finally:liberar.set()
            f.result(timeout=2)
        with c.admitir():pass
        self.assertEqual(c.pico,1);self.assertEqual(c.em_andamento,0)
    def test_orcamento_renovacao_e_prazo_sem_transporte(self):
        tick=[0.];ctrl=ControleExterno(chamadas=1,janela=10,relogio=lambda:tick[0])
        with ctrl.admitir():pass
        with self.assertRaisesRegex(LimiteOperacional,'ORCAMENTO'):
            with ctrl.admitir():pass
        tick[0]=10
        with ctrl.admitir():pass
        abrir=Mock();c=self.cliente(abrir)
        with usar_prazo(Prazo(time.monotonic(),0)),self.assertRaisesRegex(FalhaConsulta,'TIMEOUT'):
            c.consultar_traducoes(100)
        abrir.assert_not_called()
    def test_prazo_restante_chega_ao_timeout(self):
        limites=[]
        def abrir(req,timeout):limites.append(timeout);return Resposta(req.full_url,{'id':100,'translations':[]})
        with usar_prazo(Prazo(time.monotonic(),.4)):
            self.cliente(abrir).consultar_traducoes(100)
        self.assertGreater(limites[0],0);self.assertLessEqual(limites[0],.4)
    def test_mesma_credencial_compartilha_orcamento_sem_guarda_token(self):
        self.assertIs(controle_credencial(TOKEN),controle_credencial(TOKEN))
        self.assertIsNot(controle_credencial(TOKEN),controle_credencial(TOKEN+'2'))
        ctrl=ControleExterno(chamadas=1)
        c=self.cliente(lambda req,timeout:Resposta(req.full_url,{'id':100,'translations':[]}),controle=ctrl)
        c.consultar_traducoes(100);p=Posteres({1:100},TOKEN,abrir=Mock(),controle=ctrl)
        self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER);p.abrir.assert_not_called()
    def test_snapshot_isolado_versao_e_sessoes_independentes(self):
        c=Conversa(fixture());a,b=EstadoSessao(Sessao()),EstadoSessao(Sessao())
        a.executar(lambda s:c.executar(s,{'acao':'confirmar_selecao','ids':[1]}))
        snap=a.snapshot();snap.dados.assistidos.append(99)
        self.assertNotIn(99,a.sessao.assistidos)
        a.executar(lambda s:s.referencias.append(2))
        self.assertFalse(a.aplicar(snap,lambda s:s.assistidos.clear()))
        self.assertFalse(b.aplicar(a.snapshot(),lambda s:s.assistidos.clear()))
        self.assertIn(1,a.sessao.assistidos)
        self.assertTrue(a.aplicar(a.snapshot(),lambda s:None))
    def test_http_duas_sessoes_nao_serializa_operacao_lenta(self):
        def post(d,cookie=''):
            body=json.dumps(d).encode();req=(f'POST /api/recomendar HTTP/1.0\r\nHost: localhost\r\nCookie: {cookie}\r\nContent-Length: {len(body)}\r\n\r\n').encode()+body
            class T:
                def __init__(self):self.entrada=io.BytesIO(req);self.saida=bytearray()
                def makefile(self,*a):return self.entrada
                def sendall(self,d):self.saida.extend(d)
            t=T();Handler(t,('127.0.0.1',1),object());h,b=bytes(t.saida).split(b'\r\n\r\n')
            cookie=next((x.split(': ',1)[1].split(';')[0] for x in h.decode().split('\r\n') if x.startswith('Set-Cookie:')),cookie)
            return json.loads(b),cookie
        gate=threading.Event();release=threading.Event();original=Conversa.executar
        def lento(c,s,d):
            if d.get('ids')==[2]:gate.set();release.wait(2)
            return original(c,s,d)
        with patch.object(Handler,'modelo',fixture()),patch.object(Handler,'sessoes',{}),patch.object(Handler,'_estados',{}):
            _,ca=post({'acao':'estado'});_,cb=post({'acao':'estado'})
            with patch.object(Conversa,'executar',lento),ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(post,{'acao':'confirmar_selecao','ids':[2]},ca)
                try:
                    self.assertTrue(gate.wait(1));inicio=time.monotonic()
                    b=pool.submit(post,{'acao':'confirmar_selecao','ids':[1]},cb).result(timeout=1)
                    self.assertTrue(b[0]['referencias']);self.assertFalse(a.done())
                    print('SIMULACAO '+json.dumps({'http_sessao_independente_segundos':time.monotonic()-inicio}))
                finally:release.set()
                a.result(timeout=2)
