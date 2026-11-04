"""Diretórios e integridade dos resultados; sem regras de recomendação."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4, UUID
from zipfile import BadZipFile

import pandas as pd
from scipy.sparse import load_npz

ARQUIVOS = (
    'treino.csv', 'teste.csv', 'filmes.csv', 'ranking_treino.csv',
    'matriz_treino.npz', 'indices_matriz.json', 'metricas_por_usuario.csv',
    'relatorio.json',
)
MANIFESTO = 'manifesto.json'
PENDENTE = '.preparacao-em-andamento'
ESQUEMA = 'cinematch.movielens.resultados'
VERSAO_ESQUEMA = 1


class ErroArtefatos(RuntimeError):
    """Resultados identificados ausentes, incompatíveis ou sem integridade."""


def identidade_dataset(dataset, fonte):
    identidade = ({'nome': 'MovieLens Latest Small', 'versao': None, 'fonte': fonte}
                  if dataset is None else dict(dataset))
    if set(identidade) != {'nome', 'versao', 'fonte'}:
        raise ValueError('Dataset deve informar nome, versao e fonte.')
    if any(not isinstance(identidade[k], str) or not identidade[k].strip()
           for k in ('nome', 'fonte')):
        raise ValueError('Nome e fonte do dataset devem ser textos não vazios.')
    versao = identidade['versao']
    if versao is not None and (not isinstance(versao, str) or not versao.strip()):
        raise ValueError('Versão deve ser texto não vazio ou None quando desconhecida.')
    return identidade


def assinatura(caminho):
    digest = hashlib.sha256()
    with Path(caminho).open('rb') as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b''):
            digest.update(bloco)
    return {'sha256': digest.hexdigest(), 'bytes': Path(caminho).stat().st_size}


def _validar_assinatura(registro, nome):
    if (not re.fullmatch(r'[0-9a-f]{64}', registro['sha256'])
            or type(registro['bytes']) is not int or registro['bytes'] < 0):
        raise ValueError('Assinatura inválida: ' + nome)


def iniciar_identificacao(pasta):
    """Reserva pasta vazia. Nunca substitui resultados de outra execução."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    if any(pasta.iterdir()):
        raise FileExistsError('Resultados identificados exigem diretório vazio: ' + str(pasta))
    execucao = str(uuid4())
    # Criação exclusiva: outra preparação concorrente não pode reservar a pasta.
    with (pasta / PENDENTE).open('x', encoding='utf-8') as arquivo:
        arquivo.write(execucao)
    return execucao


def gravar_manifesto(pasta, execucao, dataset, parametros, entradas):
    pasta = Path(pasta)
    manifesto = {
        'esquema': ESQUEMA, 'versao_esquema': VERSAO_ESQUEMA,
        'execucao_id': execucao,
        'criado_em': datetime.now(timezone.utc).isoformat(),
        'dataset': dataset, 'parametros': parametros,
        'entradas': {nome: assinatura(caminho) for nome, caminho in entradas.items()
                     if Path(caminho).is_file()},
        'arquivos': {nome: assinatura(pasta / nome) for nome in ARQUIVOS},
    }
    # Publicado por último; o marcador permanece se qualquer etapa falhar.
    with (pasta / MANIFESTO).open('x', encoding='utf-8') as arquivo:
        json.dump(manifesto, arquivo, ensure_ascii=False, indent=2, allow_nan=False)
    (pasta / PENDENTE).unlink()
    return manifesto


def _ler_json(caminho):
    with caminho.open(encoding='utf-8') as arquivo:
        return json.load(arquivo)


