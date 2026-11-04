"""RF-02B: HTTP injetado, relógio controlado, nenhum acesso real à rede."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.client import IncompleteRead
import io
import json
import threading
import traceback
import unittest
from unittest.mock import Mock, patch
import urllib.error
from urllib.parse import parse_qs, urlparse

from disponibilidade import Estado, Modalidade, FalhaConsulta
from identidades import conteudo_movielens, IdentidadeConteudo, TipoConteudo
from tmdb_disponibilidade import ClienteDisponibilidadeTMDB, TransporteTMDB, SemRedirecionamento

TOKEN = 'CREDENCIAL_SINTETICA_SOMENTE_TESTE'


def payload(i=100):
    return {'id':i,'results':{'BR':{'flatrate':[{'provider_id':10,'provider_name':'Serviço sintético'}],
        'rent':[{'provider_id':20,'provider_name':'Aluguel sintético'}]}}}


class Resposta:
    def __init__(self,url,dados,*,status=200,headers=None,bruto=None):
        self.url,self.status = url,status
        self.headers = {'Content-Type':'application/json; charset=utf-8',**(headers or {})}
        self.corpo = io.BytesIO(json.dumps(dados).encode() if bruto is None else bruto)
        self.fechada = False
    def __enter__(self): return self
    def __exit__(self,*a): self.fechada=True
    def geturl(self): return self.url
    def read(self,n): return self.corpo.read(n)


class TransporteDisponibilidadeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict('os.environ',{'TMDB_READ_ACCESS_TOKEN':TOKEN})
        self.env.start(); self.addCleanup(self.env.stop)
        rede = patch('socket.create_connection',side_effect=AssertionError('Rede real proibida'))
        rede.start(); self.addCleanup(rede.stop)
        self.hora = datetime(2026,10,29,12,tzinfo=timezone.utc)
        self.tick = 0.
        self.calls = []
        self.dados = payload()
        self.abrir = Mock(side_effect=self.responder)
        self.links = {conteudo_movielens(1):100,conteudo_movielens(2):200}

    def responder(self,pedido,timeout):
        self.calls.append((pedido,timeout))
        return Resposta(pedido.full_url,self.dados)

    def esperar(self,segundos): self.tick+=segundos

    def cliente(self,**opcoes):
        valores = dict(habilitado=True,termos_aprovados=True,abrir=self.abrir,
            relogio=lambda:self.hora,monotono=lambda:self.tick,esperar=self.esperar)
        valores.update(opcoes)
        return ClienteDisponibilidadeTMDB(self.links,**valores)

    def test_desativado_por_padrao_sem_chamadas_iniciais(self):
        # Também constrói o opener padrão real, mas a trava de habilitação
        # impede qualquer rede (socket.create_connection está sentinela).
        padrao = ClienteDisponibilidadeTMDB(self.links)
        self.assertEqual(padrao.obter(conteudo_movielens(1)).motivo,'INTEGRACAO_DESATIVADA')
        c = ClienteDisponibilidadeTMDB(self.links,abrir=self.abrir)
        self.abrir.assert_not_called()
        self.assertEqual(c.obter(conteudo_movielens(1)).motivo,'INTEGRACAO_DESATIVADA')
        self.assertEqual(c.provedores().motivo,'INTEGRACAO_DESATIVADA')
        self.abrir.assert_not_called()

    def test_duas_aprovacoes_explicitas_necessarias(self):
        for flags in ({'habilitado':False},{'termos_aprovados':False}):
            c = self.cliente(**flags)
            self.assertEqual(c.obter(conteudo_movielens(1)).motivo,'INTEGRACAO_DESATIVADA')
        self.abrir.assert_not_called()

    def test_credencial_ausente_ou_injecao_de_cabecalho(self):
        for token,codigo in (('','SEM_CREDENCIAL'),('abc\r\nX: valor','CREDENCIAL_INVALIDA')):
            with patch.dict('os.environ',{'TMDB_READ_ACCESS_TOKEN':token}):
                d = self.cliente().obter(conteudo_movielens(1))
                self.assertEqual(d.motivo,codigo)
        self.abrir.assert_not_called()

    def test_requisicao_filme_https_id_mapeado_e_token_so_cabecalho(self):
        c = self.cliente(timeout=1.5)
        d = c.obter(conteudo_movielens(1))
        req,timeout = self.calls[0]
        self.assertEqual(req.full_url,'https://api.themoviedb.org/3/movie/100/watch/providers')
        self.assertEqual(req.get_method(),'GET')
        self.assertEqual(req.get_header('Authorization'),'Bearer '+TOKEN)
        self.assertEqual(timeout,1.5)
        self.assertNotIn(TOKEN,req.full_url)
        self.assertNotIn(TOKEN,repr(d))
        self.assertIs(d.estado,Estado.CONFIRMADA)
        self.assertEqual({o.modalidade for o in d.ofertas},{Modalidade.ASSINATURA,Modalidade.ALUGUEL})

    def test_catalogo_br_idioma_separado_e_ids(self):
        self.dados = {'results':[{'provider_id':20,'provider_name':'Mesmo nome'},
            {'provider_id':10,'provider_name':'Mesmo nome'}]}
        d = self.cliente().provedores(idioma='en-US')
        u = urlparse(self.calls[0][0].full_url)
        self.assertEqual(u.path,'/3/watch/providers/movie')
        self.assertEqual(parse_qs(u.query),{'watch_region':['BR'],'language':['en-US']})
        self.assertEqual(d.regiao,'BR'); self.assertEqual(d.idioma,'en-US')
        self.assertEqual(d.provedores,((10,'Mesmo nome'),(20,'Mesmo nome')))

    def test_cinco_modalidades_por_pais(self):
        self.dados = {'id':100,'results':{'US':{'flatrate':[{'provider_id':1,'provider_name':'US'}]},
            'BR':{m.value:[{'provider_id':10,'provider_name':'BR'}] for m in Modalidade}}}
        c = self.cliente()
        d = c.obter(conteudo_movielens(1))
        self.assertEqual({o.modalidade for o in d.ofertas},set(Modalidade))
        self.assertEqual({o.provedor_id for o in d.ofertas},{10})
        self.assertEqual(c.obter(conteudo_movielens(1),'US').ofertas[0].provedor_id,1)

    def test_sem_regiao_e_catalogo_vazio_nao_sao_indisponibilidade(self):
        self.dados = {'id':100,'results':{'US':{}}}
        c = self.cliente()
        d = c.obter(conteudo_movielens(1))
        self.assertIs(d.estado,Estado.DESCONHECIDA)
        self.assertEqual(d.motivo,'SEM_DADOS_REGIAO')
        self.assertFalse(d.ausencia_confirmada)
        self.dados = {'results':[]}
        self.assertIs(c.provedores().estado,Estado.DESCONHECIDA)

    def test_sem_id_series_e_ids_injetados_nao_consultam(self):
        c = self.cliente()
        self.assertEqual(c.obter(conteudo_movielens(999)).motivo,'SEM_MAPEAMENTO_TMDB')
        serie = IdentidadeConteudo('movielens',TipoConteudo.SERIE,'1')
        self.assertEqual(c.obter(serie).motivo,'TIPO_NAO_SUPORTADO')
        for i in (True,'100',100.5,999,-1):
            with self.assertRaises(ValueError): c._transporte.consultar_filme(i)
        for regiao in ('br','BR&x=1','https://evil.test'):
            with self.assertRaises(ValueError): c.provedores(regiao)
        with self.assertRaises(ValueError): c.provedores(idioma='pt-BR&token=1')
        self.abrir.assert_not_called()

    def test_http_401_403_404_429_5xx_distintos_sem_token(self):
        for status,motivo in ((401,'HTTP_401'),(403,'HTTP_403'),(404,'HTTP_404'),
                              (429,'HTTP_429'),(500,'HTTP_5XX'),(503,'HTTP_5XX'),(400,'HTTP_OUTRO')):
            with self.subTest(status=status):
                self.abrir.side_effect = urllib.error.HTTPError('https://api.themoviedb.org/'+TOKEN,
                    status,TOKEN,{},io.BytesIO(TOKEN.encode()))
                d = self.cliente().obter(conteudo_movielens(1))
                self.assertEqual(d.motivo,motivo)
                self.assertIs(d.estado,Estado.ERRO)
                self.assertEqual(d.ofertas,())
                self.assertNotIn(TOKEN,repr(d))

    def test_retry_after_segundos_data_e_sem_repeticao_automatica(self):
        base = self.hora
        for valor in ('120',format_datetime(self.hora+timedelta(seconds=120),usegmt=True),'inválido'):
            with self.subTest(valor=valor):
                self.hora=base
                self.tick=0
                self.abrir.reset_mock()
                self.abrir.side_effect = urllib.error.HTTPError('https://api.themoviedb.org',429,'erro',{'Retry-After':valor},None)
                c = self.cliente()
                self.assertEqual(c.obter(conteudo_movielens(1)).motivo,'HTTP_429')
                self.assertEqual(self.abrir.call_count,1)
                self.hora+=timedelta(seconds=61); self.tick=61
                motivo=c.obter(conteudo_movielens(1)).motivo
                if valor!='inválido':
                    self.assertEqual(motivo,'CONSULTA_SUSPENSA')
                    self.assertEqual(self.abrir.call_count,1)
                else:
                    self.assertEqual(motivo,'HTTP_429')
                    self.assertEqual(self.abrir.call_count,2)

    def test_timeout_e_conexao_simulados(self):
        for erro,codigo in ((TimeoutError(TOKEN),'TIMEOUT'),
                (urllib.error.URLError(TimeoutError(TOKEN)),'TIMEOUT'),
                (urllib.error.URLError(TOKEN),'CONEXAO'),(OSError(TOKEN),'CONEXAO')):
            self.abrir.side_effect=erro
            d=self.cliente().obter(conteudo_movielens(1))
            self.assertEqual(d.motivo,codigo)
            self.assertNotIn(TOKEN,repr(d))

    def test_json_invalido_incompleto_mime_tamanho_e_eco_credencial(self):
        casos = (({},None,{}),([],None,{}),(payload(),b'invalido',{}),
            (payload(),None,{'Content-Type':'text/html'}),
            (payload(),b' '*1025,{}),(payload(),None,{'Content-Length':'1025'}),
            (payload(),json.dumps({'eco':TOKEN}).encode(),{}))
        for dados,bruto,headers in casos:
            with self.subTest(dados=dados,headers=headers):
                self.abrir.side_effect=lambda req,timeout:Resposta(req.full_url,dados,bruto=bruto,headers=headers)
                d=self.cliente(max_bytes=1024).obter(conteudo_movielens(1))
                self.assertIs(d.estado,Estado.ERRO)
                self.assertNotIn(TOKEN,repr(d))

    def test_redirecionamento_bloqueado_antes_de_reencaminhar_token(self):
        with self.assertRaisesRegex(FalhaConsulta,'REDIRECIONAMENTO_BLOQUEADO'):
            SemRedirecionamento().redirect_request(None,None,302,'Found',{},'https://evil.test')
        self.abrir.side_effect=lambda req,timeout:Resposta('https://evil.test',payload())
        d=self.cliente().obter(conteudo_movielens(1))
        self.assertEqual(d.motivo,'REDIRECIONAMENTO_BLOQUEADO')

    def test_cache_disponibilidade_expira_sem_reusar_sucesso_apos_falha(self):
        c=self.cliente()
        a=c.obter(conteudo_movielens(1)); self.assertIs(c.obter(conteudo_movielens(1)),a)
        self.assertEqual(self.abrir.call_count,1)
        self.hora=a.expira_em; self.tick+=86400
        self.abrir.side_effect=TimeoutError('offline')
        erro=c.obter(conteudo_movielens(1))
        self.assertEqual(erro.motivo,'TIMEOUT'); self.assertEqual(erro.ofertas,())
        self.assertEqual(self.abrir.call_count,2)

    def test_cache_catalogo_expira_e_separa_pais_idioma(self):
        self.dados={'results':[{'provider_id':10,'provider_name':'X'}]}
        c=self.cliente(limite_catalogo=2)
        a=c.provedores(); self.assertIs(c.provedores(),a)
        c.provedores('US');c.provedores('BR','en-US')
        self.assertEqual(self.abrir.call_count,3)
        self.assertEqual(len(c._catalogos),2)
        c.provedores();self.assertEqual(self.abrir.call_count,4)
        self.hora+=timedelta(hours=24);self.tick+=86400
        c.provedores();self.assertEqual(self.abrir.call_count,5)

    def test_isolamento_filmes_e_regioes(self):
        def responder(req,timeout):
            i=int(req.full_url.split('/movie/')[1].split('/')[0])
            return Resposta(req.full_url,payload(i))
        self.abrir.side_effect=responder
        c=self.cliente()
        self.assertEqual(c.obter(conteudo_movielens(1)).tmdb_id,100)
        self.assertEqual(c.obter(conteudo_movielens(2)).tmdb_id,200)
        self.assertIs(c.obter(conteudo_movielens(1),'US').estado,Estado.DESCONHECIDA)
        c.obter(conteudo_movielens(1));self.assertEqual(self.abrir.call_count,3)

    def test_concorrencia_mesma_chave_uma_chamada(self):
        c=self.cliente()
        barreira=threading.Barrier(8)
        def obter(_):
            barreira.wait(timeout=5)
            return c.obter(conteudo_movielens(1))
        with ThreadPoolExecutor(max_workers=8) as pool:
            resultados=list(pool.map(obter,range(8)))
        self.assertEqual(self.abrir.call_count,1)
        self.assertTrue(all(d is resultados[0] for d in resultados))

    def test_excecao_direta_transporte_sanitizada(self):
        self.abrir.side_effect=urllib.error.HTTPError('https://api.themoviedb.org/'+TOKEN,401,TOKEN,{},None)
        with self.assertRaises(FalhaConsulta) as e:
            self.cliente()._transporte.consultar_filme(100)
        self.assertEqual(str(e.exception),'HTTP_401')
        self.assertNotIn(TOKEN,str(e.exception))
        self.assertNotIn(TOKEN,''.join(traceback.format_exception(e.exception)))

    def test_eco_credencial_escapado_no_json_e_rejeitado(self):
        dados=payload()
        dados['results']['BR']['flatrate'][0]['provider_name']=TOKEN
        corpo=json.dumps(dados).replace(TOKEN,'\\u0043'+TOKEN[1:]).encode()
        self.abrir.side_effect=lambda req,timeout:Resposta(req.full_url,None,bruto=corpo)
        d=self.cliente().obter(conteudo_movielens(1))
        self.assertEqual(d.motivo,'RESPOSTA_INVALIDA')
        self.assertNotIn(TOKEN,repr(d))

    def test_catalogo_concorrente_e_erro_cacheado(self):
        self.dados={'results':[{'provider_id':10,'provider_name':'X'}]}
        c=self.cliente()
        with ThreadPoolExecutor(max_workers=4) as pool:
            respostas=list(pool.map(lambda _:c.provedores(),range(4)))
        self.assertEqual(self.abrir.call_count,1)
        self.assertTrue(all(r is respostas[0] for r in respostas))
        self.hora+=timedelta(hours=24);self.tick+=86400
        self.abrir.side_effect=urllib.error.HTTPError('https://api.themoviedb.org',403,'erro',{},None)
        erro=c.provedores()
        self.assertEqual(erro.motivo,'HTTP_403')
        self.assertIs(c.provedores(),erro)
        self.assertEqual(self.abrir.call_count,2)

    def test_status_de_resposta_e_parametros_timeout_invalidos(self):
        self.abrir.side_effect=lambda req,timeout:Resposta(req.full_url,payload(),status=503)
        self.assertEqual(self.cliente().obter(conteudo_movielens(1)).motivo,'HTTP_5XX')
        for timeout in (0,-1,True,float('inf'),'3'):
            with self.subTest(timeout=timeout),self.assertRaises(ValueError): self.cliente(timeout=timeout)

    def test_corpo_truncado_e_comprimento_incoerente_sao_invalidos(self):
        self.abrir.side_effect=IncompleteRead(TOKEN.encode(),100)
        d=self.cliente().obter(conteudo_movielens(1))
        self.assertEqual(d.motivo,'RESPOSTA_INVALIDA')
        self.assertNotIn(TOKEN,repr(d))
        self.abrir.side_effect=lambda req,timeout:Resposta(req.full_url,payload(),headers={'Content-Length':'1000'})
        self.assertEqual(self.cliente().obter(conteudo_movielens(1)).motivo,'RESPOSTA_INVALIDA')


if __name__=='__main__':
    unittest.main()
