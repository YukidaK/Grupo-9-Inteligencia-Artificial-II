"""Resultados isolados e metadados: somente CSVs sintéticos e diretórios temporários."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from scipy.sparse import load_npz, save_npz

import recomendador as modulo
from conversa import Sessao
from artefatos_resultados import (
    ARQUIVOS, MANIFESTO, PENDENTE, ESQUEMA, VERSAO_ESQUEMA,
    ErroArtefatos, assinatura, validar_resultados,
)


class Artefatos(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.raiz = Path(temporaria.name)
        self.dados = self.raiz / 'entrada'
        self.dados.mkdir()
        self.saida = self.raiz / 'execucao-a'
        self.dataset = {'nome': 'Fixture acadêmica', 'versao': 'sintetica-v1', 'fonte': 'teste-local'}
        movies = pd.DataFrame([(i, f'Sintético {i} (2000)', 'Drama|Comedy')
                               for i in range(1, 9)], columns=['movieId', 'title', 'genres'])
        ratings = pd.DataFrame([(u, i, float(3+i % 3), u*100+i)
                                for u in range(1, 7) for i in range(1, 9)],
                               columns=['userId', 'movieId', 'rating', 'timestamp'])
        movies.to_csv(self.dados / 'movies.csv', index=False)
        ratings.to_csv(self.dados / 'ratings.csv', index=False)
        rede = patch('urllib.request.urlopen', side_effect=AssertionError('Rede proibida'))
        self.rede = rede.start()
        self.addCleanup(rede.stop)

    def gerar(self, saida=None, **opcoes):
        with contextlib.redirect_stdout(io.StringIO()):
            return modulo.preparar(self.dados,
                diretorio_resultados=self.saida if saida is None else saida,
                **opcoes)

    def identificado(self, **opcoes):
        return self.gerar(identificar=True, dataset=self.dataset, **opcoes)

    def manifesto(self):
        return json.loads((self.saida / MANIFESTO).read_text())

    def escrever_manifesto(self, manifesto):
        (self.saida / MANIFESTO).write_text(json.dumps(manifesto), encoding='utf-8')

    def reassinar(self, nome):
        manifesto = self.manifesto()
        manifesto['arquivos'][nome] = assinatura(self.saida / nome)
        self.escrever_manifesto(manifesto)

    def test_diretorio_opcional_preserva_artefatos_e_retorno_padrao(self):
        raiz_legada = self.raiz / 'app'
        raiz_legada.mkdir()
        with patch.object(modulo, 'ROOT', raiz_legada), contextlib.redirect_stdout(io.StringIO()) as log:
            anterior = modulo.preparar(self.dados)
        saida = self.raiz / 'isolado/aninhado'
        with contextlib.redirect_stdout(io.StringIO()) as outro_log:
            atual = modulo.preparar(self.dados, diretorio_resultados=saida)
        self.assertEqual(log.getvalue(), outro_log.getvalue())
        for antes, depois in zip(anterior, atual):
            pd.testing.assert_frame_equal(antes, depois)
        for nome in ARQUIVOS:
            if nome == 'matriz_treino.npz':
                a, b = load_npz(raiz_legada/'resultados'/nome), load_npz(saida/nome)
                self.assertEqual(a.shape, b.shape)
                self.assertEqual((a != b).nnz, 0)
            else:
                self.assertEqual((raiz_legada/'resultados'/nome).read_bytes(), (saida/nome).read_bytes())
        self.assertFalse((saida / MANIFESTO).exists())
        self.rede.assert_not_called()

    def test_manifesto_vincula_todos_os_arquivos_parametros_e_fontes(self):
        self.identificado()
        m = self.manifesto()
        self.assertEqual((m['esquema'], m['versao_esquema']), (ESQUEMA, VERSAO_ESQUEMA))
        self.assertEqual(m['dataset'], self.dataset)
        self.assertEqual(m['parametros'], {
            'seed': 42, 'fracao_teste': .2, 'min_avaliacoes_filme_treino': 5,
            'min_avaliacoes_usuario_treino': 5, 'k': 10, 'relevante': 4.,
        })
        self.assertEqual(set(m['arquivos']), set(ARQUIVOS))
        for nome in ARQUIVOS:
            self.assertEqual(m['arquivos'][nome], assinatura(self.saida/nome))
        for nome in ('ratings.csv', 'movies.csv'):
            self.assertEqual(m['entradas'][nome], assinatura(self.dados/nome))
        self.assertFalse((self.saida / PENDENTE).exists())
        self.assertTrue(validar_resultados(self.saida)['integridade_verificada'])

    def test_versao_desconhecida_nao_e_inventada(self):
        self.gerar(identificar=True)
        self.assertEqual(self.manifesto()['dataset'], {
            'nome': 'MovieLens Latest Small', 'versao': None, 'fonte': modulo.URL})

    def test_modelo_identificado_preserva_recomendacoes_do_legado(self):
        self.identificado()
        outra = self.raiz/'legado'
        self.gerar(outra)
        identificado = modulo.carregar_modelo(self.saida, exigir_manifesto=True,
            dataset_esperado=self.dataset, execucao_esperada=self.manifesto()['execucao_id'])
        legado = modulo.carregar_modelo(outra)
        sessao = Sessao(assistidos=[1], referencias=[1])
        self.assertEqual(identificado.recomendar_perfil(sessao), legado.recomendar_perfil(sessao))
        pd.testing.assert_frame_equal(identificado.filmes, legado.filmes)
        pd.testing.assert_frame_equal(identificado.catalogo, legado.catalogo)
        self.assertEqual(identificado.vistos, legado.vistos)

    def test_legado_minimo_continua_carregando_sem_afirmar_integridade(self):
        self.gerar()
        for nome in ARQUIVOS:
            if nome not in ('filmes.csv', 'ranking_treino.csv', 'treino.csv', 'relatorio.json'):
                (self.saida / nome).unlink()
        # O loader antigo só usava a existência do relatório, não seu conteúdo.
        (self.saida/'relatorio.json').write_text('{}')
        with patch.object(modulo, 'ROOT', self.raiz):
            # Muda apenas o nome do diretório temporário para o padrão antigo.
            self.saida.rename(self.raiz/'resultados')
            modelo = modulo.carregar_modelo()
            self.assertFalse(modelo.catalogo.empty)
            self.assertEqual(validar_resultados(self.raiz/'resultados'),
                {'estado': 'legado_sem_manifesto', 'integridade_verificada': False})

    def test_padrao_legado_ainda_chama_preparar_sem_argumentos_se_relatorio_faltar(self):
        self.gerar()
        (self.saida/'relatorio.json').unlink()
        self.saida.rename(self.raiz/'resultados')
        with patch.object(modulo, 'ROOT', self.raiz), patch.object(modulo, 'preparar') as preparar:
            modulo.carregar_modelo()
        preparar.assert_called_once_with()

    def test_diretorio_explicito_ausente_nao_dispara_preparacao_ou_download(self):
        with patch.object(modulo, 'preparar') as preparar, self.assertRaises(ErroArtefatos):
            modulo.carregar_modelo(self.saida)
        preparar.assert_not_called()
        self.rede.assert_not_called()

    def test_exigencia_de_manifesto_recusa_legado_e_manifesto_removido(self):
        self.identificado()
        (self.saida/MANIFESTO).unlink()
        for opcoes in ({'exigir_manifesto': True}, {'dataset_esperado': self.dataset},
                       {'execucao_esperada': 'uma-execucao'}):
            with self.subTest(opcoes=opcoes), self.assertRaisesRegex(ErroArtefatos, 'Manifesto obrigatório'):
                modulo.carregar_modelo(self.saida, **opcoes)
        self.assertFalse(validar_resultados(self.saida)['integridade_verificada'])

    def test_ausencia_de_cada_artefato_e_detectada_antes_de_carregar(self):
        self.identificado()
        for nome in ARQUIVOS:
            caminho = self.saida/nome
            original = caminho.read_bytes()
            with self.subTest(nome=nome):
                caminho.unlink()
                try:
                    with self.assertRaisesRegex(ErroArtefatos, nome.replace('.', r'\.')):
                        modulo.carregar_modelo(self.saida)
                finally:
                    caminho.write_bytes(original)

    def test_corrupcao_de_cada_artefato_e_detectada_por_hash(self):
        self.identificado()
        for nome in ARQUIVOS:
            caminho = self.saida/nome
            original = caminho.read_bytes()
            with self.subTest(nome=nome):
                caminho.write_bytes(original+b'alterado')
                try:
                    with self.assertRaisesRegex(ErroArtefatos, 'Integridade inválida'):
                        modulo.carregar_modelo(self.saida)
                finally:
                    caminho.write_bytes(original)

    def test_manifestos_malformados_e_esquemas_incompativeis_sao_recusados(self):
        self.identificado()
        original = self.manifesto()
        for conteudo in ('{', '[]', 'null'):
            with self.subTest(conteudo=conteudo):
                (self.saida/MANIFESTO).write_text(conteudo)
                with self.assertRaises(ErroArtefatos):
                    modulo.carregar_modelo(self.saida)
        for chave, valor in (('esquema', 'outra-fonte'), ('versao_esquema', 99),
                             ('versao_esquema', True), ('execucao_id', 'invalido')):
            with self.subTest(chave=chave, valor=valor):
                m = dict(original); m[chave] = valor
                self.escrever_manifesto(m)
                with self.assertRaises(ErroArtefatos):
                    modulo.carregar_modelo(self.saida)

    def test_inventario_incompleto_extra_ou_hash_invalido_sao_recusados(self):
        self.identificado()
        original = self.manifesto()
        for modo in ('faltante', 'extra', 'hash'):
            with self.subTest(modo=modo):
                m = json.loads(json.dumps(original))
                if modo == 'faltante': del m['arquivos']['teste.csv']
                elif modo == 'extra': m['arquivos']['../externo.csv'] = {}
                else: m['arquivos']['teste.csv']['sha256'] = 'nao-e-hash'
                self.escrever_manifesto(m)
                with self.assertRaises(ErroArtefatos):
                    modulo.carregar_modelo(self.saida)

    def test_expectativas_rejeitam_outro_dataset_versao_fonte_ou_execucao(self):
        self.identificado()
        for chave in ('nome', 'versao', 'fonte'):
            with self.subTest(chave=chave), self.assertRaisesRegex(ErroArtefatos, 'dataset incompatível'):
                modulo.carregar_modelo(self.saida, dataset_esperado={chave: 'diferente'})
        with self.assertRaisesRegex(ErroArtefatos, 'execução incompatível'):
            modulo.carregar_modelo(self.saida, execucao_esperada='outra-execucao')

    def test_mistura_de_arquivos_de_execucoes_distintas_e_detectada(self):
        self.identificado()
        ratings = pd.read_csv(self.dados/'ratings.csv')
        ratings['rating'] = 1.
        ratings.to_csv(self.dados/'ratings.csv', index=False)
        outra = self.raiz/'execucao-b'
        self.gerar(outra, identificar=True, dataset=self.dataset)
        (self.saida/'treino.csv').write_bytes((outra/'treino.csv').read_bytes())
        with self.assertRaisesRegex(ErroArtefatos, 'Integridade inválida: treino.csv'):
            modulo.carregar_modelo(self.saida)

    def test_parametros_divergentes_do_relatorio_sao_recusados(self):
        self.identificado()
        m = self.manifesto(); m['parametros']['min_avaliacoes_filme_treino'] = 20
        self.escrever_manifesto(m)
        with self.assertRaisesRegex(ErroArtefatos, 'Parâmetro diverge'):
            modulo.carregar_modelo(self.saida)

    def test_metadados_obrigatorios_ausentes_ou_invalidos_sao_recusados(self):
        self.identificado()
        original = self.manifesto()
        for chave in ('dataset', 'parametros', 'entradas', 'criado_em', 'execucao_id'):
            with self.subTest(ausente=chave):
                m = dict(original); del m[chave]
                self.escrever_manifesto(m)
                with self.assertRaises(ErroArtefatos):
                    modulo.carregar_modelo(self.saida)
        for chave, valor in (('criado_em', 'ontem'), ('entradas', []),
                             ('dataset', {'nome': 'sem fonte'})):
            with self.subTest(chave=chave, valor=valor):
                m = dict(original); m[chave] = valor
                self.escrever_manifesto(m)
                with self.assertRaises(ErroArtefatos):
                    modulo.carregar_modelo(self.saida)

    def test_dimensao_da_matriz_incompativel_e_recusada(self):
        self.identificado()
        caminho = self.saida/'matriz_treino.npz'
        matriz = load_npz(caminho)
        save_npz(caminho, matriz[:-1, :]); self.reassinar('matriz_treino.npz')
        with self.assertRaisesRegex(ErroArtefatos, 'Dimensão'):
            modulo.carregar_modelo(self.saida)

    def test_matriz_corrompida_e_recusada_mesmo_com_hash_recalculado(self):
        self.identificado()
        (self.saida/'matriz_treino.npz').write_bytes(b'zip corrompido')
        self.reassinar('matriz_treino.npz')
        with self.assertRaises(ErroArtefatos):
            modulo.carregar_modelo(self.saida)

    def test_indices_incompativeis_sao_recusados_mesmo_com_hash_recalculado(self):
        self.identificado()
        caminho = self.saida/'indices_matriz.json'
        indices = json.loads(caminho.read_text()); indices['movieIds'].reverse()
        caminho.write_text(json.dumps(indices))
        self.reassinar('indices_matriz.json')
        with self.assertRaisesRegex(ErroArtefatos, 'Índices da matriz'):
            modulo.carregar_modelo(self.saida)

    def test_valores_da_matriz_sao_conferidos_contra_treino(self):
        self.identificado()
        caminho = self.saida/'matriz_treino.npz'
        matriz = load_npz(caminho); matriz.data[0] += .5
        save_npz(caminho, matriz); self.reassinar('matriz_treino.npz')
        with self.assertRaisesRegex(ErroArtefatos, 'Valores da matriz'):
            modulo.carregar_modelo(self.saida)

    def test_csv_com_esquema_invalido_e_recusado_mesmo_reassinado(self):
        self.identificado()
        (self.saida/'ranking_treino.csv').write_text('coluna_errada\n1\n')
        self.reassinar('ranking_treino.csv')
        with self.assertRaisesRegex(ErroArtefatos, 'Colunas incompatíveis'):
            modulo.carregar_modelo(self.saida)

    def test_execucao_interrompida_nao_cai_no_modo_legado(self):
        with patch.object(modulo, 'carregar', side_effect=RuntimeError('falha simulada')):
            with self.assertRaisesRegex(RuntimeError, 'falha simulada'):
                self.identificado()
        self.assertTrue((self.saida/PENDENTE).exists())
        with self.assertRaisesRegex(ErroArtefatos, 'incompleta'):
            modulo.carregar_modelo(self.saida)
        with self.assertRaises(ErroArtefatos):
            self.gerar()

    def test_identificacao_nunca_sobrescreve_diretorio_ocupado(self):
        self.gerar()
        antes = {p.name: p.read_bytes() for p in self.saida.iterdir()}
        with self.assertRaises(FileExistsError): self.identificado()
        self.assertEqual(antes, {p.name: p.read_bytes() for p in self.saida.iterdir()})

    def test_modo_legado_nao_sobrescreve_execucao_identificada(self):
        self.identificado()
        antes = {p.name: p.read_bytes() for p in self.saida.iterdir()}
        with self.assertRaises(ErroArtefatos): self.gerar()
        self.assertEqual(antes, {p.name: p.read_bytes() for p in self.saida.iterdir()})

    def test_sem_relevantes_preserva_metricas_vazias_validas(self):
        ratings = pd.read_csv(self.dados/'ratings.csv'); ratings['rating'] = 1.
        ratings.to_csv(self.dados/'ratings.csv', index=False)
        self.identificado()
        self.assertEqual((self.saida/'metricas_por_usuario.csv').read_text(), '\n')
        self.assertTrue(validar_resultados(self.saida)['integridade_verificada'])

    def test_metadados_invalidos_ou_sem_ativacao_nao_escrevem_resultados(self):
        for dataset in ({'nome': 'incompleto'},
                        {'nome': '', 'versao': None, 'fonte': 'teste'}):
            with self.subTest(dataset=dataset), self.assertRaises(ValueError):
                self.gerar(identificar=True, dataset=dataset)
        with self.assertRaises(ValueError): self.gerar(dataset=self.dataset)
        self.assertFalse(self.saida.exists())


if __name__ == '__main__':
    unittest.main()
