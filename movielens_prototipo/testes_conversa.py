"""Caracterizações do motor e preparação, preservadas no escopo essencial."""
import contextlib

import hashlib

import http.cookiejar

import io

import json

from pathlib import Path

import tempfile

import threading

import unittest

import urllib.request

import urllib.error

import zipfile

from unittest.mock import patch

import numpy as np

import pandas as pd

from scipy.sparse import load_npz

import recomendador as modulo

from recomendador import Recomendador, ranking, limpar, dividir

from conversa import Conversa, Sessao

from app import Handler

from http.server import ThreadingHTTPServer

def fixture():
    filmes = pd.DataFrame([(i, f'Filme {i} (2000)', ['Drama', 'Thriller|Crime', 'Horror', 'Sci-Fi|Adventure'][i % 4], 2000) for i in range(1, 41)], columns=['movieId', 'title', 'genres', 'ano'])
    filmes.loc[0, 'title'] = 'Solaris (1972)'
    filmes.loc[1, 'title'] = 'Solaris (2002)'
    treino = pd.DataFrame([(u, i, float(3 + i % 3), i) for u in range(1, 7) for i in range(1, 41)], columns=['userId', 'movieId', 'rating', 'timestamp'])
    return Recomendador(filmes, ranking(treino), treino)

class CaracterizacaoPerfil(unittest.TestCase):
    def setUp(self):
        filmes = pd.DataFrame([
            (1, 'Referência mista (2000)', 'Drama|Comedy', 2000),
            (2, 'Referência de ação (2000)', 'Action', 2000),
            (3, 'Referência de drama (2000)', 'Drama', 2000),
            (4, 'Referência de comédia (2000)', 'Comedy', 2000),
            (5, 'Referência de terror (2000)', 'Horror', 2000),
            (12, 'Candidato misto (2000)', 'Comedy|Action', 2000),
            (15, 'Sem gêneros (2000)', '(no genres listed)', 2000),
            (14, 'Candidato de ação (2000)', 'Action', 2000),
            (11, 'Candidato de drama (2000)', 'Drama', 2000),
            (13, 'Candidato de terror (2000)', 'Horror', 2000),
            (10, 'Candidato semelhante (2000)', 'Drama|Comedy', 2000),
        ], columns=['movieId', 'title', 'genres', 'ano'])
        # Estatísticas sintéticas fornecidas diretamente: o alvo é o perfil,
        # não a preparação dos baselines. A ordem de entrada não é o ranking.
        stats = pd.DataFrame([
            (1, 20, 5., 5.), (2, 20, 5., 5.),
            (12, 7, 3., 3.), (15, 10, 5., 5.),
            (14, 6, 4., 4.), (11, 9, 5., 5.),
            (13, 12, 5., 5.), (10, 8, 4., 4.),
        ], columns=['movieId', 'contagem', 'media', 'nota_ponderada'])
        self.modelo = Recomendador(filmes, stats)
    def conferir(self, resultados, esperados):
        """Compara a lista inteira com pares (ID, score) calculados à mão."""
        self.assertEqual([f['movieId'] for f in resultados],
                         [movie_id for movie_id, _ in esperados])
        for filme, (_, score) in zip(resultados, esperados):
            with self.subTest(movieId=filme['movieId']):
                self.assertAlmostEqual(filme['pontuacao'], score, delta=1e-12)
    def test_ids_ordem_scores_e_diferentes_referencias(self):
        # S contra referência 1: IDs 10=1, 11=1/2, 12=1/3.
        # S contra referência 2: IDs 14=1, 12=1/2.
        # Duas referências: S(10)=S(14)=1/2, S(12)=5/12,
        # S(11)=1/4. W contribui com 0,08 / 0,06 / 0,10.
        # Com R=[1,2,3], S(10,11,12,14)=(1/2,1/2,5/18,1/3).
        # Com R=[1,2,3,4], S=(1/2,3/8,1/3,1/4).
        # Com R=[1,2,3,4,5], S=(2/5,3/10,4/15,1/5),
        # e Horror (ID 13) passa a ter S=1/5.
        casos = [
            ([1], [(10, .73), (11, .425), (12, .2766666666666667)]),
            ([2], [(14, .73), (12, .385)]),
            ([1, 2], [(10, .405), (14, .405),
                      (12, .3308333333333333), (11, .2625)]),
            ([2, 1], [(10, .405), (14, .405),
                      (12, .3308333333333333), (11, .2625)]),
            ([1, 2, 3], [(11, .425), (10, .405),
                         (14, .2966666666666667), (12, .2405555555555556)]),
            ([1, 2, 3, 4], [(10, .405), (11, .34375),
                            (12, .2766666666666667), (14, .2425)]),
            ([1, 2, 3, 4, 5], [(10, .34), (11, .295),
                               (12, .2333333333333333), (13, .23), (14, .21)]),
        ]
        for referencias, esperados in casos:
            with self.subTest(referencias=referencias):
                sessao = Sessao(assistidos=[1, 2, 3, 4, 5], referencias=referencias)
                resultados = self.modelo.recomendar_perfil(sessao)
                self.conferir(resultados, esperados)
                self.assertFalse(set(referencias) &
                                 {f['movieId'] for f in resultados})
    def test_assistido_fora_das_referencias_tambem_e_excluido(self):
        sessao = Sessao(assistidos=[1, 10], referencias=[1])
        self.conferir(self.modelo.recomendar_perfil(sessao),
                      [(11, .425), (12, .2766666666666667)])
    def test_positivos_filtram_e_pontuam_proporcao_atendida(self):
        # P={Comedy,Action}: A(10)=1/2, A(12)=1, A(14)=1/2.
        # O ID 14 entra mesmo com S=0; o ID 11 sai por não atender P.
        sessao = Sessao(assistidos=[1, 2], referencias=[1],
                        positivos={'Comedy', 'Action'})
        self.conferir(self.modelo.recomendar_perfil(sessao),
                      [(10, .855), (12, .5266666666666667), (14, .205)])
    def test_negativo_e_exclusao_obrigatoria_sem_penalizar_outros(self):
        sessao = Sessao(assistidos=[1, 2], referencias=[1],
                        negativos={'Comedy'})
        self.conferir(self.modelo.recomendar_perfil(sessao), [(11, .425)])
    def test_negativos_prevalecem_sobre_afinidade_positiva(self):
        sessao = Sessao(assistidos=[1, 2], referencias=[1],
                        positivos={'Comedy', 'Action'}, negativos={'Comedy'})
        self.conferir(self.modelo.recomendar_perfil(sessao), [(14, .205)])
    def test_referencia_rejeitada_nao_contribui_para_similaridade(self):
        # Mesmo que o ID permaneça nas referências recebidas pelo motor,
        # a rejeição impede sua contribuição. Resta apenas a referência 2.
        sessao = Sessao(assistidos=[1, 2], referencias=[1, 2], rejeitados={1})
        self.conferir(self.modelo.recomendar_perfil(sessao),
                      [(14, .73), (12, .385)])
    def test_sem_referencias_ativas_nao_gera_ranking_geral(self):
        sessao = Sessao(assistidos=[1, 2], referencias=[], rejeitados={1, 2})
        # RF-01 aprovado: substitui explicitamente o antigo fallback W/50.
        self.conferir(self.modelo.recomendar_perfil(sessao), [])
        self.assertEqual(sessao.assistidos, [1, 2])
        self.assertEqual(sessao.rejeitados, {1, 2})
    def test_sem_referencias_ativas_nao_recomenda_mesmo_com_preferencia(self):
        sessao = Sessao(assistidos=[1, 2], referencias=[],
                        rejeitados={1, 2}, positivos={'Action'})
        # Preferência explícita não dispensa a referência ativa obrigatória.
        self.conferir(self.modelo.recomendar_perfil(sessao), [])
        self.assertEqual(sessao.positivos, {'Action'})
    def test_referencias_todas_rejeitadas_nao_contam_como_ativas(self):
        sessao = Sessao(assistidos=[1, 2], referencias=[1, 2],
                        rejeitados={1, 2}, positivos={'Action'})
        self.conferir(self.modelo.recomendar_perfil(sessao), [])
    def test_referencias_fora_do_catalogo_nao_habilitam_recomendacao(self):
        sessao = Sessao(assistidos=[1], referencias=[999], positivos={'Action'})
        self.conferir(self.modelo.recomendar_perfil(sessao), [])
    def test_motor_nao_recomenda_com_mais_de_cinco_referencias_ativas(self):
        # Defesa do motor contra estado inválido; a conversa nunca cria seis.
        sessao = Sessao(assistidos=[1, 2, 3, 4, 5, 10], referencias=[1, 2, 3, 4, 5, 10])
        self.conferir(self.modelo.recomendar_perfil(sessao), [])
    def test_marcador_sem_generos_nao_cria_similaridade(self):
        sessao = Sessao(assistidos=[15], referencias=[15])
        self.conferir(self.modelo.recomendar_perfil(sessao), [])
    def test_sem_candidatos_nao_relaxa_restricoes(self):
        sessao = Sessao(assistidos=[1, 2], referencias=[1],
                        negativos={'Drama', 'Comedy', 'Action', 'Horror'})
        self.conferir(self.modelo.recomendar_perfil(sessao), [])
    def test_sem_historico_nao_recomenda(self):
        self.conferir(self.modelo.recomendar_perfil(Sessao()), [])
    def test_desempates_por_nota_contagem_e_menor_id(self):
        filmes = pd.DataFrame([
            (1, 'Referência (2000)', 'Drama|Comedy', 2000),
            (10, 'Menor nota (2000)', 'Drama', 2000),
            (30, 'Mesmo score C (2000)', 'Drama|Comedy|Action|Adventure|Horror', 2000),
            (20, 'Mesmo score B (2000)', 'Drama|Comedy|Action|Adventure|Horror', 2000),
            (40, 'Maior contagem (2000)', 'Drama|Comedy|Action|Adventure|Horror', 2000),
        ], columns=['movieId', 'title', 'genres', 'ano'])
        stats = pd.DataFrame([
            (1, 5, 5., 5.), (10, 100, 1., 1.),
            (30, 6, 4.25, 4.25), (20, 6, 4.25, 4.25),
            (40, 9, 4.25, 4.25),
        ], columns=['movieId', 'contagem', 'media', 'nota_ponderada'])
        # ID 10: 0,65*(1/2)+0,10*(1/5)=0,345.
        # Outros: 0,65*(2/5)+0,10*(4,25/5)=0,345.
        # Todos empatam no score: W vence a contagem 100 do ID 10;
        # entre W=4,25, contagem 9 vence 6; por fim, ID 20 vence 30.
        sessao = Sessao(assistidos=[1], referencias=[1])
        for ordem in [filmes.index, filmes.index[::-1]]:
            with self.subTest(ordem=list(ordem)):
                modelo = Recomendador(filmes.loc[ordem], stats)
                resultados = modelo.recomendar_perfil(sessao)
                self.conferir(resultados,
                              [(40, .345), (20, .345), (30, .345), (10, .345)])
                # Empate exato no cálculo atual: evita testar desempate
                # secundário usando scores que apenas parecem iguais.
                self.assertEqual(len({f['pontuacao'] for f in resultados}), 1)
    def test_limite_padrao_dez_e_corte_de_lista(self):
        filmes = pd.DataFrame(
            [(i, f'Sintético {i} (2000)', 'Drama', 2000)
             for i in range(13, 0, -1)],
            columns=['movieId', 'title', 'genres', 'ano'])
        stats = pd.DataFrame(
            [(i, 5, 4., 4.) for i in range(1, 14)],
            columns=['movieId', 'contagem', 'media', 'nota_ponderada'])
        modelo = Recomendador(filmes, stats)
        sessao = Sessao(assistidos=[1], referencias=[1])
        # S=1 e W=4: score=0,65+0,08=0,73; empata por menor ID.
        self.conferir(modelo.recomendar_perfil(sessao),
                      [(i, .73) for i in range(2, 12)])
        self.conferir(modelo.recomendar_perfil(sessao, k=3),
                      [(2, .73), (3, .73), (4, .73)])

