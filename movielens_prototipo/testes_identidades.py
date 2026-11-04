"""Identidades e ponte MovieLens; somente dados sintéticos, sem rede ou arquivos reais."""
from dataclasses import FrozenInstanceError
import json
import unittest

import numpy as np
import pandas as pd

from identidades import (
    FONTE_MOVIELENS, TipoConteudo, IdentidadeConteudo, IdentidadeUsuario,
    conteudo_movielens, usuario_movielens, movie_id_legado, user_id_legado,
)
from recomendador import Recomendador
from conversa import Conversa, Sessao
from busca import BuscaCatalogo
from testes_conversa import fixture


class Identidades(unittest.TestCase):
    def test_conteudos_de_fontes_diferentes_com_mesmo_id_nao_colidem(self):
        a = IdentidadeConteudo('fonte-a', TipoConteudo.FILME, '1')
        b = IdentidadeConteudo('fonte-b', TipoConteudo.FILME, '1')
        self.assertNotEqual(a, b)
        indice = {a: 'registro A', b: 'registro B'}
        self.assertEqual(len(indice), 2)
        self.assertEqual(indice[a], 'registro A')
        self.assertEqual(indice[b], 'registro B')

    def test_filme_e_serie_na_mesma_fonte_nao_colidem(self):
        filme = IdentidadeConteudo('fonte-a', TipoConteudo.FILME, '1')
        serie = IdentidadeConteudo('fonte-a', TipoConteudo.SERIE, '1')
        self.assertNotEqual(filme, serie)
        self.assertEqual(len({filme, serie}), 2)
        # Somente representação: não se fornece série ao recomendador.

    def test_usuarios_historicos_de_fontes_diferentes_nao_colidem(self):
        a, b = IdentidadeUsuario('fonte-a', '7'), IdentidadeUsuario('fonte-b', '7')
        self.assertNotEqual(a, b)
        self.assertEqual(len({a: 'A', b: 'B'}), 2)

    def test_identidades_iguais_possuem_hash_compativel_e_sao_imutaveis(self):
        for a, b in ((conteudo_movielens(7), conteudo_movielens(7)),
                     (usuario_movielens(7), usuario_movielens(7))):
            with self.subTest(classe=type(a).__name__):
                self.assertEqual(a, b)
                self.assertEqual(hash(a), hash(b))
                with self.assertRaises(FrozenInstanceError):
                    a.id_original = '8'

    def test_conteudo_e_usuario_nao_se_confundem(self):
        self.assertNotEqual(conteudo_movielens(1), usuario_movielens(1))
        self.assertEqual(len({conteudo_movielens(1), usuario_movielens(1)}), 2)

    def test_roundtrip_movie_id_preserva_inteiro_original(self):
        for valor in (1, 42, 193609, np.int64(42)):
            with self.subTest(valor=valor):
                identidade = conteudo_movielens(valor)
                self.assertEqual(identidade, IdentidadeConteudo(
                    FONTE_MOVIELENS, TipoConteudo.FILME, str(int(valor))))
                legado = movie_id_legado(identidade)
                self.assertEqual(legado, int(valor))
                self.assertIs(type(legado), int)

    def test_roundtrip_user_id_preserva_inteiro_original(self):
        for valor in (1, 610, np.int64(7)):
            with self.subTest(valor=valor):
                identidade = usuario_movielens(valor)
                self.assertEqual(identidade, IdentidadeUsuario(FONTE_MOVIELENS, str(int(valor))))
                self.assertEqual(user_id_legado(identidade), int(valor))
                self.assertIs(type(user_id_legado(identidade)), int)

    def test_ids_movielens_invalidos_nao_sofrem_coercao(self):
        for valor in (True, False, np.bool_(True), 0, -1, 1., 1.5, '1', '01', None, [], {}):
            for converter in (conteudo_movielens, usuario_movielens):
                with self.subTest(valor=valor, converter=converter.__name__):
                    with self.assertRaises(ValueError):
                        converter(valor)

    def test_fontes_invalidas_ou_ambiguas_sao_rejeitadas(self):
        for fonte in ('', 'MovieLens', ' movielens', 'movielens ', 'fonte a',
                      'https://exemplo.invalid', '1fonte', 'fonte..a', None, 1):
            with self.subTest(fonte=fonte):
                with self.assertRaises(ValueError):
                    IdentidadeConteudo(fonte, TipoConteudo.FILME, '1')
                with self.assertRaises(ValueError):
                    IdentidadeUsuario(fonte, '1')

    def test_ids_originais_invalidos_ou_ambiguos_sao_rejeitados(self):
        for valor in ('', ' 1', '1 ', '1 2', '1\n', '1\x00', None, True, 1, 1.):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    IdentidadeConteudo('fonte-a', TipoConteudo.FILME, valor)
                with self.assertRaises(ValueError):
                    IdentidadeUsuario('fonte-a', valor)

    def test_tipo_exige_enum_sem_adivinhar_texto(self):
        for tipo in ('FILME', 'SERIE', 'filme', 'episodio', None, 1):
            with self.subTest(tipo=tipo), self.assertRaises(ValueError):
                IdentidadeConteudo('fonte-a', tipo, '1')

    def test_ids_opacos_nao_sao_normalizados_ou_associados(self):
        # Fora da ponte MovieLens, zeros e caixa pertencem ao identificador.
        ids = [IdentidadeConteudo('fonte-a', TipoConteudo.FILME, valor)
               for valor in ('1', '01', 'ABC', 'abc')]
        self.assertEqual(len(set(ids)), 4)
        imdb = IdentidadeConteudo('imdb', TipoConteudo.FILME, '0114709')
        self.assertEqual(imdb.id_original, '0114709')
        self.assertNotEqual(imdb, IdentidadeConteudo('tmdb', TipoConteudo.FILME, '0114709'))

    def test_converter_para_legado_rejeita_fonte_tipo_e_entidade_errados(self):
        for valor in (IdentidadeConteudo('outra', TipoConteudo.FILME, '1'),
                      IdentidadeConteudo('movielens', TipoConteudo.SERIE, '1'),
                      usuario_movielens(1), 1, None):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                movie_id_legado(valor)
        for valor in (IdentidadeUsuario('outra', '1'), conteudo_movielens(1),
                      'cookie-do-visitante', 1, None):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                user_id_legado(valor)

    def test_legado_rejeita_identificador_original_nao_canonico(self):
        for valor in ('01', '0', '-1', '+1', '1.0', '١'):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    movie_id_legado(IdentidadeConteudo('movielens', TipoConteudo.FILME, valor))
                with self.assertRaises(ValueError):
                    user_id_legado(IdentidadeUsuario('movielens', valor))

    def test_identidade_nao_introduz_ordenacao_lexicografica(self):
        with self.assertRaises(TypeError):
            sorted([conteudo_movielens(10), conteudo_movielens(2)])


