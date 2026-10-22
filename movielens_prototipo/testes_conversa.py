"""Fixtures sintéticas, sem download; não medem qualidade das recomendações."""
import contextlib
import http.cookiejar
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
import recomendador as modulo
from recomendador import Recomendador, ranking, limpar, dividir
from conversa import Conversa, Sessao, interpretar_mensagem
from app import Handler
from http.server import ThreadingHTTPServer


def fixture():
    filmes = pd.DataFrame([(i, f'Filme {i} (2000)', ['Drama', 'Thriller|Crime', 'Horror', 'Sci-Fi|Adventure'][i % 4], 2000) for i in range(1, 41)], columns=['movieId', 'title', 'genres', 'ano'])
    filmes.loc[0, 'title'] = 'Solaris (1972)'
    filmes.loc[1, 'title'] = 'Solaris (2002)'
    treino = pd.DataFrame([(u, i, float(3 + i % 3), i) for u in range(1, 7) for i in range(1, 41)], columns=['userId', 'movieId', 'rating', 'timestamp'])
    return Recomendador(filmes, ranking(treino), treino)


class Fluxo(unittest.TestCase):
    def setUp(self):
        self.modelo = fixture()
        self.c = Conversa(self.modelo)
        self.s = Sessao()

    def confirmar(self, ids):
        self.s.pendentes = set(ids)
        return self.c.executar(self.s, {'acao': 'confirmar', 'ids': ids})

    def msg(self, t):
        return self.c.executar(self.s, {'texto': t})

    def test_uma_referencia_avisa_e_recomenda(self):
        d = self.confirmar([1])
        self.assertIn('abrangente', d['mensagem'])
        self.assertTrue(d['recomendacoes'])
        self.assertNotIn(1, [f['movieId'] for f in d['recomendacoes']])

    def test_duas_a_cinco(self):
        for n in range(2, 6):
            self.s = Sessao()
            self.confirmar(list(range(1, n+1)))
            self.assertEqual(self.s.referencias, list(range(1, n+1)))

    def test_excedentes_duplicatas_e_limite(self):
        d = self.confirmar([1, 1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(self.s.referencias, [1, 2, 3, 4, 5])
        self.assertEqual([f['movieId'] for f in d['excedentes']], [6, 7])
        ids = [f['movieId'] for f in d['recomendacoes']]
        self.assertFalse(set(ids) & set(range(1, 8)))
        self.assertEqual(len(set(ids)), len(ids))
        self.assertLessEqual(len(ids), 10)

    def test_substituicao_explicita_preserva_historico(self):
        self.confirmar([1, 2, 3, 4, 5, 8])
        antes = self.s.recomendacoes.copy()
        d = self.c.executar(self.s, {'acao': 'considerar', 'movieId': 8})
        self.assertIn('substituir', d['mensagem'])
        self.assertEqual(self.s.referencias, [1, 2, 3, 4, 5])
        self.c.executar(self.s, {'acao': 'considerar', 'movieId': 8, 'substituir': 2})
        self.assertEqual(self.s.referencias, [1, 8, 3, 4, 5])
        self.assertEqual(self.s.assistidos, [1, 2, 3, 4, 5, 8])
        self.assertNotEqual(antes, self.s.recomendacoes)

    def test_adicionar_confirmados_preenche_vagas_sem_troca_silenciosa(self):
        self.confirmar([1])
        self.confirmar([2, 3, 4])
        self.assertEqual(self.s.referencias, [1, 2, 3, 4])
        self.confirmar([5, 6, 7])
        self.assertEqual(self.s.referencias, [1, 2, 3, 4, 5])
        self.assertEqual(self.s.assistidos, [1, 2, 3, 4, 5, 6, 7])

    def test_rejeicao_nao_positiva(self):
        self.confirmar([1, 4])
        self.msg('Assisti Solaris (1972), mas não gostei.')
        self.assertNotIn(1, self.s.referencias)
        self.assertIn(1, self.s.assistidos)
        self.assertIn(1, self.s.rejeitados)
        outra = Sessao(assistidos=[1, 4], referencias=[4])
        self.assertEqual(self.s.recomendacoes, self.modelo.recomendar_perfil(outra))
        with self.assertRaises(ValueError):
            self.c.considerar(self.s, 1)

    def test_busca_ambigua_desconhecida_revisao_parcial(self):
        d = self.c.executar(self.s, {'acao': 'buscar', 'texto': 'Solaris; inexistente xyz; Filme 3 (2000)'})
        self.assertEqual(len(d['buscas'][0]['opcoes']), 2)
        self.assertEqual(d['buscas'][1]['opcoes'], [])
        self.assertFalse(self.s.referencias)
        self.c.executar(self.s, {'acao': 'confirmar', 'ids': [3]})
        self.assertEqual(self.s.referencias, [3])
        self.msg('Assisti Solaris, mas não gostei')
        self.assertEqual(self.s.assistidos, [3])
        with self.assertRaises(ValueError):
            self.c.executar(self.s, {'acao': 'confirmar', 'ids': [999]})
        self.assertTrue(self.c.buscar('Filme 3'))

    def test_zero_reconhecidos_nao_inicia(self):
        self.c.executar(self.s, {'acao': 'buscar', 'texto': 'inexistente xyz'})
        with self.assertRaises(ValueError):
            self.c.executar(self.s, {'acao': 'confirmar', 'ids': []})
        self.assertFalse(self.msg('Quero suspense')['recomendacoes'])

    def test_preferencias_persistem_mudam_ranking_e_limpeza(self):
        self.confirmar([4, 1])
        antes = self.s.recomendacoes.copy()
        self.msg('Quero mais suspense.')
        self.assertNotEqual(antes, self.s.recomendacoes)
        self.assertTrue(all('Thriller' in f['generos'] for f in self.s.recomendacoes))
        self.msg('Não gosto de terror')
        self.assertEqual(self.s.positivos, {'Thriller'})
        self.assertEqual(self.s.negativos, {'Horror'})
        self.msg('Prefiro ficção científica')
        self.assertEqual(self.s.positivos, {'Thriller', 'Sci-Fi'})
        self.assertTrue(all('Horror' not in f['generos'] for f in self.s.recomendacoes))
        self.msg('Limpar minhas preferências')
        self.assertFalse(self.s.positivos | self.s.negativos)
        self.assertEqual(self.s.referencias, [4, 1])

    def test_restricao_sem_candidatos_nao_relaxa(self):
        self.confirmar([1])
        for genero in ['drama', 'suspense', 'terror', 'ficção científica']:
            d = self.msg('Não gosto de ' + genero)
        self.assertEqual(d['recomendacoes'], [])
        self.assertIn('restrições', d['mensagem'])

    def test_desconhecido_e_explicacao_preservam(self):
        self.confirmar([4])
        antes = self.s.recomendacoes.copy()
        for texto in ['Quero só suspense sem terror', 'Quero mais suspense sem terror', 'sugira um enredo com viagens', 'Não gosto de terror, mas adoro drama']:
            d = self.msg(texto)
            self.assertIn('Não entendi', d['mensagem'])
            self.assertEqual(antes, d['recomendacoes'])
        d = self.msg('Por que você recomendou esse?')
        self.assertIn('posição', d['mensagem'])
        d = self.msg('Por que 1?')
        self.assertIn(antes[0]['motivo'], d['mensagem'])
        self.assertEqual(self.s.recomendacoes, antes)

    def test_adicao_nao_substitui_nem_promove_rejeicao(self):
        self.confirmar([4])
        self.msg('Assisti Filme 8 (2000)')
        self.assertEqual(self.s.referencias, [4])
        self.msg('Quero considerar Filme 8 (2000)')
        self.assertEqual(self.s.referencias, [4, 8])
        self.msg('Assisti Filme 8 (2000), mas não gostei')
        self.msg('Limpar minhas preferências')
        self.assertNotIn(8, self.s.referencias)
        self.assertIn(8, self.s.rejeitados)

    def test_sessoes_independentes_e_reset(self):
        self.confirmar([1, 4])
        outra = Sessao()
        self.assertFalse(self.c.executar(outra, {'acao': 'estado'})['assistidos'])
        self.msg('Não gosto de terror')
        self.assertFalse(outra.negativos)
        self.c.executar(self.s, {'acao': 'reiniciar'})
        self.assertEqual(self.s, Sessao())


class Pipeline(unittest.TestCase):
    def test_zip_local_evita_download(self):
        import zipfile
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta)/'ml-latest-small'
            with zipfile.ZipFile(Path(pasta)/'ml-latest-small.zip', 'w') as z:
                for nome, texto in {
                    'ratings.csv': 'userId,movieId,rating,timestamp\n1,1,4,1\n',
                    'movies.csv': 'movieId,title,genres\n1,Filme (2000),Drama\n',
                    'tags.csv': '', 'links.csv': '', 'README.txt': 'Fixture sintética'
                }.items():
                    z.writestr('ml-latest-small/'+nome, texto)
            with patch.object(modulo.urllib.request, 'urlopen') as download:
                r, m = modulo.carregar(destino)
                download.assert_not_called()
                self.assertEqual(len(r), 1)
                self.assertEqual(len(m), 1)
                self.assertTrue((Path(pasta)/'origem.json').exists())

    def test_falha_certificado_tem_orientacao(self):
        import ssl
        import urllib.error
        erro = urllib.error.URLError(ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED'))
        with tempfile.TemporaryDirectory() as pasta, patch.object(modulo.urllib.request, 'urlopen', side_effect=erro):
            with self.assertRaisesRegex(RuntimeError, 'certificado HTTPS') as resultado:
                modulo.carregar(Path(pasta)/'ml-latest-small')
            self.assertIn('ml-latest-small.zip', str(resultado.exception))

    def test_artefatos_matriz_treino_e_baselines(self):
        modelo = fixture()
        movies = modelo.filmes
        bruto = pd.DataFrame([(u, i, float(3 + i % 3), i) for u in range(1, 7) for i in range(1, 41)], columns=['userId', 'movieId', 'rating', 'timestamp'])
        with tempfile.TemporaryDirectory() as pasta, patch.object(modulo, 'ROOT', Path(pasta)), patch.object(modulo, 'carregar', return_value=(bruto, movies)), contextlib.redirect_stdout(io.StringIO()):
            treino, teste, _, stats = modulo.preparar()
            self.assertFalse(set(zip(treino.userId, treino.movieId)) & set(zip(teste.userId, teste.movieId)))
            pd.testing.assert_frame_equal(stats, ranking(treino))
            a, b = dividir(limpar(bruto, movies)[0])
            pd.testing.assert_frame_equal(treino, a)
            pd.testing.assert_frame_equal(teste, b)
            matriz = load_npz(Path(pasta)/'resultados/matriz_treino.npz')
            indices = json.loads((Path(pasta)/'resultados/indices_matriz.json').read_text())
            self.assertEqual(matriz.nnz, len(treino))
            for f in treino.itertuples():
                self.assertEqual(matriz[indices['userIds'].index(f.userId), indices['movieIds'].index(f.movieId)], f.rating)
            rel = json.loads((Path(pasta)/'resultados/relatorio.json').read_text())
            self.assertEqual(set(rel['metricas']), {'popularidade', 'nota_ponderada'})
            for m in rel['metricas'].values():
                self.assertEqual(set(m), {'precision_at_10', 'recall_at_10', 'ndcg_at_10'})


class HTTP(unittest.TestCase):
    def test_http_em_memoria_fluxo_completo(self):
        # Executa o handler HTTP real com transporte em memória, sem substituir o motor.
        Handler.modelo = fixture()
        Handler.sessoes = {}
        class Transporte:
            def __init__(self, dados):
                self.entrada = io.BytesIO(dados)
                self.saida = bytearray()
            def makefile(self, *args):
                return self.entrada
            def sendall(self, dados):
                self.saida.extend(dados)
        def post(dados, cookie=''):
            corpo = json.dumps(dados).encode()
            cabecalho = (f'POST /api/recomendar HTTP/1.0\r\nHost: localhost\r\nCookie: {cookie}\r\nContent-Length: {len(corpo)}\r\n\r\n').encode()
            transporte = Transporte(cabecalho + corpo)
            Handler(transporte, ('127.0.0.1', 1234), object())
            headers, body = bytes(transporte.saida).split(b'\r\n\r\n', 1)
            novo = next((h.split(': ', 1)[1].split(';', 1)[0] for h in headers.decode().split('\r\n') if h.startswith('Set-Cookie:')), cookie)
            return headers, json.loads(body), novo
        h, d, cookie = post({'acao': 'estado'})
        self.assertIn(b'200 OK', h)
        self.assertFalse(d['referencias'])
        _, d, _ = post({'acao': 'buscar', 'texto': 'Solaris; Filme 4'}, cookie)
        self.assertEqual(len(d['buscas'][0]['opcoes']), 2)
        _, d, _ = post({'acao': 'confirmar', 'ids': [1, 4]}, cookie)
        self.assertEqual(len(d['referencias']), 2)
        self.assertTrue(d['recomendacoes'])
        _, d, _ = post({'texto': 'Não gosto de terror'}, cookie)
        self.assertEqual(d['preferencias']['negativas'], ['Horror'])
        _, outro, outro_cookie = post({'acao': 'estado'})
        self.assertNotEqual(cookie, outro_cookie)
        self.assertFalse(outro['assistidos'])
        _, d, _ = post({'texto': 'Por que 1?'}, cookie)
        self.assertIn(d['recomendacoes'][0]['motivo'], d['mensagem'])
        h, _, _ = post({'texto': ''}, cookie)
        self.assertIn(b'400 Bad Request', h)
        _, d, _ = post({'acao': 'reiniciar'}, cookie)
        self.assertFalse(d['assistidos'])

    def test_fluxo_cookie_isolamento_e_erros(self):
        Handler.modelo = fixture()
        Handler.sessoes = {}
        try:
            servidor = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        except PermissionError:
            self.skipTest('Sandbox não permite abrir sockets locais; contrato HTTP validado também em memória.')
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{servidor.server_port}'
        clientes = [urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())) for _ in range(2)]
        def post(cliente, dados):
            req = urllib.request.Request(url+'/api/recomendar', json.dumps(dados).encode(), {'Content-Type': 'application/json'})
            with cliente.open(req) as resposta:
                return json.load(resposta)
        try:
            with clientes[0].open(url) as r:
                self.assertIn('CineMatch', r.read().decode())
            for cliente in clientes:
                post(cliente, {'acao': 'estado'})
            post(clientes[0], {'acao': 'buscar', 'texto': 'Solaris'})
            d = post(clientes[0], {'acao': 'confirmar', 'ids': [1]})
            self.assertEqual(len(d['referencias']), 1)
            self.assertFalse(post(clientes[1], {'acao': 'estado'})['assistidos'])
            post(clientes[0], {'texto': 'Não gosto de terror'})
            self.assertEqual(post(clientes[0], {'acao': 'estado'})['preferencias']['negativas'], ['Horror'])
            self.assertFalse(post(clientes[1], {'acao': 'estado'})['preferencias']['negativas'])
            with self.assertRaises(urllib.error.HTTPError) as e:
                post(clientes[0], {'texto': ''})
            self.assertEqual(e.exception.code, 400)
        finally:
            servidor.shutdown(); servidor.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
