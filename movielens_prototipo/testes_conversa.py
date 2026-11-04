"""Fixtures sintéticas, sem download; não medem qualidade das recomendações."""
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
from conversa import Conversa, Sessao, interpretar_mensagem
from app import Handler
from http.server import ThreadingHTTPServer


def fixture():
    filmes = pd.DataFrame([(i, f'Filme {i} (2000)', ['Drama', 'Thriller|Crime', 'Horror', 'Sci-Fi|Adventure'][i % 4], 2000) for i in range(1, 41)], columns=['movieId', 'title', 'genres', 'ano'])
    filmes.loc[0, 'title'] = 'Solaris (1972)'
    filmes.loc[1, 'title'] = 'Solaris (2002)'
    treino = pd.DataFrame([(u, i, float(3 + i % 3), i) for u in range(1, 7) for i in range(1, 41)], columns=['userId', 'movieId', 'rating', 'timestamp'])
    return Recomendador(filmes, ranking(treino), treino)


class CaracterizacaoPerfil(unittest.TestCase):
    """Oráculos manuais; não usa ranking(), dados reais nem arquivos de resultados."""

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

    def test_rejeitar_recomendacao_exclui_id_sem_rejeitar_seus_generos(self):
        sessao = Sessao(assistidos=[1, 2], referencias=[1])
        resposta = Conversa(self.modelo).executar(
            sessao, {'acao': 'rejeitar', 'movieId': 10})
        self.assertIn(10, sessao.assistidos)
        self.assertEqual(sessao.rejeitados, {10})
        self.assertEqual(sessao.negativos, set())
        self.assertEqual(sessao.referencias, [1])
        self.conferir(resposta['recomendacoes'],
                      [(11, .425), (12, .2766666666666667)])

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

    def test_retirada_neutra_preserva_historico_preferencias_e_excedentes(self):
        self.confirmar([1,2,3,4,5,6,7])
        self.s.positivos = {'Drama'}
        self.s.negativos = {'Horror'}
        self.s.rejeitados.add(7)
        d = self.c.executar(self.s, {'acao':'remover_referencia','movieId':2})
        self.assertEqual(self.s.referencias,[1,3,4,5])
        self.assertEqual(self.s.assistidos,[1,2,3,4,5,6,7])
        self.assertEqual(self.s.rejeitados,{7})
        self.assertEqual(d['preferencias'],{'positivas':['Drama'],'negativas':['Horror']})
        self.assertEqual([f['movieId'] for f in d['excedentes']],[2,6])
        self.assertIn('sem registrar',d['mensagem'])
        self.assertNotIn(2,[f['movieId'] for f in d['recomendacoes']])

    def test_retirar_todas_sem_preencher_vagas_e_retomar(self):
        self.confirmar([1,2,3,4,5,6,7])
        self.s.positivos={'Drama'}
        self.s.negativos={'Horror'}
        self.s.rejeitados={7}
        for i in (1,2,3,4,5):
            d = self.c.executar(self.s, {'acao':'remover_referencia','movieId':i})
        self.assertEqual(d['referencias'],[])
        self.assertEqual(d['recomendacoes'],[])
        self.assertEqual(self.s.assistidos,[1,2,3,4,5,6,7])
        self.assertEqual(self.s.rejeitados,{7})
        self.assertEqual(self.s.positivos,{'Drama'})
        self.assertEqual(self.s.negativos,{'Horror'})
        self.assertIn('Selecione pelo menos um filme',d['mensagem'])
        d = self.c.executar(self.s, {'acao':'considerar','movieId':4})
        self.assertEqual(self.s.referencias,[4])
        self.assertTrue(d['recomendacoes'])
        self.assertEqual(self.s.rejeitados,{7})

    def test_retirar_nao_altera_limite_nem_semantica_rejeitar(self):
        self.confirmar([1,2,3,4,5,6])
        self.c.executar(self.s,{'acao':'remover_referencia','movieId':1})
        self.c.executar(self.s,{'acao':'considerar','movieId':6})
        self.c.executar(self.s,{'acao':'considerar','movieId':1})
        self.assertEqual(self.s.referencias,[2,3,4,5,6])
        self.c.executar(self.s,{'acao':'considerar','movieId':1,'substituir':2})
        self.assertEqual(self.s.referencias,[1,3,4,5,6])
        self.c.executar(self.s,{'acao':'rejeitar','movieId':1})
        self.assertIn(1,self.s.rejeitados)
        self.assertIn(1,self.s.assistidos)
        with self.assertRaises(ValueError):
            self.c.executar(self.s,{'acao':'considerar','movieId':1})

    def test_retirada_invalida_nao_muda_estado(self):
        self.confirmar([1,2])
        antes = self.c.executar(self.s,{'acao':'estado'})
        for i in (None,True,'1',1.0,999,3):
            with self.subTest(movieId=i),self.assertRaises(ValueError):
                self.c.executar(self.s,{'acao':'remover_referencia','movieId':i})
        self.assertEqual(antes,self.c.executar(self.s,{'acao':'estado'}))

    def test_confirmacao_repetida_nao_reativa_referencia_removida(self):
        self.confirmar([1,2])
        self.c.executar(self.s,{'acao':'remover_referencia','movieId':1})
        self.c.executar(self.s,{'acao':'confirmar_selecao','ids':[1]})
        self.assertEqual(self.s.referencias,[2])
        self.assertNotIn(1,self.s.rejeitados)

    def test_uma_referencia_avisa_e_recomenda(self):
        d = self.confirmar([1])
        self.assertIn('abrangente', d['mensagem'])
        self.assertTrue(d['recomendacoes'])
        self.assertNotIn(1, [f['movieId'] for f in d['recomendacoes']])

    def test_duas_a_cinco(self):
        for n in range(2, 6):
            self.s = Sessao()
            with self.subTest(quantidade=n):
                d = self.confirmar(list(range(1, n+1)))
                self.assertEqual(self.s.referencias, list(range(1, n+1)))
                self.assertTrue(d['recomendacoes'])
                self.assertLessEqual(len(d['recomendacoes']), 10)
                if n == 2:
                    self.assertIn('2 referências ativas', d['mensagem'])
                    self.assertIn('sem garantir maior precisão', d['mensagem'])
                else:
                    self.assertNotIn('o perfil pode ficar abrangente', d['mensagem'])

    def test_rejeitar_ultima_referencia_preserva_perfil_e_permite_retomada(self):
        self.confirmar([1])
        self.msg('Quero mais suspense')
        self.msg('Não gosto de terror')
        d = self.c.executar(self.s, {'acao': 'rejeitar', 'movieId': 1})
        self.assertEqual(self.s.referencias, [])
        self.assertEqual(self.s.assistidos, [1])
        self.assertEqual(self.s.rejeitados, {1})
        self.assertEqual(self.s.positivos, {'Thriller'})
        self.assertEqual(self.s.negativos, {'Horror'})
        self.assertEqual(d['recomendacoes'], [])
        self.assertIn('Selecione pelo menos um filme', d['mensagem'])
        self.assertNotIn('candidatos adequados', d['mensagem'])
        for acao in ({'acao': 'estado'}, {'acao': 'mensagem', 'texto': 'Por que 1?'},
                     {'acao': 'mensagem', 'texto': 'comando desconhecido'}):
            with self.subTest(acao=acao):
                d = self.c.executar(self.s, acao)
                self.assertEqual(d['recomendacoes'], [])
                self.assertIn('Selecione pelo menos um filme', d['mensagem'])
        self.assertEqual(self.modelo.recomendar_perfil(self.s), [])
        d = self.confirmar([5])
        self.assertEqual(self.s.referencias, [5])
        self.assertEqual(self.s.assistidos, [1, 5])
        self.assertEqual(self.s.rejeitados, {1})
        self.assertEqual(self.s.positivos, {'Thriller'})
        self.assertEqual(self.s.negativos, {'Horror'})
        self.assertTrue(d['recomendacoes'])
        self.assertTrue(all('Thriller' in f['generos'] and 'Horror' not in f['generos']
                            for f in d['recomendacoes']))

    def test_retomar_considerando_filme_do_historico_sem_promover_rejeitados(self):
        self.confirmar([1, 4])
        self.msg('Quero drama')
        self.msg('Assisti Filme 8 (2000)')
        for i in [1, 4]:
            d = self.c.executar(self.s, {'acao': 'rejeitar', 'movieId': i})
        self.assertEqual(d['recomendacoes'], [])
        self.assertEqual(self.s.assistidos, [1, 4, 8])
        self.assertEqual(self.s.rejeitados, {1, 4})
        with self.assertRaises(ValueError):
            self.c.considerar(self.s, 1)
        d = self.c.executar(self.s, {'acao': 'considerar', 'movieId': 8})
        self.assertEqual(self.s.referencias, [8])
        self.assertEqual(self.s.assistidos, [1, 4, 8])
        self.assertEqual(self.s.rejeitados, {1, 4})
        self.assertEqual(self.s.positivos, {'Drama'})
        self.assertTrue(d['recomendacoes'])

    def test_estado_sem_referencias_limpa_somente_recomendacoes_em_cache(self):
        self.s = Sessao(assistidos=[1], rejeitados={1}, positivos={'Thriller'},
                        negativos={'Horror'}, recomendacoes=[{'movieId': 2}])
        d = self.c.executar(self.s, {'acao': 'estado'})
        self.assertEqual(d['recomendacoes'], [])
        self.assertEqual(d['referencias'], [])
        self.assertEqual([f['movieId'] for f in d['assistidos']], [1])
        self.assertEqual([f['movieId'] for f in d['rejeitados']], [1])
        self.assertEqual(d['preferencias'], {'positivas': ['Thriller'], 'negativas': ['Horror']})
        self.assertIn('Selecione pelo menos um filme', d['mensagem'])

    def test_excedentes_duplicatas_e_limite(self):
        d = self.confirmar([1, 1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(self.s.referencias, [1, 2, 3, 4, 5])
        self.assertEqual([f['movieId'] for f in d['excedentes']], [6, 7])
        ids = [f['movieId'] for f in d['recomendacoes']]
        self.assertFalse(set(ids) & set(range(1, 8)))
        self.assertEqual(len(set(ids)), len(ids))
        self.assertLessEqual(len(ids), 10)
        self.assertIn('Referências ativas', d['mensagem'])
        self.assertIn('apenas no histórico', d['mensagem'])

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
        d = self.c.executar(self.s, {'acao': 'estado'})
        self.assertEqual(d['referencias'], [])
        self.assertEqual(d['recomendacoes'], [])
        self.assertIn('Selecione pelo menos um filme', d['mensagem'])

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


class CarregamentoMovieLens(unittest.TestCase):
    """Contrato do carregador compatível; arquivos sintéticos e rede simulada."""

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
        post({'acao': 'rejeitar', 'movieId': 1}, cookie)
        h, d, _ = post({'acao': 'rejeitar', 'movieId': 4}, cookie)
        self.assertIn(b'200 OK', h)
        self.assertEqual(d['referencias'], [])
        self.assertEqual(d['recomendacoes'], [])
        self.assertEqual([f['movieId'] for f in d['assistidos']], [1, 4])
        self.assertEqual([f['movieId'] for f in d['rejeitados']], [1, 4])
        self.assertEqual(d['preferencias']['negativas'], ['Horror'])
        self.assertIn('Selecione pelo menos um filme', d['mensagem'])
        _, d, _ = post({'acao': 'estado'}, cookie)
        self.assertEqual(d['recomendacoes'], [])
        h, d, _ = post({'acao': 'confirmar_selecao', 'ids': [8]}, cookie)
        self.assertIn(b'200 OK', h)
        self.assertEqual([f['movieId'] for f in d['referencias']], [8])
        self.assertTrue(d['recomendacoes'])
        self.assertEqual(d['preferencias']['negativas'], ['Horror'])
        # UX-01: mesma rota/cookie, retirada neutra e retomada sem rejeição.
        h, d, _ = post({'acao':'remover_referencia','movieId':8},cookie)
        self.assertIn(b'200 OK',h)
        self.assertEqual(d['referencias'],[])
        self.assertEqual(d['recomendacoes'],[])
        self.assertIn(8,[f['movieId'] for f in d['assistidos']])
        self.assertNotIn(8,[f['movieId'] for f in d['rejeitados']])
        self.assertEqual(d['preferencias']['negativas'],['Horror'])
        self.assertIn('Selecione pelo menos um filme',d['mensagem'])
        h, _, _ = post({'acao':'remover_referencia','movieId':8},cookie)
        self.assertIn(b'400 Bad Request',h)
        h, d, _ = post({'acao':'considerar','movieId':8},cookie)
        self.assertIn(b'200 OK',h)
        self.assertEqual([f['movieId'] for f in d['referencias']],[8])
        self.assertTrue(d['recomendacoes'])
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