class CarregamentoMovieLens(unittest.TestCase):

    RATINGS = ('userId,movieId,rating,timestamp,extra\n'
                   '2,10,6.0,100,original\n1,20,2.5,200,preservado\n')

    MOVIES = ('movieId,title,genres\n20,"Título, Dois (2001)",Comedy\n'
                  '10,Primeiro (2000),Drama|Comedy\n')

    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.raiz = Path(temporaria.name)
        self.destino = self.raiz / 'catalogo'
        rede = patch('urllib.request.urlopen',
                     side_effect=AssertionError('Download real proibido neste teste'))
        self.download = rede.start()
        self.addCleanup(rede.stop)
    def escrever_csvs(self, destino):
        destino.mkdir(parents=True, exist_ok=True)
        (destino / 'ratings.csv').write_text(self.RATINGS, encoding='utf-8')
        (destino / 'movies.csv').write_text(self.MOVIES, encoding='utf-8')
    def pacote(self, omitir=None):
        arquivo = io.BytesIO()
        with zipfile.ZipFile(arquivo, 'w') as z:
            for nome, texto in {
                'ratings.csv': self.RATINGS, 'movies.csv': self.MOVIES,
                'tags.csv': '', 'links.csv': '', 'README.txt': 'Base sintética',
            }.items():
                if nome != omitir:
                    z.writestr('ml-latest-small/' + nome, texto)
        return arquivo.getvalue()
    def conferir_tabelas(self, resultado):
        self.assertIsInstance(resultado, tuple)
        self.assertEqual(len(resultado), 2)
        ratings, movies = resultado
        # Inclusive ordem, tipos inferidos e coluna adicional. A nota 6 é
        # deliberada: carregar lê o original; limpar é outra responsabilidade.
        pd.testing.assert_frame_equal(ratings, pd.DataFrame({
            'userId': [2, 1], 'movieId': [10, 20], 'rating': [6., 2.5],
            'timestamp': [100, 200], 'extra': ['original', 'preservado'],
        }))
        pd.testing.assert_frame_equal(movies, pd.DataFrame({
            'movieId': [20, 10],
            'title': ['Título, Dois (2001)', 'Primeiro (2000)'],
            'genres': ['Comedy', 'Drama|Comedy'],
        }))
    def test_csvs_locais_preservam_dados_e_nao_consultam_zip_ou_rede(self):
        self.escrever_csvs(self.destino)
        (self.raiz / 'ml-latest-small.zip').write_bytes(b'ZIP invalido ignorado')
        origem = self.raiz / 'origem.json'
        origem.write_text('registro anterior', encoding='utf-8')
        for pasta in [self.destino, str(self.destino)]:
            with self.subTest(pasta=pasta), contextlib.redirect_stdout(io.StringIO()) as saida:
                self.conferir_tabelas(modulo.carregar(pasta))
                self.assertEqual(saida.getvalue(), '')
        self.assertEqual(origem.read_text(), 'registro anterior')
        self.download.assert_not_called()
    def test_pasta_padrao_respeita_root_do_ponto_de_entrada(self):
        destino = self.raiz / 'dados/ml-latest-small'
        self.escrever_csvs(destino)
        with patch.object(modulo, 'ROOT', self.raiz):
            for pasta in [None, '']:
                with self.subTest(pasta=pasta):
                    self.conferir_tabelas(modulo.carregar(pasta))
        self.assertFalse((destino.parent / 'origem.json').exists())
        self.download.assert_not_called()
    def test_zip_local_extrai_arquivos_e_registra_origem(self):
        arquivo = self.pacote()
        zip_local = self.raiz / 'ml-latest-small.zip'
        zip_local.write_bytes(arquivo)
        # Um CSV ausente dispara a extração de todos, inclusive sobrescrevendo
        # o que já existia. Caracteriza a política atual, sem alterá-la.
        self.destino.mkdir()
        (self.destino / 'movies.csv').write_text('incompleto')
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            self.conferir_tabelas(modulo.carregar(self.destino))
        self.assertEqual(saida.getvalue(), 'Usando ZIP local: ' + str(zip_local) + '\n')
        self.assertEqual({p.name for p in self.destino.iterdir()},
                         {'ratings.csv', 'movies.csv', 'tags.csv', 'links.csv', 'README.txt'})
        self.assertEqual(json.loads((self.raiz / 'origem.json').read_text()), {
            'url': modulo.URL, 'arquivo_local': str(zip_local),
            'sha256_zip': hashlib.sha256(arquivo).hexdigest(),
        })
        self.download.assert_not_called()
    def test_download_simulado_preserva_url_timeout_e_nao_salva_zip(self):
        arquivo = self.pacote()
        resposta = io.BytesIO(arquivo)
        self.download.side_effect = None
        self.download.return_value = resposta
        url = 'https://example.invalid/movielens-sintetico.zip'
        with patch.object(modulo, 'URL', url), contextlib.redirect_stdout(io.StringIO()) as saida:
            self.conferir_tabelas(modulo.carregar(self.destino))
        self.download.assert_called_once_with(url, timeout=60)
        self.assertTrue(resposta.closed)
        self.assertEqual(saida.getvalue(), 'Baixando MovieLens oficial...\n')
        self.assertFalse((self.raiz / 'ml-latest-small.zip').exists())
        self.assertEqual(json.loads((self.raiz / 'origem.json').read_text()), {
            'url': url, 'arquivo_local': None,
            'sha256_zip': hashlib.sha256(arquivo).hexdigest(),
        })
    def test_erros_rede_e_certificado_preservam_mensagem_e_causa(self):
        import ssl
        for motivo, mensagem in [
            ('offline', 'Não foi possível baixar o MovieLens: offline'),
            (ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED'),
             'O Python não conseguiu validar o certificado HTTPS.'),
        ]:
            with self.subTest(motivo=motivo):
                erro = urllib.error.URLError(motivo)
                self.download.side_effect = erro
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError) as falha:
                    modulo.carregar(self.destino)
                esperado = (mensagem + '\nBaixe ' + modulo.URL + ' pelo navegador e salve em '
                            + str(self.raiz / 'ml-latest-small.zip')
                            + '\nDepois execute o aplicativo novamente. Também pode extrair '
                            + 'ratings.csv e movies.csv em ' + str(self.destino) + '.')
                self.assertEqual(str(falha.exception), esperado)
                self.assertIs(falha.exception.__cause__, erro)
                self.assertFalse((self.raiz / 'origem.json').exists())
    def test_zip_invalido_propaga_erro_sem_novo_tratamento(self):
        (self.raiz / 'ml-latest-small.zip').write_bytes(b'nao e zip')
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(zipfile.BadZipFile):
            modulo.carregar(self.destino)
        # O registro precede a abertura do ZIP na implementação atual.
        self.assertTrue((self.raiz / 'origem.json').exists())
        self.download.assert_not_called()
    def test_membro_ausente_preserva_extracao_parcial_e_keyerror(self):
        (self.raiz / 'ml-latest-small.zip').write_bytes(self.pacote(omitir='README.txt'))
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(KeyError):
            modulo.carregar(self.destino)
        self.assertTrue((self.destino / 'ratings.csv').exists())
        self.assertTrue((self.destino / 'links.csv').exists())
        self.assertFalse((self.destino / 'README.txt').exists())
        self.download.assert_not_called()
    def test_csv_vazio_propaga_erro_do_pandas(self):
        self.escrever_csvs(self.destino)
        (self.destino / 'ratings.csv').write_text('')
        with self.assertRaises(pd.errors.EmptyDataError):
            modulo.carregar(self.destino)
        self.download.assert_not_called()

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
            with patch('urllib.request.urlopen') as download:
                r, m = modulo.carregar(destino)
                download.assert_not_called()
                self.assertEqual(len(r), 1)
                self.assertEqual(len(m), 1)
                self.assertTrue((Path(pasta)/'origem.json').exists())
    def test_falha_certificado_tem_orientacao(self):
        import ssl
        import urllib.error
        erro = urllib.error.URLError(ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED'))
        with tempfile.TemporaryDirectory() as pasta, patch('urllib.request.urlopen', side_effect=erro):
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
