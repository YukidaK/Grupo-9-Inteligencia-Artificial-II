"""RF-02C isolada: candidatos e transporte exclusivamente sintéticos."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import io
import json
import os
import unittest
from unittest.mock import Mock, patch

from conversa import Sessao, Conversa
from disponibilidade import Disponibilidade, Oferta, Estado, Modalidade, ConsultaControlada
from preferencias_streaming import PreferenciasStreaming, Modo
from filtro_streaming import CandidatoStreaming, LimitesStreaming, filtrar_streaming
from identidades import conteudo_movielens, IdentidadeConteudo, TipoConteudo
from tmdb_disponibilidade import ClienteDisponibilidadeTMDB
from testes_conversa import fixture
import testes_tmdb_disponibilidade as http_fixture
from app import Handler


class ServicoSintetico:
    def __init__(self,respostas,cache=()):
        self.respostas=respostas
        self.cache=set(cache)
        self.chamadas=[]
    def obter_controlado(self,conteudo,regiao,*,permitir_consulta=False):
        chave=(conteudo,regiao)
        if chave in self.cache: return ConsultaControlada(self.respostas[chave],'CACHE')
        if not permitir_consulta: return ConsultaControlada(None,'NAO_VERIFICADO')
        self.chamadas.append(chave)
        self.cache.add(chave)
        return ConsultaControlada(self.respostas[chave],'CONSULTA',1)


class FiltroStreamingTests(unittest.TestCase):
    def setUp(self):
        self.hora=datetime(2026,10,29,12,tzinfo=timezone.utc)
        self.tick=0.
        rede=patch('socket.create_connection',side_effect=AssertionError('Rede real proibida'))
        rede.start();self.addCleanup(rede.stop)
    def candidato(self,i,score=None):
        return CandidatoStreaming.movielens({'movieId':i,'titulo':f'Filme {i}',
            'pontuacao':1.-i/100 if score is None else score})
    def dados(self,i,provedor=10,modalidade=Modalidade.ASSINATURA,estado=Estado.CONFIRMADA,regiao='BR'):
        ofertas=(Oferta(provedor,modalidade,'Serviço sintético'),) if estado is Estado.CONFIRMADA else ()
        return Disponibilidade(conteudo_movielens(i),100+i,regiao,self.hora,
            self.hora+timedelta(hours=1),estado,ofertas)
    def servico(self,lista,cache=()):
        return ServicoSintetico({(d.conteudo,d.regiao):d for d in lista},cache)
    def prefs(self,ids=(10,),**kw):
        return PreferenciasStreaming(frozenset(ids),ativo=True,**kw)
    def filtrar(self,candidatos,prefs,servico,**kw):
        return filtrar_streaming(candidatos,prefs,servico,relogio=lambda:self.hora,
            monotono=lambda:self.tick,**kw)
    def ids(self,r):return [x.candidato.dados['movieId'] for x in r.itens]

    def test_sessao_sem_configuracao_diferente_de_ativada_vazia(self):
        s=Sessao();self.assertIsNone(s.streaming)
        desativado=self.filtrar([self.candidato(1)],None,None)
        self.assertEqual(self.ids(desativado),[1]);self.assertFalse(desativado.configurado)
        vazio=self.filtrar([self.candidato(1)],self.prefs(()),None)
        self.assertEqual(self.ids(vazio),[]);self.assertTrue(vazio.ativo)
        self.assertIn('Selecione',vazio.mensagem)

    def test_configurar_preserva_estado_e_isola_sessoes(self):
        s=Sessao(assistidos=[1,2],referencias=[1],rejeitados={2},positivos={'Drama'},negativos={'Horror'})
        outra=Sessao()
        antes=(s.assistidos[:],s.referencias[:],s.rejeitados.copy(),s.positivos.copy(),s.negativos.copy())
        s.configurar_streaming(self.prefs((10,20)),provedores_permitidos=frozenset({10,20}),regiao_catalogo='BR')
        s.configurar_streaming(replace(s.streaming,ativo=False),provedores_permitidos=frozenset({10,20}),regiao_catalogo='BR')
        self.assertIsNone(outra.streaming)
        self.assertEqual(antes,(s.assistidos,s.referencias,s.rejeitados,s.positivos,s.negativos))
        self.assertEqual(s.streaming.modo,Modo.RESTRITO)
        self.assertFalse(s.streaming.ativo)

    def test_ids_invalidos_e_catalogo_regional_sem_mutacao(self):
        s=Sessao()
        for ids in ((True,),('10',),(-1,)):
            with self.assertRaises(ValueError):self.prefs(ids)
        for p,regiao in ((self.prefs((99,)),'BR'),(self.prefs(),'US')):
            with self.assertRaises(ValueError):
                s.configurar_streaming(p,provedores_permitidos=frozenset({10}),regiao_catalogo=regiao)
        self.assertIsNone(s.streaming)

    def test_assinaturas_diferentes_e_multiplas(self):
        lista=[self.dados(1,10),self.dados(2,20)]
        self.assertEqual(self.ids(self.filtrar([self.candidato(1),self.candidato(2)],self.prefs(),self.servico(lista))),[1])
        self.assertEqual(self.ids(self.filtrar([self.candidato(1),self.candidato(2)],self.prefs((20,)),self.servico(lista))),[2])
        self.assertEqual(self.ids(self.filtrar([self.candidato(1),self.candidato(2)],self.prefs((10,20)),self.servico(lista))),[1,2])

    def test_desativado_preserva_scores_ordem_e_nao_consulta(self):
        c=[self.candidato(4,.5),self.candidato(1,.5),self.candidato(3,.4)]
        r=self.filtrar(c,replace(self.prefs(),ativo=False),None)
        self.assertEqual(self.ids(r),[4,1,3])
        self.assertEqual([i.candidato.dados['pontuacao'] for i in r.itens],[.5,.5,.4])
        self.assertTrue(all(i.disponibilidade is None for i in r.itens))

    def test_ignora_aluguel_compra_gratis_ads_e_procura_apos_dez(self):
        dados=[self.dados(i,modalidade=Modalidade.ALUGUEL) for i in range(1,11)]
        dados += [self.dados(11),self.dados(12,modalidade=Modalidade.COMPRA),
                  self.dados(13,modalidade=Modalidade.GRATIS),self.dados(14,modalidade=Modalidade.ANUNCIOS)]
        r=self.filtrar([self.candidato(i) for i in range(1,15)],self.prefs(),self.servico(dados))
        self.assertEqual(self.ids(r),[11])
        self.assertEqual(r.estatisticas['confirmados_assinatura'],1)

    def test_desconhecido_erro_regiao_e_expirado_restrito(self):
        dados=[self.dados(1,estado=Estado.DESCONHECIDA),self.dados(2,estado=Estado.ERRO),
            replace(self.dados(3),consultado_em=self.hora-timedelta(days=2),expira_em=self.hora-timedelta(days=1)),
            self.dados(4)]
        r=self.filtrar([self.candidato(i) for i in range(1,5)],self.prefs(),self.servico(dados))
        self.assertEqual(self.ids(r),[4]);self.assertTrue(r.parcial)
        self.assertEqual(r.estatisticas['erros'],1)

    def test_flexivel_mantem_elegibilidade_sem_ofertas_vencidas(self):
        velho=replace(self.dados(1),consultado_em=self.hora-timedelta(days=2),expira_em=self.hora-timedelta(days=1))
        r=self.filtrar([self.candidato(1),self.candidato(2)],self.prefs(modo=Modo.FLEXIVEL),
            self.servico([velho,self.dados(2,estado=Estado.ERRO)]))
        self.assertEqual(self.ids(r),[1,2])
        self.assertEqual(r.itens[0].disponibilidade.ofertas,())
        self.assertIs(r.itens[0].disponibilidade.estado,Estado.DESCONHECIDA)
        self.assertIs(r.itens[1].disponibilidade.estado,Estado.ERRO)

    def test_orcamento_cache_nao_conta_e_continua_busca_limitada(self):
        dados=[self.dados(1,20),self.dados(2),self.dados(3)]
        servico=self.servico(dados,cache={(conteudo_movielens(3),'BR')})
        r=self.filtrar([self.candidato(i) for i in (1,2,3)],self.prefs(),servico,
            limites=LimitesStreaming(consultas=1))
        self.assertEqual(self.ids(r),[3])
        self.assertEqual(len(servico.chamadas),1)
        self.assertEqual(r.estatisticas['cache'],1)
        self.assertEqual(r.estatisticas['tentativas_orcadas'],1)
        self.assertEqual(r.estatisticas['consultas_necessarias'],2)
        self.assertTrue(r.parcial);self.assertIn('parcial',r.mensagem)

    def test_flexivel_orcamento_zero_mantem_dez_sem_consultar(self):
        servico=self.servico([])
        r=self.filtrar([self.candidato(i) for i in range(1,15)],self.prefs(modo=Modo.FLEXIVEL),servico,
            limites=LimitesStreaming(consultas=0))
        self.assertEqual(self.ids(r),list(range(1,11)))
        self.assertEqual(servico.chamadas,[])
        self.assertEqual(r.estatisticas['nao_verificados'],10)
        self.assertTrue(r.parcial)

    def test_limite_candidatos_nao_consumir_iterador_milhares(self):
        lidos=[]
        def gerar():
            for i in range(1,10000):
                lidos.append(i);yield self.candidato(i)
        r=self.filtrar(gerar(),self.prefs(),self.servico([]),
            limites=LimitesStreaming(consultas=0,candidatos=3))
        self.assertEqual(lidos,[1,2,3]);self.assertEqual(self.ids(r),[])
        self.assertIn('CANDIDATOS',r.limites_atingidos)

    def test_prazo_cooperativo_e_flexivel_nao_chama_servico(self):
        servico=self.servico([])
        r=self.filtrar([self.candidato(1)],self.prefs(),servico,limites=LimitesStreaming(segundos=0))
        self.assertEqual(r.itens,());self.assertEqual(servico.chamadas,[])
        r=self.filtrar([self.candidato(1)],self.prefs(modo=Modo.FLEXIVEL),servico,limites=LimitesStreaming(segundos=0))
        self.assertEqual(self.ids(r),[1]);self.assertEqual(servico.chamadas,[])
        self.assertEqual(r.itens[0].disponibilidade.motivo,'LIMITE_TEMPO')

    def test_sem_duplicatas_preserva_primeira_posicao_e_dados(self):
        c=self.candidato(1)
        r=self.filtrar([c,c,self.candidato(2)],None,None)
        self.assertEqual(self.ids(r),[1,2]);self.assertEqual(r.estatisticas['duplicatas'],1)
        r.itens[0].candidato.dados['titulo']='alterado'
        self.assertEqual(c.dados['titulo'],'Filme 1')

    def test_tipo_serie_e_limites_invalidos(self):
        with self.assertRaises(ValueError):
            CandidatoStreaming(IdentidadeConteudo('x',TipoConteudo.SERIE,'1'),{'pontuacao':1.})
        with self.assertRaises(ValueError):
            CandidatoStreaming(conteudo_movielens(2),{'movieId':1,'pontuacao':1.})
        for kw in ({'consultas':-1},{'consultas':True},{'candidatos':0},{'tamanho':11},{'segundos':float('inf')}):
            with self.assertRaises(ValueError):LimitesStreaming(**kw)

    def test_conversa_publica_ignora_configuracao_interna_e_mantem_json(self):
        c=Conversa(fixture());s=Sessao()
        antes=c.executar(s,{'acao':'confirmar_selecao','ids':[1,4]})
        s.configurar_streaming(self.prefs(),provedores_permitidos=frozenset({10}),regiao_catalogo='BR')
        depois=c.executar(s,{'acao':'estado'})
        self.assertEqual(set(antes),set(depois));self.assertNotIn('streaming',depois)
        self.assertEqual(antes['recomendacoes'],depois['recomendacoes'])
        c.executar(s,{'acao':'remover_referencia','movieId':1})
        d=c.executar(s,{'acao':'remover_referencia','movieId':4})
        self.assertEqual(d['recomendacoes'],[])
        self.assertTrue(s.streaming.ativo)

    def test_rf02b_controlado_nao_habilita_rede_e_conta_tentativas(self):
        with patch.dict(os.environ,{},clear=True):
            cliente=ClienteDisponibilidadeTMDB({conteudo_movielens(1):100},relogio=lambda:self.hora)
            r=self.filtrar([self.candidato(1)],self.prefs(),cliente)
            self.assertEqual(r.estatisticas['tentativas_orcadas'],1)
            self.assertEqual(r.estatisticas['chamadas_transporte'],0)
            self.assertEqual(r.estatisticas['erros'],1)

    def test_rf02b_stub_cache_e_consulta_contabilizados(self):
        abrir=Mock(side_effect=lambda req,timeout:http_fixture.Resposta(req.full_url,http_fixture.payload()))
        with patch.dict(os.environ,{'TMDB_READ_ACCESS_TOKEN':http_fixture.TOKEN}):
            cliente=ClienteDisponibilidadeTMDB({conteudo_movielens(1):100},habilitado=True,
                termos_aprovados=True,abrir=abrir,relogio=lambda:self.hora)
        r=self.filtrar([self.candidato(1)],self.prefs(),cliente)
        self.assertEqual(self.ids(r),[1]);self.assertEqual(r.estatisticas['chamadas_transporte'],1)
        r=self.filtrar([self.candidato(1)],self.prefs(),cliente,limites=LimitesStreaming(consultas=0))
        self.assertEqual(self.ids(r),[1]);self.assertEqual(r.estatisticas['cache'],1)
        self.assertEqual(r.estatisticas['chamadas_transporte'],0)
        self.assertEqual(abrir.call_count,1)

    def test_http_normal_sem_credenciais_preserva_esquema(self):
        class Transporte:
            def __init__(self,req):self.entrada=io.BytesIO(req);self.saida=bytearray()
            def makefile(self,*a):return self.entrada
            def sendall(self,d):self.saida.extend(d)
        corpo=json.dumps({'acao':'confirmar_selecao','ids':[1]}).encode()
        req=b'POST /api/recomendar HTTP/1.0\r\nHost: localhost\r\nContent-Length: '+str(len(corpo)).encode()+b'\r\n\r\n'+corpo
        with patch.dict(os.environ,{},clear=True),patch.object(Handler,'modelo',fixture()),patch.object(Handler,'sessoes',{}):
            t=Transporte(req);Handler(t,('127.0.0.1',1),object())
        headers,body=bytes(t.saida).split(b'\r\n\r\n',1)
        d=json.loads(body)
        self.assertIn(b'200 OK',headers);self.assertTrue(d['recomendacoes'])
        self.assertNotIn('streaming',d)

    def test_controlado_concorrente_so_uma_tentativa_consulta(self):
        abrir=Mock(side_effect=lambda req,timeout:http_fixture.Resposta(req.full_url,http_fixture.payload()))
        with patch.dict(os.environ,{'TMDB_READ_ACCESS_TOKEN':http_fixture.TOKEN}):
            c=ClienteDisponibilidadeTMDB({conteudo_movielens(1):100},habilitado=True,
                termos_aprovados=True,abrir=abrir,relogio=lambda:self.hora)
        with ThreadPoolExecutor(max_workers=4) as pool:
            r=list(pool.map(lambda _:c.obter_controlado(conteudo_movielens(1),permitir_consulta=True),range(4)))
        self.assertEqual(abrir.call_count,1)
        self.assertEqual(sum(x.chamadas_transporte for x in r),1)
        self.assertEqual(sum(x.origem=='CONSULTA' for x in r),1)

    def test_consulta_lenta_prazo_e_cooperativo_sem_segunda_consulta(self):
        servico=self.servico([self.dados(1),self.dados(2)])
        original=servico.obter_controlado
        def lento(*args,**kwargs):
            self.tick+=6
            return original(*args,**kwargs)
        servico.obter_controlado=lento
        r=self.filtrar([self.candidato(1),self.candidato(2)],self.prefs(),servico)
        self.assertEqual(self.ids(r),[1])
        self.assertEqual(len(servico.chamadas),1)
        self.assertIn('TEMPO',r.limites_atingidos)

    def test_expiracao_durante_consulta_nao_confirma(self):
        servico=self.servico([self.dados(1)])
        original=servico.obter_controlado
        def lento(*args,**kwargs):
            self.hora+=timedelta(hours=2)
            return original(*args,**kwargs)
        servico.obter_controlado=lento
        r=self.filtrar([self.candidato(1)],self.prefs(),servico)
        self.assertEqual(r.itens,())
        self.assertEqual(r.estatisticas['nao_verificados'],1)

    def test_resposta_para_outro_pais_ou_filme_nao_confirma(self):
        for dados in (self.dados(1,regiao='US'),self.dados(2)):
            servico=ServicoSintetico({(conteudo_movielens(1),'BR'):dados})
            r=self.filtrar([self.candidato(1)],self.prefs(),servico)
            self.assertEqual(r.itens,());self.assertTrue(r.parcial)


if __name__=='__main__':unittest.main()
