"""RF-02A: respostas sintéticas, sem token, rede, sessão ou dados reais."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from identidades import IdentidadeConteudo, TipoConteudo, conteudo_movielens
from disponibilidade import (
    Oferta, Disponibilidade, Disponibilidades, PreferenciasStreaming, Modalidade,
    Estado, Modo, Compatibilidade, compatibilidade, links_movielens, catalogo_provedores,
)


def provedor(i=10,nome='Serviço sintético'):
    return {'provider_id':i,'provider_name':nome,'logo_path':'/sintetico.png'}


def resposta(**modalidades):
    return {'id':100,'results':{'BR':{'link':'https://www.themoviedb.org/movie/100/watch?locale=BR',**modalidades}}}


class DisponibilidadeTests(unittest.TestCase):
    def setUp(self):
        self.conteudo = conteudo_movielens(1)
        self.hora = datetime(2026,10,29,12,tzinfo=timezone.utc)
        self.relogio = lambda:self.hora
        self.consultar = Mock(return_value=resposta(flatrate=[provedor()]))
        self.servico = Disponibilidades({self.conteudo:100},self.consultar,relogio=self.relogio)

    def comparar(self,provedores,regiao='BR',modo=Modo.RESTRITO):
        return compatibilidade(self.servico.obter(self.conteudo,regiao),
            PreferenciasStreaming(frozenset(provedores),regiao,modo),self.hora)

    def test_assinatura_selecionada_e_nao_selecionada(self):
        self.assertIs(self.comparar([10]),Compatibilidade.INCLUIDO_ASSINATURA)
        self.assertIs(self.comparar([20]),Compatibilidade.NAO_CONFIRMADO)
        self.assertIs(self.comparar([]),Compatibilidade.SEM_SELECAO)

    def test_aluguel_compra_gratis_e_anuncios_nao_viram_assinatura(self):
        self.consultar.return_value = resposta(rent=[provedor()],buy=[provedor()],free=[provedor()],ads=[provedor()])
        d = self.servico.obter(self.conteudo)
        self.assertEqual({o.modalidade for o in d.ofertas},
            {Modalidade.ALUGUEL,Modalidade.COMPRA,Modalidade.GRATIS,Modalidade.ANUNCIOS})
        self.assertIs(self.comparar([10]),Compatibilidade.NAO_CONFIRMADO)

    def test_multiplas_assinaturas_e_modo_flexivel_nao_relaxam_sozinhos(self):
        self.assertIs(self.comparar([20,10]),Compatibilidade.INCLUIDO_ASSINATURA)
        self.assertIs(self.comparar([20],modo=Modo.FLEXIVEL),Compatibilidade.NAO_CONFIRMADO)
        antes = PreferenciasStreaming(frozenset({20}))
        depois = replace(antes,provedores=frozenset({10}))
        self.assertEqual(antes.provedores,frozenset({20}))
        self.assertIs(compatibilidade(self.servico.obter(self.conteudo),depois,self.hora),Compatibilidade.INCLUIDO_ASSINATURA)

    def test_regioes_isoladas(self):
        self.consultar.return_value = {'id':100,'results':{'US':{'flatrate':[provedor()]}}}
        self.assertIs(self.comparar([10]),Compatibilidade.DESCONHECIDA)
        self.assertIs(self.comparar([10],'US'),Compatibilidade.INCLUIDO_ASSINATURA)
        self.assertEqual(self.consultar.call_count,2)
        d = self.servico.obter(self.conteudo,'US')
        self.assertIs(compatibilidade(d,PreferenciasStreaming(frozenset({10}),'BR'),self.hora),Compatibilidade.DESCONHECIDA)

    def test_sem_mapeamento_nao_chama_fonte(self):
        d = self.servico.obter(conteudo_movielens(2))
        self.assertIsNone(d.tmdb_id)
        self.assertEqual(d.motivo,'SEM_MAPEAMENTO_TMDB')
        self.consultar.assert_not_called()

    def test_filme_serie_e_fontes_com_mesmo_id_nao_colidem(self):
        filme = self.servico.obter(self.conteudo)
        serie = IdentidadeConteudo('movielens',TipoConteudo.SERIE,'1')
        outra = IdentidadeConteudo('outra',TipoConteudo.FILME,'1')
        self.assertEqual(self.servico.obter(serie).motivo,'TIPO_NAO_SUPORTADO')
        self.assertEqual(self.servico.obter(outra).motivo,'SEM_MAPEAMENTO_TMDB')
        self.assertIs(self.servico.obter(self.conteudo),filme)
        self.consultar.assert_called_once_with(100,'BR')

    def test_respostas_vazias_nunca_confirmam_indisponibilidade(self):
        for payload in ({'id':100,'results':{}},resposta(),resposta(flatrate=[])):
            with self.subTest(payload=payload):
                s = Disponibilidades({self.conteudo:100},lambda *args:payload,relogio=self.relogio)
                d = s.obter(self.conteudo)
                self.assertIs(d.estado,Estado.DESCONHECIDA)
                self.assertFalse(d.ausencia_confirmada)
                self.assertEqual(d.ofertas,())

    def test_respostas_invalidas_falham_fechadas(self):
        payloads = (None,[],{}, {'id':True,'results':{}},{'id':999,'results':{}},
            {'id':100,'results':[]},{'id':100,'results':{'BR':None}},
            resposta(flatrate='serviço'),resposta(flatrate=[{'provider_id':True,'provider_name':'X'}]),
            resposta(flatrate=[provedor()],premium=[provedor()]),
            resposta(flatrate=[provedor()],link='https://malicioso.test'))
        for payload in payloads:
            with self.subTest(payload=payload):
                s = Disponibilidades({self.conteudo:100},lambda *args:payload,relogio=self.relogio)
                d = s.obter(self.conteudo)
                self.assertIs(d.estado,Estado.ERRO)
                self.assertEqual(d.ofertas,())
                self.assertEqual(d.motivo,'RESPOSTA_INVALIDA')

    def test_falha_rede_nao_vaza_mensagem_ou_credencial(self):
        self.consultar.side_effect = TimeoutError('token=SEGREDO_SINTETICO')
        d = self.servico.obter(self.conteudo)
        self.assertIs(d.estado,Estado.ERRO)
        self.assertEqual(d.motivo,'FALHA_FONTE')
        self.assertNotIn('SEGREDO',repr(d))
        self.assertIs(self.comparar([10]),Compatibilidade.ERRO)

    def test_cache_consulta_unica_e_expiracao_exata(self):
        d = self.servico.obter(self.conteudo)
        self.assertIs(self.servico.obter(self.conteudo),d)
        self.assertEqual(self.consultar.call_count,1)
        self.hora += timedelta(hours=24)
        self.assertIs(compatibilidade(d,PreferenciasStreaming(frozenset({10})),self.hora),Compatibilidade.DESCONHECIDA)
        self.consultar.return_value = resposta(rent=[provedor()])
        novo = self.servico.obter(self.conteudo)
        self.assertIsNot(novo,d)
        self.assertEqual(self.consultar.call_count,2)
        self.assertIs(self.comparar([10]),Compatibilidade.NAO_CONFIRMADO)

    def test_cache_desconhecido_e_erro_prazos_distintos_sem_usar_stale(self):
        self.consultar.return_value = resposta()
        d = self.servico.obter(self.conteudo)
        self.assertEqual(d.expira_em-self.hora,timedelta(minutes=15))
        self.hora = d.expira_em
        self.consultar.side_effect = OSError('offline')
        erro = self.servico.obter(self.conteudo)
        self.assertEqual(erro.expira_em-self.hora,timedelta(seconds=60))
        self.assertIs(self.servico.obter(self.conteudo),erro)
        self.assertIs(self.comparar([10]),Compatibilidade.ERRO)

    def test_sucesso_vencido_nao_e_reaproveitado_apos_falha(self):
        antigo = self.servico.obter(self.conteudo)
        self.hora = antigo.expira_em
        self.consultar.side_effect = OSError('offline')
        novo = self.servico.obter(self.conteudo)
        self.assertEqual(novo.ofertas,())
        self.assertIs(self.comparar([10]),Compatibilidade.ERRO)
        self.assertEqual(self.consultar.call_count,2)

    def test_assinatura_de_outro_provedor_nao_confirma_aluguel_selecionado(self):
        self.consultar.return_value = resposta(flatrate=[provedor(20)],rent=[provedor(10)])
        self.assertIs(self.comparar([10]),Compatibilidade.NAO_CONFIRMADO)
        self.assertIs(self.comparar([10,20]),Compatibilidade.INCLUIDO_ASSINATURA)

    def test_cache_limite_e_mudanca_de_id(self):
        s = Disponibilidades({self.conteudo:100},self.consultar,relogio=self.relogio,limite=1)
        s.obter(self.conteudo)
        s.obter(conteudo_movielens(2))
        self.assertEqual(len(s.cache),1)
        s.obter(self.conteudo)
        self.assertEqual(self.consultar.call_count,2)
        s.links[self.conteudo] = 200
        self.consultar.return_value = {'id':200,'results':{}}
        self.assertEqual(s.obter(self.conteudo).tmdb_id,200)
        self.assertEqual(self.consultar.call_count,3)

    def test_ids_estaveis_nomes_nao_sao_associacao_e_modalidades_deduplicadas(self):
        self.consultar.return_value = resposta(flatrate=[provedor(),provedor()],rent=[provedor()])
        self.assertEqual(len(self.servico.obter(self.conteudo).ofertas),2)
        self.assertEqual(catalogo_provedores({'results':[provedor(10,'Mesmo nome'),provedor(20,'Mesmo nome')]}),
            ((10,'Mesmo nome'),(20,'Mesmo nome')))
        self.assertEqual(catalogo_provedores({'results':[]}),())
        with self.assertRaises(ValueError):
            catalogo_provedores({'results':[provedor(10,'A'),provedor(10,'B')]})

    def test_links_csv_sem_titulo_ou_conflitos(self):
        with tempfile.TemporaryDirectory() as pasta:
            p = Path(pasta)/'links.csv'
            p.write_text('movieId,imdbId,tmdbId\n1,1,100\n2,2,200\n2,2,201\n3,3,\n')
            self.assertEqual(links_movielens(p),{self.conteudo:100})

    def test_link_tmdb_com_slug_mesmo_id_e_id_errado(self):
        self.consultar.return_value = resposta(flatrate=[provedor()],link='https://www.themoviedb.org/movie/100-filme-sintetico/watch?locale=BR')
        self.assertIs(self.comparar([10]),Compatibilidade.INCLUIDO_ASSINATURA)
        self.hora += timedelta(days=1)
        self.consultar.return_value = resposta(flatrate=[provedor()],link='https://www.themoviedb.org/movie/200-outro/watch?locale=BR')
        self.assertIs(self.servico.obter(self.conteudo).estado,Estado.ERRO)

    def test_ausencia_explicita_reservada_nao_e_inferida_do_tmdb(self):
        args = dict(conteudo=self.conteudo,tmdb_id=100,regiao='BR',consultado_em=self.hora,
            expira_em=self.hora+timedelta(hours=1),estado=Estado.CONFIRMADA,ausencia_confirmada=True,
            evidencia_ausencia='Evidência sintética explícita, escopo conteúdo/região')
        with self.assertRaises(ValueError): Disponibilidade(**args)
        d = Disponibilidade(**args,fonte='fonte_futura_explicita')
        self.assertIs(compatibilidade(d,PreferenciasStreaming(frozenset({10})),self.hora),Compatibilidade.INDISPONIVEL_CONFIRMADO)

    def test_validacoes_de_contrato_e_sem_transporte_implicito(self):
        with self.assertRaises(ValueError): Disponibilidades({},None)
        with self.assertRaises(ValueError): PreferenciasStreaming(frozenset({True}))
        with self.assertRaises(ValueError): PreferenciasStreaming(frozenset({10}),regiao='br')
        with self.assertRaises(ValueError): self.servico.obter(1)
        with patch('urllib.request.urlopen',side_effect=AssertionError('Rede proibida')):
            self.assertIs(self.comparar([10]),Compatibilidade.INCLUIDO_ASSINATURA)
        with self.assertRaises(ValueError):
            compatibilidade(self.servico.obter(self.conteudo),PreferenciasStreaming(),datetime(2026,1,1))


if __name__=='__main__':
    unittest.main()
