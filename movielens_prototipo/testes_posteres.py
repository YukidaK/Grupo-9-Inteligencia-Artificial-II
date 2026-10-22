"""Integração TMDB simulada: nenhum teste usa rede ou credenciais reais."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from posteres import Posteres, PLACEHOLDER, carregar_links, carregar_ambiente
from app import Handler
from testes_conversa import fixture
from conversa import Sessao


class TMDB(unittest.TestCase):
    def setUp(self):
        self.instante = 1000
        self.calls = []
        self.movie = {'id': 862, 'poster_path': '/padrao.jpg', 'images': {'posters': [
            {'file_path': '/ingles.jpg', 'iso_639_1': 'en'},
            {'file_path': '/portugues.jpg', 'iso_639_1': 'pt'}]}}

    def abrir(self, req, timeout):
        self.calls.append(req)
        self.assertEqual(timeout, 3)
        self.assertEqual(req.get_header('Authorization'), 'Bearer token-ficticio')
        self.assertNotIn('token-ficticio', req.full_url)
        resposta = {'images': {'secure_base_url': 'https://image.tmdb.org/t/p/', 'poster_sizes': ['w185', 'w342', 'w500', 'original']}} if req.full_url.endswith('/configuration') else self.movie
        return io.BytesIO(json.dumps(resposta).encode())

    def servico(self, cache=None):
        p = Posteres({1: 862}, 'token-ficticio', cache, self.abrir, lambda: self.instante)
        # Remove apenas a espera entre chamadas dos testes; relógio de validade controlado.
        return p

    def test_mapeamento_ausencias_invalidos_conflitos(self):
        with tempfile.TemporaryDirectory() as pasta:
            p = Path(pasta)/'links.csv'
            p.write_text('movieId,imdbId,tmdbId\n1,0114709,862\n2,xxx,\n3,xxx,NaN\n4,xxx,0\n5,xxx,-3\n6,xxx,3.5\n7,xxx,9.0\n8,xxx,10\n8,xxx,11\n9,xxx,inf\n')
            self.assertEqual(carregar_links(p), {1: 862, 7: 9})
            self.assertEqual(carregar_links(Path(pasta)/'ausente.csv'), {})

    def test_portugues_por_id_e_sem_prefetch(self):
        p = self.servico()
        self.assertFalse(self.calls)
        d = p.obter(1)
        self.assertTrue(d['poster_url'].endswith('/w342/portugues.jpg'))
        self.assertTrue(d['thumbnail_url'].endswith('/w185/portugues.jpg'))
        self.assertIn('/movie/862?', self.calls[0].full_url)
        self.assertIn('language=pt-BR', self.calls[0].full_url)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(any('/search' in r.full_url for r in self.calls))

    def test_sem_credencial_ou_id_nao_chama_api(self):
        with patch.dict(os.environ, {}, clear=True):
            p = Posteres({1: 862}, abrir=self.abrir)
            self.assertEqual(p.obter(1)['poster_url'], PLACEHOLDER)
        p = self.servico()
        self.assertEqual(p.obter(999)['poster_url'], PLACEHOLDER)
        self.assertFalse(self.calls)

    def test_fallback_idioma_e_poster_path(self):
        self.movie['images']['posters'] = [{'file_path': '/ingles.jpg', 'iso_639_1': 'en'}, {'file_path': '/neutro.jpg', 'iso_639_1': None}]
        self.assertIn('/ingles.jpg', self.servico().obter(1)['poster_url'])
        self.movie['images']['posters'] = []
        self.assertIn('/padrao.jpg', self.servico().obter(1)['poster_url'])

    def test_sem_poster_cacheia_ausencia(self):
        self.movie = {'id': 862, 'poster_path': None}
        p = self.servico()
        self.assertEqual(p.obter(1)['poster_url'], PLACEHOLDER)
        self.assertEqual(p.obter(1)['poster_url'], PLACEHOLDER)
        self.assertEqual(len(self.calls), 1)

    def test_cache_persistente_e_expiracao(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta)/'cache.json'
            p = self.servico(caminho)
            antes = p.obter(1)
            p.obter(1)
            self.assertEqual(len(self.calls), 2)
            outro = self.servico(caminho)
            self.assertEqual(outro.obter(1), antes)
            self.assertEqual(len(self.calls), 2)
            self.assertNotIn('token-ficticio', caminho.read_text())
            self.instante += 7*24*3600 + 1
            outro.obter(1)
            self.assertEqual(len(self.calls), 4)

    def test_timeout_offline_json_invalido_e_id_errado(self):
        for erro in [TimeoutError(), urllib.error.URLError('offline'), ValueError('JSON inválido')]:
            p = self.servico()
            with patch.object(p, 'abrir', side_effect=erro) as mock:
                self.assertEqual(p.obter(1)['poster_url'], PLACEHOLDER)
                self.assertEqual(p.obter(1)['poster_url'], PLACEHOLDER)
                self.assertEqual(mock.call_count, 1)
        self.movie['id'] = 999
        self.assertEqual(self.servico().obter(1)['poster_url'], PLACEHOLDER)

    def test_429_respeita_retry_after_sem_repeticao(self):
        p = self.servico()
        erro = urllib.error.HTTPError('https://api.themoviedb.org', 429, 'limite', {'Retry-After': '120'}, None)
        with patch.object(p, 'abrir', side_effect=erro) as mock:
            self.assertEqual(p.obter(1)['poster_url'], PLACEHOLDER)
            self.instante += 61
            self.assertEqual(p.obter(1)['poster_url'], PLACEHOLDER)
            self.assertEqual(mock.call_count, 1)
        self.instante += 60
        self.assertIn('/portugues.jpg', p.obter(1)['poster_url'])

    def test_404_e_cache_negativo_sem_bloquear_outros_filmes(self):
        p = self.servico()
        erro = urllib.error.HTTPError('https://api.themoviedb.org', 404, 'ausente', {}, None)
        with patch.object(p, 'abrir', side_effect=erro) as mock:
            self.assertEqual(p.obter(1)['poster_url'], PLACEHOLDER)
            self.assertEqual(p.obter(1)['poster_url'], PLACEHOLDER)
            self.assertEqual(mock.call_count, 1)
        self.assertEqual(p.pausa_ate, 0)

    def test_config_falha_usa_tamanho_documentado(self):
        p = self.servico()
        def abrir(req, timeout):
            if req.full_url.endswith('/configuration'):
                raise TimeoutError()
            return self.abrir(req, timeout)
        p.abrir = abrir
        self.assertIn('/w500/portugues.jpg', p.obter(1)['poster_url'])

    def test_resposta_hostil_nao_vira_url(self):
        self.movie = {'id': 862, 'poster_path': 'https://invalido.example/a.jpg', 'images': {'posters': [{'file_path': '/../../a.jpg'}]}}
        self.assertEqual(self.servico().obter(1)['poster_url'], PLACEHOLDER)

    def test_cache_corrompido_e_disco_indisponivel(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta)/'cache.json'
            arquivo.write_text('{erro')
            self.assertIn('/portugues.jpg', self.servico(arquivo).obter(1)['poster_url'])
            self.assertIn('/portugues.jpg', self.servico(Path(pasta)).obter(1)['poster_url'])

    def test_env_nao_sobrescreve_variavel_e_nao_carrega_outros_nomes(self):
        with tempfile.TemporaryDirectory() as pasta, patch.dict(os.environ, {'TMDB_READ_ACCESS_TOKEN': 'exportado'}, clear=True):
            Path(pasta, '.env').write_text('TMDB_READ_ACCESS_TOKEN=arquivo\nMOVIELENS_LINKS_CSV=/tmp/links.csv\nOUTRA_VARIAVEL=ignorada\n')
            carregar_ambiente(pasta)
            self.assertEqual(os.environ['TMDB_READ_ACCESS_TOKEN'], 'exportado')
            self.assertEqual(os.environ['MOVIELENS_LINKS_CSV'], '/tmp/links.csv')
            self.assertNotIn('OUTRA_VARIAVEL', os.environ)

    def test_endpoint_placeholder_catalogo_e_ranking_intacto(self):
        modelo = fixture()
        sessao = Sessao(assistidos=[1], referencias=[1])
        antes = modelo.recomendar_perfil(sessao)
        class Transporte:
            def __init__(self, caminho):
                self.entrada = io.BytesIO(f'GET {caminho} HTTP/1.0\r\n\r\n'.encode())
                self.saida = bytearray()
            def makefile(self, *args):
                return self.entrada
            def sendall(self, dados):
                self.saida.extend(dados)
        with patch.object(Handler, 'modelo', modelo), patch.object(Handler, 'posteres', Posteres({1: 862})):
            for caminho, status in [('/api/poster/1', b'200 OK'), ('/api/poster/999999', b'404'), ('/static/poster-placeholder.svg', b'200 OK')]:
                t = Transporte(caminho)
                Handler(t, ('127.0.0.1', 1234), object())
                self.assertIn(status, t.saida)
                if caminho == '/api/poster/1':
                    self.assertEqual(json.loads(bytes(t.saida).split(b'\r\n\r\n')[1])['poster_url'], PLACEHOLDER)
        self.assertEqual(modelo.recomendar_perfil(sessao), antes)


if __name__ == '__main__':
    unittest.main()