class PonteMovieLens(unittest.TestCase):
    def setUp(self):
        # Ordem intencionalmente diferente do desempate numérico e títulos
        # repetidos: identidade não pode ser inferida pelo nome da obra.
        self.filmes = pd.DataFrame([
            (1, 'Referência (2000)', 'Drama', 2000),
            (30, 'Mesmo título (2001)', 'Drama', 2001),
            (10, 'Mesmo título (2001)', 'Drama', 2001),
            (20, 'Mesmo título (2001)', 'Drama', 2001),
        ], columns=['movieId', 'title', 'genres', 'ano'])
        self.stats = pd.DataFrame([(i, 5, 4., 4.) for i in [1, 30, 10, 20]],
            columns=['movieId', 'contagem', 'media', 'nota_ponderada'])
        self.treino = pd.DataFrame([(7, 1, 4., 100), (8, 10, 4., 101)],
            columns=['userId', 'movieId', 'rating', 'timestamp'])
        self.modelo = Recomendador(self.filmes, self.stats, self.treino)

    def test_mapas_internos_preservam_ids_tabelas_e_vistos_legados(self):
        self.assertEqual(self.modelo.identidades_conteudo,
                         {i: conteudo_movielens(i) for i in (1, 30, 10, 20)})
        self.assertEqual(self.modelo.identidades_usuarios,
                         {7: usuario_movielens(7), 8: usuario_movielens(8)})
        self.assertEqual(self.modelo.vistos, {7: {1}, 8: {10}})
        self.assertEqual(self.modelo.vistos_identificados, {
            usuario_movielens(7): frozenset({conteudo_movielens(1)}),
            usuario_movielens(8): frozenset({conteudo_movielens(10)}),
        })
        pd.testing.assert_frame_equal(self.modelo.filmes, self.filmes)
        self.assertEqual(list(self.modelo.catalogo.movieId), [1, 30, 10, 20])
        self.assertEqual(list(self.filmes.columns), ['movieId', 'title', 'genres', 'ano'])
        self.assertEqual(list(self.treino.userId), [7, 8])

    def test_mesmo_titulo_ano_e_genero_nao_unificam_conteudos(self):
        identidades = self.modelo.identidades_conteudo
        self.assertEqual(len(identidades), 4)
        self.assertEqual(len({identidades[i] for i in (10, 20, 30)}), 3)

    def test_recomendacao_preserva_score_e_desempate_numerico(self):
        resultado = self.modelo.recomendar_perfil(Sessao(assistidos=[1], referencias=[1]))
        self.assertEqual([f['movieId'] for f in resultado], [10, 20, 30])
        for filme in resultado:
            self.assertAlmostEqual(filme['pontuacao'], .73, delta=1e-12)
            self.assertIs(type(filme['movieId']), int)
        # Os objetos de identidade não vazam para o JSON público.
        self.assertEqual(json.loads(json.dumps(resultado)), resultado)
        self.assertEqual(set(resultado[0]), {
            'movieId', 'titulo', 'ano', 'generos', 'nota_media_treino',
            'avaliacoes_treino', 'motivo', 'pontuacao'})

    def test_busca_e_conversa_preservam_ids_e_campos_publicos(self):
        busca = BuscaCatalogo(self.modelo.filmes).buscar('Mesmo')
        self.assertEqual([f['movieId'] for f in busca], [10, 20, 30])
        self.assertEqual(set(busca[0]), {'movieId', 'titulo', 'ano', 'generos', 'correspondencia'})
        resposta = Conversa(self.modelo).executar(Sessao(),
            {'acao': 'confirmar_selecao', 'ids': [1]})
        self.assertEqual(resposta['referencias'][0]['movieId'], 1)
        self.assertEqual(set(resposta['referencias'][0]), {'movieId', 'titulo', 'ano', 'generos'})
        self.assertEqual([f['movieId'] for f in resposta['recomendacoes']], [10, 20, 30])
        json.dumps(resposta)

    def test_visitante_nao_e_usuario_historico_do_dataset(self):
        modelo = fixture()  # Cada usuário histórico avaliou todo o catálogo.
        self.assertEqual(len(modelo.vistos[1]), 40)
        sessao = Sessao(assistidos=[1], referencias=[1])
        resultado = modelo.recomendar_perfil(sessao)
        self.assertTrue(resultado)  # Não exclui o histórico do userId=1.
        self.assertNotIn(1, [f['movieId'] for f in resultado])
        self.assertEqual(sessao.assistidos, [1])

    def test_sem_treino_nao_cria_usuarios_historicos_a_partir_da_sessao(self):
        modelo = Recomendador(self.filmes, self.stats)
        modelo.recomendar_perfil(Sessao(assistidos=[1], referencias=[1]))
        self.assertEqual(modelo.identidades_usuarios, {})
        self.assertEqual(modelo.vistos_identificados, {})
        self.assertEqual(modelo.vistos, {})


if __name__ == '__main__':
    unittest.main()
