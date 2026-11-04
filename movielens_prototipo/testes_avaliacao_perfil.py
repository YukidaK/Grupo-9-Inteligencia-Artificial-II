"""Oráculos manuais e isolamento do experimento, sem dados reais ou rede."""
import contextlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from avaliacao_perfil import (
    METRICAS, avaliar_perfil, executar, gerar_listas, metricas_top10, selecionar_referencias,
)
from artefatos_resultados import ErroArtefatos, assinatura, validar_resultados
from recomendador import avaliar, preparar


class AvaliacaoPerfil(unittest.TestCase):
    def setUp(self):
        self.filmes = pd.DataFrame([(1,'A (2000)','Drama'),(2,'B (2000)','Drama'),
            (3,'C (2000)','Comedy'),(4,'D (2000)','Drama'),(99,'E (2000)','Comedy')],
            columns=['movieId','title','genres'])
        self.treino = pd.DataFrame([(1,1,5.,1),(1,3,1.,2),(2,2,5.,3),
            (2,4,4.,4),(2,3,2.,5),(3,99,1.,6)],
            columns=['userId','movieId','rating','timestamp'])
        self.teste = pd.DataFrame([(1,2,5.,10),(1,99,4.,11),(2,1,3.,12),(3,4,5.,13)],
            columns=['userId','movieId','rating','timestamp'])
        self.opcoes = {'min_usuario': 1, 'min_filme': 1, 'seed': 42}

    def test_metricas_manuais_preservam_relevante_inelegivel_no_denominador(self):
        m = metricas_top10([2,4], {2,99})
        self.assertAlmostEqual(m['precision_at_10'], .1)
        self.assertAlmostEqual(m['recall_at_10'], .5)
        self.assertAlmostEqual(m['ndcg_at_10'], 1/(1+1/math.log2(3)))

    def test_sem_positivos_e_indefinido_e_lista_vazia_com_positivos_e_zero(self):
        self.assertEqual(metricas_top10([1], set()), dict.fromkeys(METRICAS, None))
        self.assertEqual(metricas_top10([], {1}), dict.fromkeys(METRICAS, 0.))
        with self.assertRaises(ValueError): metricas_top10([1,1], {1})

    def test_referencias_sao_somente_positivos_do_treino_e_prefixos_aninhados(self):
        refs = selecionar_referencias(self.treino)
        self.assertEqual(refs[1], [1])
        self.assertEqual(set(refs[2]), {2,4})
        self.assertEqual(refs[3], [])
        self.assertNotIn(99, refs[1])  # Positivo somente no teste desse usuário.
        listas, _, _ = gerar_listas(self.treino, self.filmes, **self.opcoes)
        usuario = listas[(listas.userId==2) & (listas.metodo=='perfil')]
        a = json.loads(usuario[usuario.n_referencias==1].iloc[0].referencias)
        b = json.loads(usuario[usuario.n_referencias==2].iloc[0].referencias)
        self.assertEqual(a, b[:1])

    def test_teste_nao_pode_mudar_estatisticas_referencias_ou_listas(self):
        a, _, _, sa = avaliar_perfil(self.treino,self.teste,self.filmes,**self.opcoes)
        alterado = self.teste.copy(); alterado['rating'] = 1.
        b, _, _, sb = avaliar_perfil(self.treino,alterado,self.filmes,**self.opcoes)
        colunas = ['userId','n_referencias','metodo','referencias','recomendacoes','hash_candidatos']
        pd.testing.assert_frame_equal(a[colunas], b[colunas])
        pd.testing.assert_frame_equal(sa, sb)
        self.assertTrue(b[list(METRICAS)].isna().all().all())

    def test_sobreposicao_de_pares_e_rejeitada(self):
        teste = pd.concat([self.teste,self.treino.iloc[:1]],ignore_index=True)
        with self.assertRaisesRegex(ValueError,'Sobreposição'):
            avaliar_perfil(self.treino,teste,self.filmes,**self.opcoes)

    def test_exclui_todo_historico_inclusive_notas_baixas(self):
        listas, _, _ = gerar_listas(self.treino,self.filmes,**self.opcoes)
        for linha in listas[listas.elegivel].itertuples():
            vistos = set(self.treino.loc[self.treino.userId==linha.userId,'movieId'])
            self.assertFalse(set(json.loads(linha.recomendacoes)) & vistos)

    def test_algoritmos_usam_mesmos_usuarios_candidatos_e_relevancia(self):
        detalhes, resumo, _, _ = avaliar_perfil(self.treino,self.teste,self.filmes,**self.opcoes)
        for _, grupo in detalhes.groupby(['userId','n_referencias']):
            self.assertEqual(set(grupo.metodo), {'perfil','popularidade','nota_ponderada'})
            self.assertEqual(grupo.elegivel.nunique(), 1)
            self.assertEqual(grupo.hash_candidatos.nunique(dropna=False), 1)
            self.assertEqual(grupo.avaliado_metricas.nunique(), 1)
        linhas = detalhes[(detalhes.userId==1)&(detalhes.n_referencias==1)]
        for linha in linhas.itertuples():
            self.assertEqual(json.loads(linha.recomendacoes), [2,4])
            self.assertEqual(linha.relevantes_teste,2)
            self.assertAlmostEqual(linha.precision_at_10,.1)
            self.assertAlmostEqual(linha.recall_at_10,.5)
        base = resumo[(resumo.coorte=='por_n_disponivel')&(resumo.n_referencias==1)]
        self.assertTrue(base.usuarios_elegiveis.eq(2).all())
        self.assertTrue(base.usuarios_avaliados.eq(1).all())
        self.assertTrue(base.usuarios_sem_positivos_teste.eq(1).all())
        self.assertTrue(base.media_recomendacoes.eq(1.5).all())
        self.assertTrue(base.cobertura_usuarios.eq(1.).all())

    def test_insuficientes_nao_recebem_metricas_zero_artificiais(self):
        detalhes, resumo, _, _ = avaliar_perfil(self.treino,self.teste,self.filmes,**self.opcoes)
        insuf = detalhes[~detalhes.elegivel]
        self.assertTrue(insuf[list(METRICAS)].isna().all().all())
        self.assertTrue(insuf.n_recomendacoes.isna().all())
        sem_coorte = resumo[resumo.coorte=='fixa_5']
        self.assertTrue(sem_coorte.usuarios_elegiveis.eq(0).all())
        self.assertTrue(sem_coorte[list(METRICAS)].isna().all().all())

    def test_lista_vazia_permanece_na_media_quando_existem_positivos(self):
        detalhes, resumo, _, _ = avaliar_perfil(self.treino,self.teste,self.filmes,
            min_filme=20,min_usuario=1)
        avaliados = detalhes[detalhes.avaliado_metricas]
        self.assertTrue(avaliados.n_recomendacoes.eq(0).all())
        self.assertTrue(avaliados[list(METRICAS)].eq(0).all().all())
        base = resumo[(resumo.coorte=='por_n_disponivel')&(resumo.n_referencias==1)]
        self.assertTrue(base.cobertura_usuarios.eq(0).all())
        self.assertTrue(base.usuarios_sem_candidatos.eq(2).all())

    def test_reprodutibilidade_independe_da_ordem_das_linhas(self):
        a = avaliar_perfil(self.treino,self.teste,self.filmes,**self.opcoes)
        b = avaliar_perfil(self.treino.sample(frac=1,random_state=9),
            self.teste.sample(frac=1,random_state=10),self.filmes,**self.opcoes)
        for x,y in zip(a[:2],b[:2]): pd.testing.assert_frame_equal(x,y)
        self.assertEqual(a[2],b[2])

    def test_baselines_equivalem_a_avaliar_quando_universo_e_o_mesmo(self):
        filmes = self.filmes.copy(); filmes['genres'] = 'Drama'
        detalhes, _, _, stats = avaliar_perfil(self.treino,self.teste,filmes,**self.opcoes)
        # Usuários 1/2 têm referências; apenas 1 tem relevantes. O 3 não pode
        # entrar numa comparação pareada, pois não possui referências positivas.
        original,_ = avaliar(self.treino,self.teste[self.teste.userId.isin([1,2])],stats)
        for linha in original.itertuples():
            atual = detalhes[(detalhes.userId==linha.userId)&
                (detalhes.metodo==linha.metodo)&(detalhes.n_referencias==1)].iloc[0]
            for coluna in METRICAS:self.assertAlmostEqual(atual[coluna],getattr(linha,coluna))

    def test_ausencia_total_de_usuarios_aptos_e_explicita(self):
        with self.assertRaisesRegex(ValueError,'Nenhum usuário'):
            gerar_listas(self.treino,self.filmes,min_usuario=100)

    def test_runner_isola_saida_preserva_entradas_e_usa_manifesto_proprio(self):
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.urlopen',
                side_effect=AssertionError('rede proibida')):
            p=Path(tmp); dados=p/'dados'; dados.mkdir(); resultados=p/'resultados'; saida=p/'experimento'
            pd.DataFrame([(u,i,4.,100*u+i) for u in range(1,7) for i in range(1,9)],
                columns=['userId','movieId','rating','timestamp']).to_csv(dados/'ratings.csv',index=False)
            pd.DataFrame([(i,f'F {i} (2000)','Drama') for i in range(1,9)],
                columns=['movieId','title','genres']).to_csv(dados/'movies.csv',index=False)
            (dados/'README.txt').write_text('Base sintética')
            with contextlib.redirect_stdout(io.StringIO()):
                preparar(dados,diretorio_resultados=resultados)
            antes={str(f):assinatura(f) for folder in (dados,resultados) for f in folder.iterdir()}
            with contextlib.redirect_stdout(io.StringIO()): executar(resultados,dados,saida)
            self.assertEqual(antes, {f: assinatura(f) for f in antes})
            m=json.loads((saida/'manifesto.json').read_text())
            self.assertEqual(m['esquema'],'cinematch.experimento.perfil')
            for nome,valor in m['arquivos'].items():self.assertEqual(assinatura(saida/nome),valor)
            with self.assertRaises(ErroArtefatos): validar_resultados(saida)
            with self.assertRaises(FileExistsError): executar(resultados,dados,saida)
            with self.assertRaises(ValueError): executar(resultados,dados,resultados/'novo')


if __name__ == '__main__': unittest.main()
