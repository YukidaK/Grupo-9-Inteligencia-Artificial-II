"""RF-02E2-PRE: somente transportes sintéticos, threads limitadas e sentinela de rede."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch,Mock
import urllib.error

from operacao_externa import (ControleExterno, LimiteOperacional, Prazo, usar_prazo,
    TravaRegistro, controle_credencial)
from estado_sessao import EstadoSessao
from conversa import Sessao,Conversa
from app import Handler
from testes_conversa import fixture
from identidades import conteudo_movielens
from tmdb_disponibilidade import ClienteDisponibilidadeTMDB,TransporteTMDB
from testes_tmdb_disponibilidade import Resposta,payload,TOKEN
from disponibilidade import Estado
from posteres import Posteres,PLACEHOLDER
from coletar_catalogo import coletar
from catalogo_streaming import carregar_catalogo


class OperacaoExternaTests(unittest.TestCase):
    def setUp(self):
        env=patch.dict('os.environ',{'TMDB_READ_ACCESS_TOKEN':TOKEN});env.start();self.addCleanup(env.stop)
        rede=patch('socket.create_connection',side_effect=AssertionError('Rede real proibida'));rede.start();self.addCleanup(rede.stop)
        self.links={conteudo_movielens(i):i*100 for i in (1,2,3)}
    def cliente(self,abrir,**kwargs):
        return ClienteDisponibilidadeTMDB(self.links,abrir=abrir,habilitado=True,termos_aprovados=True,**kwargs)
    def test_cache_rapido_e_filme_independente_durante_consulta_lenta(self):
        entrou=threading.Event();liberar=threading.Event()
        def abrir(req,timeout):
            i=int(req.full_url.split('/movie/')[1].split('/')[0])
            if i==200:entrou.set();liberar.wait(2)
            return Resposta(req.full_url,payload(i))
        c=self.cliente(abrir);primeiro=c.obter(conteudo_movielens(1))
        with ThreadPoolExecutor(max_workers=2) as pool:
            lento=pool.submit(c.obter,conteudo_movielens(2))
            try:
                self.assertTrue(entrou.wait(1));inicio=time.monotonic()
                self.assertIs(c.obter(conteudo_movielens(1)),primeiro)
                duracao=time.monotonic()-inicio
                outro=pool.submit(c.obter,conteudo_movielens(3)).result(timeout=1)
                self.assertEqual(outro.tmdb_id,300);self.assertFalse(lento.done())
                print('SIMULACAO '+json.dumps({'cache_sob_consulta_lenta_segundos':duracao,'pico_externo':c._transporte.controle.pico}))
            finally:liberar.set()
            self.assertIs(lento.result(timeout=2).estado,Estado.CONFIRMADA)
    def test_deduplicacao_contabilidade_por_chave(self):
        gate=threading.Barrier(6);calls=[]
        def abrir(req,timeout):calls.append(req.full_url);return Resposta(req.full_url,payload())
        c=self.cliente(abrir)
        def obter(_):gate.wait(2);return c.obter_controlado(conteudo_movielens(1),permitir_consulta=True)
        with ThreadPoolExecutor(max_workers=6) as pool:r=list(pool.map(obter,range(6)))
        self.assertEqual(len(calls),1);self.assertEqual(sum(x.chamadas_transporte for x in r),1)
        self.assertEqual(sum(x.origem=='CONSULTA' for x in r),1)
        self.assertTrue(all(x.disponibilidade is r[0].disponibilidade for x in r))
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
        with usar_prazo(Prazo(time.monotonic(),0)):
            d=c.obter(conteudo_movielens(1))
        self.assertEqual(d.motivo,'TIMEOUT');abrir.assert_not_called()
    def test_prazo_restante_chega_ao_timeout(self):
        limites=[]
        def abrir(req,timeout):limites.append(timeout);return Resposta(req.full_url,payload())
        with usar_prazo(Prazo(time.monotonic(),.4)):
            self.cliente(abrir).obter(conteudo_movielens(1))
        self.assertGreater(limites[0],0);self.assertLessEqual(limites[0],.4)
    def test_429_compartilhado_disponibilidade_e_posteres(self):
        tick=[0.];ctrl=ControleExterno(relogio=lambda:tick[0]);calls=[]
        def falhar(req,timeout):raise urllib.error.HTTPError(req.full_url,429,'segredo',{'Retry-After':'12'},None)
        c=self.cliente(falhar,controle=ctrl,monotono=lambda:tick[0])
        self.assertEqual(c.obter(conteudo_movielens(1)).motivo,'HTTP_429')
        def poster(req,timeout):calls.append(1);return io.BytesIO(b'{"id":100,"poster_path":null}')
        p=Posteres({1:100},TOKEN,abrir=poster,controle=ctrl)
        self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER);self.assertEqual(calls,[])
        tick[0]=13
        with ctrl.admitir():pass
        self.assertNotIn(TOKEN,repr(ctrl))
    def test_429_data_http_e_timeout_conexao_sanitizados(self):
        from email.utils import format_datetime
        from datetime import timedelta
        now=datetime.now(timezone.utc);tick=[0.];ctrl=ControleExterno(relogio=lambda:tick[0])
        def falhar(req,timeout):raise urllib.error.HTTPError(req.full_url,429,TOKEN,{'Retry-After':format_datetime(now+timedelta(seconds=20))},None)
        c=self.cliente(falhar,controle=ctrl,relogio=lambda:now,monotono=lambda:tick[0])
        self.assertEqual(c.obter(conteudo_movielens(1)).motivo,'HTTP_429')
        with self.assertRaisesRegex(LimiteOperacional,'SUSPENSA'):
            with ctrl.admitir():pass
        for erro,motivo in [(TimeoutError(TOKEN),'TIMEOUT'),(urllib.error.URLError(TOKEN),'CONEXAO')]:
            c=self.cliente(Mock(side_effect=erro));d=c.obter(conteudo_movielens(1))
            self.assertEqual(d.motivo,motivo);self.assertNotIn(TOKEN,repr(d))
            self.assertEqual(c._transporte.controle.em_andamento,0)
    def test_retry_after_invalido_nao_suspende_poster_para_sempre(self):
        import math
        for valor in ('Infinity','NaN','-1','inválido'):
            tick=[0.];ctrl=ControleExterno(relogio=lambda:tick[0])
            p=Posteres({},TOKEN,abrir=Mock(),relogio=lambda:tick[0],controle=ctrl)
            p._penalizar(urllib.error.HTTPError('https://api.themoviedb.org',429,'erro',{'Retry-After':valor},None))
            self.assertTrue(math.isfinite(p.pausa_ate));self.assertEqual(p.pausa_ate,60)
            tick[0]=61
            with ctrl.admitir():pass

    def test_mesma_credencial_compartilha_orcamento_sem_guarda_token(self):
        self.assertIs(controle_credencial(TOKEN),controle_credencial(TOKEN))
        self.assertIsNot(controle_credencial(TOKEN),controle_credencial(TOKEN+'2'))
        ctrl=ControleExterno(chamadas=1)
        c=self.cliente(lambda req,timeout:Resposta(req.full_url,payload()),controle=ctrl)
        c.obter(conteudo_movielens(1));p=Posteres({1:100},TOKEN,abrir=Mock(),controle=ctrl)
        self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER);p.abrir.assert_not_called()
    def test_transporte_proibido_sob_trava_global(self):
        abrir=Mock();c=self.cliente(abrir)
        with Handler.trava:d=c.obter(conteudo_movielens(1))
        abrir.assert_not_called();self.assertIs(d.estado,Estado.ERRO)
    def test_snapshot_isolado_versao_e_sessoes_independentes(self):
        c=Conversa(fixture());a,b=EstadoSessao(Sessao()),EstadoSessao(Sessao())
        a.executar(lambda s:c.executar(s,{'acao':'confirmar_selecao','ids':[1]}))
        snap=a.snapshot();snap.dados.assistidos.append(99)
        self.assertNotIn(99,a.sessao.assistidos)
        a.executar(lambda s:c.executar(s,{'acao':'mensagem','texto':'Não gosto de terror'}))
        self.assertFalse(a.aplicar(snap,lambda s:s.assistidos.clear()))
        self.assertFalse(b.aplicar(a.snapshot(),lambda s:s.assistidos.clear()))
        self.assertIn(1,a.sessao.assistidos)
        self.assertTrue(a.aplicar(a.snapshot(),lambda s:None))
    def test_preferencia_alterada_durante_consulta_snapshot_obsoleto(self):
        from streaming_web import executar_streaming
        a=EstadoSessao(Sessao());gate=threading.Event();release=threading.Event()
        snap=a.snapshot()
        def consultar():gate.set();release.wait(2);return a.aplicar(snap,lambda s:setattr(s,'recomendacoes',['obsoleta']))
        with ThreadPoolExecutor(max_workers=1) as pool:
            futuro=pool.submit(consultar)
            try:
                self.assertTrue(gate.wait(1))
                a.executar(lambda s:executar_streaming(s,{'acao':'salvar','regiao':'BR','provedores':[10],'modo':'restrito'},((10,'Fictício'),)))
            finally:release.set()
            self.assertFalse(futuro.result(timeout=2))
        self.assertEqual(a.sessao.recomendacoes,[]);self.assertFalse(a.sessao.streaming.ativo)
    def test_espera_por_mesma_chave_expira_sem_duplicar_ou_cachear_falso_sucesso(self):
        gate=threading.Event();release=threading.Event();calls=[]
        def abrir(req,timeout):
            calls.append(1);gate.set();release.wait(2);return Resposta(req.full_url,payload())
        c=self.cliente(abrir)
        with ThreadPoolExecutor(max_workers=1) as pool:
            futuro=pool.submit(c.obter,conteudo_movielens(1))
            try:
                self.assertTrue(gate.wait(1))
                with usar_prazo(Prazo(time.monotonic(),.03)):
                    r=c.obter_controlado(conteudo_movielens(1),permitir_consulta=True)
                self.assertEqual(r.disponibilidade.motivo,'TIMEOUT');self.assertEqual(r.chamadas_transporte,0)
                self.assertEqual(len(calls),1)
            finally:release.set()
            self.assertIs(futuro.result(timeout=2).estado,Estado.CONFIRMADA)
        self.assertIs(c.obter(conteudo_movielens(1)).estado,Estado.CONFIRMADA)

    def test_recupera_de_timeout_e_resposta_de_sessao_e_destacada(self):
        from datetime import timedelta
        tick=[0.];hora=[datetime.now(timezone.utc)];calls=[]
        def abrir(req,timeout):
            calls.append(1)
            if len(calls)==1:raise TimeoutError(TOKEN)
            return Resposta(req.full_url,payload())
        c=self.cliente(abrir,relogio=lambda:hora[0],monotono=lambda:tick[0])
        self.assertEqual(c.obter(conteudo_movielens(1)).motivo,'TIMEOUT')
        tick[0]=61;hora[0]+=timedelta(seconds=61)
        self.assertIs(c.obter(conteudo_movielens(1)).estado,Estado.CONFIRMADA)
        estado=EstadoSessao(Sessao());resposta=estado.executar(lambda s:s.assistidos,mutacao=False)
        resposta.append(99);self.assertNotIn(99,estado.sessao.assistidos)
        anterior=estado.snapshot()
        def erro(s):s.assistidos.append(1);raise ValueError('erro sintético')
        with self.assertRaises(ValueError):estado.executar(erro)
        self.assertFalse(estado.aplicar(anterior,lambda s:None))

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
            if d.get('texto')=='LENTO':gate.set();release.wait(2)
            return original(c,s,d)
        with patch.object(Handler,'modelo',fixture()),patch.object(Handler,'sessoes',{}),patch.object(Handler,'_estados',{}):
            _,ca=post({'acao':'estado'});_,cb=post({'acao':'estado'})
            with patch.object(Conversa,'executar',lento),ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(post,{'texto':'LENTO'},ca)
                try:
                    self.assertTrue(gate.wait(1));inicio=time.monotonic()
                    b=pool.submit(post,{'acao':'confirmar_selecao','ids':[1]},cb).result(timeout=1)
                    self.assertTrue(b[0]['referencias']);self.assertFalse(a.done())
                    print('SIMULACAO '+json.dumps({'http_sessao_independente_segundos':time.monotonic()-inicio}))
                finally:release.set()
                a.result(timeout=2)


class ColetaCatalogoTests(unittest.TestCase):
    def test_sem_aprovacao_nao_constroi_transporte(self):
        with tempfile.TemporaryDirectory() as pasta,patch('coletar_catalogo.TransporteTMDB') as transporte:
            p=Path(pasta)/'aprovacoes.json';p.write_text('{}')
            with self.assertRaises(ValueError):coletar(p,Path(pasta)/'saida')
            transporte.assert_not_called()
    def aprovado(self,pasta):
        doc=Path(pasta)/'revisao.txt';doc.write_text('Aprovação exclusivamente sintética para testar a barreira.')
        p=Path(pasta)/'aprovacoes.json';p.write_text(json.dumps({'termos_aprovados':True,'autorizacao_operacional':True,
            'responsavel':'REVISOR FICTÍCIO','aprovado_em':'2026-10-01T00:00:00+00:00','escopo':['catalogo_filmes_BR'],
            'documentos':[{'arquivo':'revisao.txt','sha256':hashlib.sha256(doc.read_bytes()).hexdigest()}]}));return p
    def test_coleta_sintetica_evidencia_hash_candidatos_nunca_homologados(self):
        with tempfile.TemporaryDirectory() as pasta:
            p=self.aprovado(pasta);saida=Path(pasta)/'nova';t=Mock();t.consultar_catalogo.return_value={'results':[{'provider_id':10,'provider_name':'Alfa FICTÍCIO'}]}
            m=coletar(p,saida,transporte=t);t.consultar_catalogo.assert_called_once_with('BR','pt-BR')
            self.assertEqual(m['homologados'],0);self.assertEqual(carregar_catalogo(saida/'candidatos.json'),())
            for n,h in m['arquivos'].items():self.assertEqual(hashlib.sha256((saida/n).read_bytes()).hexdigest(),h)
            with self.assertRaises(ValueError):coletar(p,saida,transporte=t)
    def test_coleta_rejeita_ids_invalidos_duplicados_ou_documento_modificado(self):
        with tempfile.TemporaryDirectory() as pasta:
            p=self.aprovado(pasta);t=Mock()
            for items in [[{'provider_id':True,'provider_name':'X'}],[{'provider_id':10,'provider_name':'X'}]*2]:
                t.consultar_catalogo.return_value={'results':items}
                with self.assertRaises(ValueError):coletar(p,Path(pasta)/'saida',transporte=t)
            (Path(pasta)/'revisao.txt').write_text('Alterado')
            with self.assertRaises(ValueError):coletar(p,Path(pasta)/'saida',transporte=t)