def _validar_estrutura(pasta, manifesto):
    """Coerência de esquema, parâmetros e posições da matriz, sem recalcular rankings."""
    relatorio = _ler_json(pasta / 'relatorio.json')
    indices = _ler_json(pasta / 'indices_matriz.json')
    parametros = manifesto['parametros']
    obrigatorios = {'seed', 'fracao_teste', 'min_avaliacoes_filme_treino',
                    'min_avaliacoes_usuario_treino', 'k', 'relevante'}
    if set(parametros) != obrigatorios or parametros['k'] != 10 or parametros['relevante'] != 4.:
        raise ValueError('Parâmetros incompatíveis com o esquema 1.')
    for chave in obrigatorios - {'k', 'relevante'}:
        if relatorio[chave] != parametros[chave]:
            raise ValueError('Parâmetro diverge do relatório: ' + chave)
    colunas = {
        'treino.csv': {'userId', 'movieId', 'rating', 'timestamp'},
        'teste.csv': {'userId', 'movieId', 'rating', 'timestamp'},
        'filmes.csv': {'movieId', 'title', 'genres', 'ano'},
        'ranking_treino.csv': {'movieId', 'contagem', 'media', 'nota_ponderada'},
    }
    tabelas = {}
    for nome, campos in colunas.items():
        tabela = pd.read_csv(pasta / nome)
        if not campos.issubset(tabela.columns):
            raise ValueError('Colunas incompatíveis: ' + nome)
        tabelas[nome] = tabela
    treino, teste = tabelas['treino.csv'], tabelas['teste.csv']
    if len(treino) != relatorio['linhas_treino'] or len(teste) != relatorio['linhas_teste']:
        raise ValueError('Contagens de treino/teste divergem do relatório.')
    if (treino.duplicated(['userId', 'movieId']).any()
            or set(zip(treino.userId, treino.movieId)) & set(zip(teste.userId, teste.movieId))):
        raise ValueError('Pares duplicados no treino ou compartilhados com o teste.')
    users, filmes = indices['userIds'], indices['movieIds']
    if users != sorted(treino.userId.unique()) or filmes != sorted(treino.movieId.unique()):
        raise ValueError('Índices da matriz divergem dos IDs de treino.')
    matriz = load_npz(pasta / 'matriz_treino.npz')
    if (list(matriz.shape) != relatorio['matriz_shape']
            or matriz.shape != (len(users), len(filmes)) or matriz.nnz != len(treino)):
        raise ValueError('Dimensão ou quantidade de entradas da matriz incompatível.')
    um, im = {v: i for i, v in enumerate(users)}, {v: i for i, v in enumerate(filmes)}
    valores = matriz[treino.userId.map(um).to_numpy(), treino.movieId.map(im).to_numpy()]
    if not (valores.A1 == treino.rating.to_numpy()).all():
        raise ValueError('Valores da matriz divergem das notas do treino.')
    catalogo = set(tabelas['filmes.csv'].movieId)
    ranking = tabelas['ranking_treino.csv']
    if (not set(treino.movieId).issubset(catalogo)
            or not set(teste.movieId).issubset(catalogo)
            or not set(ranking.movieId).issubset(set(treino.movieId))
            or ranking.movieId.duplicated().any()
            or len(ranking) != relatorio['itens_elegiveis']):
        raise ValueError('Catálogo, ranking e avaliações incompatíveis.')
    # Sem relevantes, avaliar() produz DataFrame sem colunas e CSV vazio.
    try:
        metricas = pd.read_csv(pasta / 'metricas_por_usuario.csv')
    except pd.errors.EmptyDataError:
        if 'metricas' in relatorio:
            raise ValueError('Métricas individuais ausentes apesar do relatório agregado.')
    else:
        if not {'metodo', 'userId', 'precision_at_10', 'recall_at_10', 'ndcg_at_10'}.issubset(metricas.columns):
            raise ValueError('Colunas de métricas incompatíveis.')


def validar_resultados(pasta, *, exigir_manifesto=False, dataset_esperado=None,
                       execucao_esperada=None):
    """Sem manifesto: identifica legado sem prometer verificação de integridade.

    Com manifesto: valida todos os oito arquivos, inclusive os não usados pela web.
    Expectativas opcionais impedem aceitar uma execução íntegra de outra origem.
    """
    pasta = Path(pasta)
    if (pasta / PENDENTE).exists():
        raise ErroArtefatos('Preparação identificada incompleta: ' + str(pasta))
    if not (pasta / MANIFESTO).exists():
        if exigir_manifesto or dataset_esperado is not None or execucao_esperada is not None:
            raise ErroArtefatos('Manifesto obrigatório ausente: ' + str(pasta))
        return {'estado': 'legado_sem_manifesto', 'integridade_verificada': False}
    try:
        manifesto = _ler_json(pasta / MANIFESTO)
        if (manifesto['esquema'] != ESQUEMA
                or type(manifesto['versao_esquema']) is not int
                or manifesto['versao_esquema'] != VERSAO_ESQUEMA):
            raise ValueError('Esquema de artefatos não suportado.')
        UUID(manifesto['execucao_id'])
        criado = datetime.fromisoformat(manifesto['criado_em'])
        if criado.tzinfo is None:
            raise ValueError('Data da execução deve informar fuso horário.')
        identidade_dataset(manifesto['dataset'], '')
        if not isinstance(manifesto['entradas'], dict) or not set(manifesto['entradas']).issubset(
                {'ratings.csv', 'movies.csv'}):
            raise ValueError('Identificação dos arquivos de origem inválida.')
        for nome, registro in manifesto['entradas'].items():
            _validar_assinatura(registro, nome)
        if dataset_esperado is not None:
            for chave, valor in dataset_esperado.items():
                if chave not in ('nome', 'versao', 'fonte') or manifesto['dataset'][chave] != valor:
                    raise ValueError('Identidade do dataset incompatível: ' + chave)
        if execucao_esperada is not None and manifesto['execucao_id'] != execucao_esperada:
            raise ValueError('Identificação da execução incompatível.')
        if set(manifesto['arquivos']) != set(ARQUIVOS):
            raise ValueError('Inventário de artefatos incompatível.')
        for nome in ARQUIVOS:
            esperado = manifesto['arquivos'][nome]
            _validar_assinatura(esperado, nome)
            caminho = pasta / nome
            if caminho.is_symlink() or not caminho.is_file():
                raise ValueError('Artefato ausente ou não regular: ' + nome)
            if assinatura(caminho) != esperado:
                raise ValueError('Integridade inválida: ' + nome)
        _validar_estrutura(pasta, manifesto)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, EOFError,
            BadZipFile, IndexError) as erro:
        raise ErroArtefatos('Resultados identificados inválidos: ' + str(erro)) from erro
    return {'estado': 'identificado', 'integridade_verificada': True,
            'manifesto': manifesto}
