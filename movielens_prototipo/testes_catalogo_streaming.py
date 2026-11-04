"""Formato de homologação com evidências sintéticas, nunca catálogo real."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from catalogo_streaming import carregar_catalogo,ESQUEMA
from streaming_web import executar_streaming
from conversa import Sessao


class CatalogoStreamingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.pasta=Path(self.tmp.name);self.arquivo=self.pasta/'catalogo.json'
        self.url='https://api.themoviedb.org/3/watch/providers/movie?watch_region=BR&language=pt-BR'
        self.data='2026-10-30T12:00:00+00:00'
        self.evidencia=self.pasta/'evidencia.json'
        self.evidencia.write_text(json.dumps({'url':self.url,'regiao':'BR','tipo':'FILME','obtido_em':self.data,
            'resposta':{'results':[{'provider_id':10,'provider_name':'Serviço fictício Alfa'},
                                  {'provider_id':20,'provider_name':'Serviço fictício Beta'}]}}))
        self.entrada={'id':10,'nome':'Serviço fictício Alfa','estado':'homologado','regiao':'BR',
            'verificado_em':self.data,'procedencia':{'url':self.url,'arquivo':'evidencia.json',
                'sha256':hashlib.sha256(self.evidencia.read_bytes()).hexdigest()}}
        self.catalogo={'esquema':ESQUEMA,'versao':1,'regiao':'BR','verificado_em':self.data,'provedores':[]}
    def salvar(self,dados):self.arquivo.write_text(json.dumps(dados))
    def test_catalogo_publico_e_vazio(self):
        caminho=Path(__file__).with_name('catalogo_streaming_br.json')
        self.assertEqual(carregar_catalogo(caminho),())
    def test_sintetico_homologado_por_id_hash_regiao_e_nome(self):
        self.catalogo['provedores']=[self.entrada];self.salvar(self.catalogo)
        self.assertEqual(carregar_catalogo(self.arquivo),((10,'Serviço fictício Alfa'),))
    def test_pendente_nao_e_exposto(self):
        p={**self.entrada,'estado':'pendente','motivo_pendencia':'Evidência ainda não revisada'}
        self.catalogo['provedores']=[p];self.salvar(self.catalogo)
        self.assertEqual(carregar_catalogo(self.arquivo),())
    def test_integra_sessao_multiplos_ids_restauracao_e_modos(self):
        outro={**self.entrada,'id':20,'nome':'Serviço fictício Beta'}
        self.catalogo['provedores']=[self.entrada,outro];self.salvar(self.catalogo)
        catalogo=carregar_catalogo(self.arquivo);s=Sessao(referencias=[1],assistidos=[1])
        r=executar_streaming(s,{'acao':'salvar','regiao':'BR','provedores':[20,10],'modo':'flexivel'},catalogo)
        self.assertEqual(r['preferencias']['provedores'],[10,20]);self.assertFalse(s.streaming.ativo)
        self.assertEqual(s.referencias,[1]);self.assertEqual(executar_streaming(s,{'acao':'estado'},catalogo)['preferencias'],r['preferencias'])
        with self.assertRaises(ValueError):executar_streaming(s,{'acao':'salvar','regiao':'BR','provedores':[99],'modo':'restrito'},catalogo)
    def test_hash_nome_id_e_regiao_incompativeis_rejeitados(self):
        for mudar in ({'id':99},{'nome':'nome não comprovado'},
                      {'regiao':'US'},{'procedencia':{**self.entrada['procedencia'],'sha256':'0'*64}},
                      {'procedencia':{**self.entrada['procedencia'],'url':self.url.replace('BR','US')}}):
            self.catalogo['provedores']=[{**self.entrada,**mudar}];self.salvar(self.catalogo)
            with self.subTest(mudar=mudar),self.assertRaises(ValueError):carregar_catalogo(self.arquivo)
    def test_duplicatas_e_evidencia_ausente_rejeitadas(self):
        self.catalogo['provedores']=[self.entrada,self.entrada];self.salvar(self.catalogo)
        with self.assertRaises(ValueError):carregar_catalogo(self.arquivo)
        self.catalogo['provedores']=[self.entrada];self.salvar(self.catalogo);self.evidencia.unlink()
        with self.assertRaises(OSError):carregar_catalogo(self.arquivo)
    def test_caminho_externo_e_headers_no_envelope_rejeitados(self):
        self.catalogo['provedores']=[deepcopy(self.entrada)]
        self.catalogo['provedores'][0]['procedencia']['arquivo']='../fora.json'
        self.salvar(self.catalogo)
        with self.assertRaises(ValueError):carregar_catalogo(self.arquivo)
        e=json.loads(self.evidencia.read_text());e['Authorization']='NÃO PERMITIDO'
        self.evidencia.write_text(json.dumps(e));self.entrada['procedencia']['sha256']=hashlib.sha256(self.evidencia.read_bytes()).hexdigest()
        self.catalogo['provedores']=[self.entrada];self.salvar(self.catalogo)
        with self.assertRaises(ValueError):carregar_catalogo(self.arquivo)


if __name__=='__main__':unittest.main()
