"""Pôsteres: respostas HTTP sintéticas, relógios injetados e cache temporário."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from email.utils import format_datetime
from http.client import IncompleteRead
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import traceback
import unittest
from unittest.mock import Mock,patch
import urllib.error

from posteres import Posteres,ErroPoster,SemRedirecionamentoPoster,PLACEHOLDER,IMAGE_BASE,TTL
from operacao_externa import ControleExterno,TravaRegistro
from tmdb_disponibilidade import ClienteDisponibilidadeTMDB
from identidades import conteudo_movielens
from testes_tmdb_disponibilidade import Resposta as RespostaDisponibilidade,payload

TOKEN='TOKEN_SINTETICO_PROTECAO_POSTER'
CONFIG={'images':{'secure_base_url':IMAGE_BASE,'poster_sizes':['w185','w342','w500']}}


class Resposta:
    def __init__(self,url,dados=None,*,bruto=None,headers=None,status=200,final=None):
        self.url=final or url;self.status=status
        self.headers={'Content-Type':'application/json; charset=utf-8',**(headers or {})}
        self.corpo=io.BytesIO(json.dumps(dados).encode() if bruto is None else bruto)
        self.pedidos=[];self.lidos=0;self.fechada=False
    def geturl(self):return self.url
    def __enter__(self):return self
    def __exit__(self,*a):self.fechada=True;self.corpo.close()
    def read(self,n):
        self.pedidos.append(n);r=self.corpo.read(n);self.lidos+=len(r);return r


class ProtecaoPosteresTests(unittest.TestCase):
    def setUp(self):
        self.hora=1000.;self.tick=0.;self.calls=[]
        p=patch('socket.create_connection',side_effect=AssertionError('Rede real proibida'))
        p.start();self.addCleanup(p.stop)
    def dados(self,i):return {'id':i,'poster_path':f'/p{i}.jpg','images':{'posters':[]}}
    def responder(self,req,timeout):
        self.calls.append(req.full_url)
        dados=CONFIG if req.full_url.endswith('/configuration') else self.dados(int(req.full_url.split('/movie/')[1].split('?')[0]))
        return Resposta(req.full_url,dados)
    def esperar(self,t):self.tick+=t
    def servico(self,**opcoes):
        valores=dict(abrir=self.responder,relogio=lambda:self.hora,
            controle=ControleExterno(relogio=lambda:self.tick),monotono=lambda:self.tick,esperar=self.esperar)
        valores.update(opcoes)
        return Posteres({1:100,2:200,3:300},TOKEN,**valores)
    def config(self):return {'expira':self.hora+TTL,'tamanhos':['w185','w342','w500']}
    def test_hit_durante_consulta_lenta_e_filme_diferente_independente(self):
        gate=threading.Event();release=threading.Event();p=None
        def abrir(req,timeout):
            self.assertFalse(p.trava._is_owned());self.assertFalse(p._disco_trava._is_owned())
            if '/movie/200?' in req.full_url:gate.set();release.wait(2)
            return self.responder(req,timeout)
        p=self.servico(abrir=abrir);p.cache={'filme:100':{'poster_path':'/existente.jpg','expira':self.hora+TTL},'config':self.config()}
        with ThreadPoolExecutor(max_workers=2) as pool:
            lento=pool.submit(p.obter,2)
            try:
                self.assertTrue(gate.wait(1));inicio=time.monotonic()
                self.assertIn('/existente.jpg',p.obter(1)['poster_url']);latencia=time.monotonic()-inicio
                outro=pool.submit(p.obter,3).result(timeout=1)
                self.assertIn('/p300.jpg',outro['poster_url']);self.assertFalse(lento.done())
                print('SIMULACAO_POSTER '+json.dumps({'cache_durante_rede_segundos':latencia,'pico_externo':p.controle.pico}))
            finally:release.set()
            self.assertIn('/p200.jpg',lento.result(timeout=2)['poster_url'])
    def test_mesmo_filme_deduplicado(self):
        p=self.servico();p.cache['config']=self.config();barreira=threading.Barrier(8)
        def obter(_):barreira.wait(2);return p.obter(1)
        with ThreadPoolExecutor(max_workers=8) as pool:r=list(pool.map(obter,range(8)))
        self.assertEqual(len(self.calls),1);self.assertTrue(all(x==r[0] for x in r));self.assertEqual(p.controle.em_andamento,0)
    def test_config_deduplicada_entre_filmes(self):
        p=self.servico()
        with ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(p.obter,(1,2)))
        self.assertEqual(sum(u.endswith('/configuration') for u in self.calls),1)
        self.assertEqual(len(self.calls),3);self.assertTrue(all(x['poster_url']!=PLACEHOLDER for x in r))
    def test_gravacao_simultanea_na_instancia_e_entre_instancias(self):
        for mesma in (True,False):
            with self.subTest(mesma=mesma),tempfile.TemporaryDirectory() as pasta:
                path=Path(pasta)/'cache.json';path.write_text(json.dumps({'versao':1,'entradas':{'config':self.config(),'filme:999':{'poster_path':None,'expira':1234}}}))
                a=self.servico(cache=path);b=a if mesma else self.servico(cache=path)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    x=pool.submit(a.obter,1);y=pool.submit(b.obter,2);x.result(timeout=3);y.result(timeout=3)
                dados=json.loads(path.read_text());self.assertEqual(dados['versao'],1)
                self.assertTrue({'filme:100','filme:200','filme:999','config'}<=set(dados['entradas']))
                self.assertEqual(list(Path(pasta).glob('.*.tmp')),[])
    def test_falhas_de_write_fsync_replace_preservam_arquivo_antigo(self):
        for etapa in ('json.dump','os.fsync','Path.replace'):
            with self.subTest(etapa=etapa),tempfile.TemporaryDirectory() as pasta:
                path=Path(pasta)/'cache.json';original=json.dumps({'versao':1,'entradas':{'config':self.config(),'legado':{'expira':1}}}).encode();path.write_bytes(original)
                p=self.servico(cache=path)
                def parcial(obj,f,**kwargs):f.write('{"versao":');raise OSError(TOKEN)
                alvo={'json.dump':'posteres.json.dump','os.fsync':'posteres.os.fsync','Path.replace':'pathlib.Path.replace'}[etapa]
                opts={'side_effect':parcial} if etapa=='json.dump' else {'side_effect':OSError(TOKEN)}
                with patch(alvo,**opts):r=p.obter(1)
                self.assertIn('/p100.jpg',r['poster_url']);self.assertEqual(path.read_bytes(),original)
                self.assertEqual(list(Path(pasta).glob('.*.tmp')),[])
                p.obter(2);self.assertTrue({'filme:100','filme:200'}<=set(json.loads(path.read_text())['entradas']))
    def test_escrita_lenta_nao_bloqueia_hit_e_serializa_escritores(self):
        with tempfile.TemporaryDirectory() as pasta:
            path=Path(pasta)/'cache.json'
            path.write_text(json.dumps({'versao':1,'entradas':{'config':self.config(),
                'filme:100':{'poster_path':'/ja.jpg','expira':self.hora+TTL}}}))
            p=self.servico(cache=path);gate=threading.Event();release=threading.Event()
            dump=json.dump;ativas=[0];pico=[0];n=[0]
            def lento(obj,f,**kwargs):
                ativas[0]+=1;pico[0]=max(pico[0],ativas[0]);n[0]+=1
                try:
                    if n[0]==1:gate.set();release.wait(2)
                    return dump(obj,f,**kwargs)
                finally:ativas[0]-=1
            with patch('posteres.json.dump',side_effect=lento),ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(p.obter,2)
                try:
                    self.assertTrue(gate.wait(1));inicio=time.monotonic()
                    self.assertIn('/ja.jpg',p.obter(1)['poster_url'])
                    print('SIMULACAO_POSTER '+json.dumps({'cache_durante_disco_segundos':time.monotonic()-inicio}))
                    b=pool.submit(p.obter,3)
                    self.assertFalse(a.done())
                finally:release.set()
                a.result(timeout=3);b.result(timeout=3)
            self.assertEqual(pico[0],1)
            self.assertTrue({'filme:100','filme:200','filme:300'}<=set(json.loads(path.read_text())['entradas']))

    def test_cache_legado_hit_nao_regrava_e_temporario_interrompido_e_ignorado(self):
        with tempfile.TemporaryDirectory() as pasta:
            path=Path(pasta)/'cache.json';temp=path.with_suffix('.tmp');temp.write_text('{interrompido')
            path.write_text(json.dumps({'versao':1,'entradas':{'config':self.config(),'filme:100':{'poster_path':'/antigo.jpg','expira':self.hora+TTL}}}))
            h=hashlib.sha256(path.read_bytes()).hexdigest();p=self.servico(cache=path)
            self.assertIn('/antigo.jpg',p.obter(1)['poster_url']);self.assertEqual(self.calls,[])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),h);self.assertEqual(temp.read_text(),'{interrompido')
    def test_capacidade_persistencia_e_ttls(self):
        with tempfile.TemporaryDirectory() as pasta:
            path=Path(pasta)/'cache.json';p=self.servico(cache=path)
            p.cache={f'legado:{i}':{'expira':1} for i in range(2001)}
            p.obter(1)
            self.assertEqual(p.cache['filme:100']['expira'],self.hora+7*24*3600)
            self.assertEqual(p.cache['config']['expira'],self.hora+TTL)
            self.assertEqual(len(json.loads(path.read_text())['entradas']),2000)
    def test_sem_poster_e_404_preservam_ttls_distintos(self):
        p=self.servico(abrir=lambda req,timeout:Resposta(req.full_url,{'id':100,'poster_path':None}))
        self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER);self.assertEqual(p.cache['filme:100']['expira'],self.hora+TTL)
        def abrir(req,timeout):raise urllib.error.HTTPError(req.full_url,404,TOKEN,{},None)
        p=self.servico(abrir=abrir);self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
        self.assertEqual(p.cache['filme:100']['expira'],self.hora+86400);self.assertEqual(p.pausa_ate,0)
    def test_tamanho_limitado_durante_leitura_e_content_length(self):
        for headers in ({},{'Content-Length':'9999999'}):
            resposta=Resposta('x',bruto=b' '*10000,headers=headers)
            def abrir(req,timeout):resposta.url=req.full_url;return resposta
            p=self.servico(abrir=abrir,max_bytes=100)
            self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER);self.assertTrue(resposta.fechada)
            self.assertLessEqual(resposta.lidos,101)
            if headers:self.assertEqual(resposta.pedidos,[])
            else:self.assertTrue(all(0<n<=101 for n in resposta.pedidos))
            self.assertEqual(p.controle.em_andamento,0)
    def test_mime_status_corpo_invalido_ou_interrompido(self):
        ruins=[dict(headers={'Content-Type':'text/html'}),dict(headers={'Content-Type':''}),dict(status=204),
            dict(status=302,headers={'Location':'http://127.0.0.1/'}),dict(status=True),dict(status=999),
            dict(headers={'Content-Length':'-1'}),dict(headers={'Content-Length':'abc'}),dict(headers={'Content-Length':'900'}),
            dict(bruto=b'{'),dict(bruto=b'[]'),dict(bruto=b'\xff'),
            dict(bruto=b'['*2000+b'0'+b']'*2000)]
        for opcoes in ruins:
            with self.subTest(opcoes=opcoes):
                r=Resposta('x',self.dados(100),**opcoes)
                def abrir(req,timeout):r.url=req.full_url;return r
                p=self.servico(abrir=abrir);self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
                self.assertTrue(r.fechada);self.assertEqual(p.controle.em_andamento,0);self.assertNotIn('filme:100',p.cache)
        r=Resposta('x',self.dados(100))
        def abrir(req,timeout):r.url=req.full_url;return r
        p=self.servico(abrir=abrir)
        with patch('posteres.json.loads',side_effect=RecursionError(TOKEN)):
            self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
        self.assertTrue(r.fechada);self.assertNotIn('filme:100',p.cache)
        p=self.servico(abrir=Mock(side_effect=IncompleteRead(TOKEN.encode(),100)))
        self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER);self.assertEqual(p.controle.em_andamento,0)
    def test_redirecionamentos_e_destinos_nao_autorizados(self):
        with self.assertRaisesRegex(ErroPoster,'REDIRECIONAMENTO'):
            SemRedirecionamentoPoster().redirect_request(None,None,302,'',{},'http://169.254.169.254/')
        for destino in ('http://127.0.0.1','https://evil.test','https://api.themoviedb.org/3/outro'):
            p=self.servico(abrir=lambda req,timeout:Resposta(req.full_url,self.dados(100),final=destino))
            self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
        abrir=Mock();p=self.servico(abrir=abrir)
        for rota in ('http://127.0.0.1','//evil.test','/movie/1/../../config','/configuration?url=http://localhost'):
            with self.assertRaises(ErroPoster):p._json(rota)
        abrir.assert_not_called()
    def test_timeout_erro_rede_recuperacao_e_falhas_nao_persistidas(self):
        for erro in (TimeoutError(TOKEN),urllib.error.URLError(TOKEN),ConnectionResetError(TOKEN)):
            with self.subTest(erro=type(erro).__name__),tempfile.TemporaryDirectory() as pasta:
                path=Path(pasta)/'cache.json';p=self.servico(cache=path,abrir=Mock(side_effect=erro))
                self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER);self.assertFalse(path.exists())
                self.assertEqual(p.controle.em_andamento,0);self.hora+=61;self.tick+=61
                p.abrir=self.responder;self.assertIn('/p100.jpg',p.obter(1)['poster_url'])
    def test_429_retry_after_e_quota_compartilhada_com_disponibilidade(self):
        ctrl=ControleExterno(relogio=lambda:self.tick)
        def erro(req,timeout):raise urllib.error.HTTPError(req.full_url,429,TOKEN,{'Retry-After':'120'},None)
        p=self.servico(abrir=erro,controle=ctrl);self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
        calls=[]
        def disponibilidade(req,timeout):calls.append(1);return RespostaDisponibilidade(req.full_url,payload())
        with patch.dict('os.environ',{'TMDB_READ_ACCESS_TOKEN':TOKEN}):
            c=ClienteDisponibilidadeTMDB({conteudo_movielens(1):100},habilitado=True,termos_aprovados=True,
                abrir=disponibilidade,controle=ctrl,monotono=lambda:self.tick)
        self.assertEqual(c.obter(conteudo_movielens(1)).motivo,'CONSULTA_SUSPENSA');self.assertEqual(calls,[])
        self.hora+=121;self.tick+=121;p.abrir=self.responder
        self.assertIn('/p100.jpg',p.obter(1)['poster_url']);self.assertEqual(ctrl.em_andamento,0)
    def test_orcamento_esgotado_e_trava_global_nao_abrem_rede(self):
        abrir=Mock();p=self.servico(abrir=abrir,controle=ControleExterno(chamadas=1))
        with p.controle.admitir():pass
        self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER);abrir.assert_not_called()
        p=self.servico(abrir=abrir)
        with TravaRegistro():self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
        abrir.assert_not_called()
    def test_segredos_nao_vazam_em_erros_corpo_cache_ou_url(self):
        for dados in ({**self.dados(100),'privado':TOKEN},):
            p=self.servico(abrir=lambda req,timeout:Resposta(req.full_url,dados))
            self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER);self.assertNotIn(TOKEN,json.dumps(p.cache))
        def erro(req,timeout):raise urllib.error.HTTPError('https://evil.test/'+TOKEN,401,TOKEN,{},None)
        p=self.servico(abrir=erro)
        with self.assertRaises(ErroPoster) as e:p._json('/configuration')
        self.assertNotIn(TOKEN,''.join(traceback.format_exception(e.exception)))
        p=self.servico();p.obter(1);self.assertTrue(all(TOKEN not in u for u in self.calls))
    def test_eco_unicode_e_credencial_invalida(self):
        body=json.dumps({**self.dados(100),'privado':TOKEN}).replace(TOKEN,'\\u0054'+TOKEN[1:]).encode()
        p=self.servico(abrir=lambda req,timeout:Resposta(req.full_url,bruto=body));self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
        abrir=Mock();p=Posteres({1:100},'x\r\nX: segredo',abrir=abrir)
        self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER);abrir.assert_not_called()
    def test_ids_mapeados_invalidos_e_limites_invalidos(self):
        abrir=Mock()
        for i in (True,-1,0,'100/../config'):
            p=Posteres({1:i},TOKEN,abrir=abrir);self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
        abrir.assert_not_called()
        for op in ({'timeout':0},{'timeout':True},{'max_bytes':0},{'max_bytes':True}):
            with self.assertRaises(ValueError):self.servico(**op)
    def test_urls_legitimas_preservadas_e_sem_download_de_imagem(self):
        p=self.servico();r=p.obter(1)
        self.assertEqual(r,{'poster_url':IMAGE_BASE+'w342/p100.jpg','thumbnail_url':IMAGE_BASE+'w185/p100.jpg','tmdbId':100})
        self.assertTrue(all(u.startswith('https://api.themoviedb.org/3/') for u in self.calls))
        self.assertEqual(len(self.calls),2)

    def test_leitura_em_blocos_valida_sem_read_ilimitado(self):
        corpo=json.dumps({'images':{},'extra':'x'*70000}).encode()
        resposta=Resposta('x',bruto=corpo,headers={'Content-Length':str(len(corpo))})
        def abrir(req,timeout):resposta.url=req.full_url;return resposta
        p=self.servico(abrir=abrir)
        dados=p._json('/configuration')
        self.assertEqual(len(dados['extra']),70000);self.assertTrue(resposta.fechada)
        self.assertTrue(all(0<n<=65536 for n in resposta.pedidos));self.assertGreater(len(resposta.pedidos),2)

    def test_interrupcao_durante_read_e_http_error_fecham_recursos(self):
        class Interrompida(Resposta):
            def read(self,n):
                if self.pedidos:raise ConnectionResetError(TOKEN)
                self.pedidos.append(n);return b'{'
        r=Interrompida('x',{})
        def abrir(req,timeout):r.url=req.full_url;return r
        p=self.servico(abrir=abrir)
        self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
        self.assertTrue(r.fechada);self.assertEqual(p.controle.em_andamento,0);self.assertNotIn('filme:100',p.cache)
        corpo=io.BytesIO('erro sintético'.encode())
        erro=urllib.error.HTTPError('https://api.themoviedb.org',403,TOKEN,{},corpo)
        p=self.servico(abrir=Mock(side_effect=erro));self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
        self.assertTrue(corpo.closed);self.assertEqual(p.controle.em_andamento,0)

    def test_retry_after_data_http_respeita_pausa_e_recupera(self):
        data=format_datetime(datetime.fromtimestamp(self.hora+120,tz=timezone.utc))
        def abrir(req,timeout):raise urllib.error.HTTPError(req.full_url,429,TOKEN,{'Retry-After':data},None)
        p=self.servico(abrir=abrir);self.assertEqual(p.obter(1)['poster_url'],PLACEHOLDER)
        self.assertEqual(p.pausa_ate,self.hora+120)
        self.hora+=121;self.tick+=121;p.abrir=self.responder
        self.assertIn('/p100.jpg',p.obter(1)['poster_url']);self.assertEqual(p.controle.em_andamento,0)
