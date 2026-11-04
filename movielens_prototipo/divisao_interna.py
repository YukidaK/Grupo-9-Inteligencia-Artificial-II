"""Particionamento experimental: somente treino original, sem avaliar modelos.

Não usa carregar_modelo(), rankings persistidos, ratings.csv ou teste.csv.
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from artefatos_resultados import assinatura, iniciar_identificacao, MANIFESTO, PENDENTE
from recomendador import dividir, ranking
from avaliacao_perfil import selecionar_referencias

ESQUEMA = 'cinematch.experimento.divisao_interna'
VERSAO = 1
COLUNAS = ['userId', 'movieId', 'rating', 'timestamp']
ARQUIVOS = ('desenvolvimento.csv', 'validacao.csv', 'auditoria.json')
ALGORITMO = 'recomendador.dividir: default_rng/choice sem reposição por usuário; IDs ordenados'
REGRA = '0 se n=1; senão min(n-1, max(1, floor(n*fracao)))'
_CAPACIDADE = object()


class ErroDivisao(ValueError):
    """Entrada, procedência ou partição experimental incompatível."""


def _tabela(tabela):
    if list(tabela.columns) != COLUNAS or tabela.empty:
        raise ErroDivisao('Esperada tabela não vazia com as quatro colunas MovieLens, na ordem original.')
    t = tabela.copy()
    try:
        t = t.apply(pd.to_numeric, errors='raise')
        if not np.isfinite(t.to_numpy()).all():
            raise ValueError('não finitos')
        for c in ('userId', 'movieId', 'timestamp'):
            if not t[c].mod(1).eq(0).all() or not t[c].ge(0 if c == 'timestamp' else 1).all():
                raise ValueError('identificadores ou timestamp inválidos')
            t[c] = t[c].astype('int64')
        if not t.rating.between(.5, 5).all() or not t.rating.mul(2).mod(1).eq(0).all():
            raise ValueError('notas inválidas')
        if t.duplicated(['userId', 'movieId']).any():
            raise ValueError('pares repetidos')
    except (ValueError, TypeError, OverflowError) as erro:
        raise ErroDivisao('Avaliações inválidas: ' + str(erro)) from erro
    t['rating'] = t.rating.astype(float)
    return t.sort_values(['userId', 'movieId']).reset_index(drop=True)


def identidade_registros(tabela):
    """Hash canônico inclui TODOS os valores, não apenas pares/contagens."""
    t = _tabela(tabela)
    texto = t.to_json(orient='values', double_precision=15)
    return hashlib.sha256(texto.encode()).hexdigest()


def dividir_interno(treino, *, seed=101, fracao=.2):
    if type(seed) is not int or seed < 0 or type(fracao) not in (int, float) or not 0 < fracao < 1:
        raise ErroDivisao('Semente inteira não negativa e fração entre zero e um são obrigatórias.')
    origem = _tabela(treino)
    dev, val = dividir(origem, fracao=fracao, seed=seed)
    return dev.reset_index(drop=True), val.reset_index(drop=True)


def _contagens(t):
    return {'avaliacoes':len(t), 'usuarios':int(t.userId.nunique()), 'filmes':int(t.movieId.nunique())}


def _auditar(origem, dev, val):
    pares = lambda t: set(zip(t.userId, t.movieId))
    if pares(dev) & pares(val):
        raise ErroDivisao('Partições compartilham pares usuário–filme.')
    if identidade_registros(pd.concat([dev, val], ignore_index=True)) != identidade_registros(origem):
        raise ErroDivisao('União das partições não conserva os registros da origem.')
    positivos = dev[dev.rating >= 4].groupby('userId').size()
    hist = origem.groupby('userId').size()
    return {'origem':_contagens(origem), 'desenvolvimento':_contagens(dev), 'validacao':_contagens(val),
        'intersecao_pares':0, 'conservacao_integral':True,
        'usuarios_historico_unitario_so_desenvolvimento':int(hist.eq(1).sum()),
        'usuarios_sem_validacao':len(set(origem.userId)-set(val.userId)),
        'usuarios_sem_positivos_desenvolvimento':int(dev.userId.nunique()-len(positivos)),
        'usuarios_referencias_suficientes':{str(n):int(positivos.ge(n).sum()) for n in range(1,6)},
        'usuarios_minimo_cinco_desenvolvimento':int(dev.groupby('userId').size().ge(5).sum())}


def _json(p, objeto):
    with p.open('x', encoding='utf-8') as f:
        json.dump(objeto, f, ensure_ascii=False, indent=2, allow_nan=False)


def verificar_origem(treino, procedencia):
    """Âncora explícita: manifesto experimental aprovado, sem abrir o teste.

    A confiança no manifesto fornecido é externa, não uma assinatura digital.
    """
    treino, procedencia = Path(treino), Path(procedencia)
    if treino.name != 'treino.csv':
        raise ErroDivisao('Somente o arquivo treino.csv de origem é permitido.')
    try:
        m = json.loads(procedencia.read_text())
        if (m['esquema'] != 'cinematch.experimento.perfil' or m['versao_esquema'] != 1
                or m['parametros']['seed_divisao_preservada'] != 42
                or m['parametros']['fracao_teste'] != .2
                or m['dataset']['nome'] != 'MovieLens Latest Small'
                or m['dataset']['versao'] != '2018-09-26'):
            raise ErroDivisao('Procedência incompatível com o treino original aprovado.')
        if assinatura(treino) != m['entradas']['resultados/treino.csv']:
            raise ErroDivisao('Integridade do treino diverge da procedência aprovada.')
        t = _tabela(pd.read_csv(treino))
        return t, {'treino':assinatura(treino),'manifesto_procedencia':assinatura(procedencia),
            'execucao_procedencia':m['execucao_id'], 'dataset':m['dataset'],
            'seed_divisao_original':42,'identidade_registros':identidade_registros(t)}
    except (KeyError, TypeError, OSError, json.JSONDecodeError) as erro:
        raise ErroDivisao('Não foi possível verificar a procedência: ' + str(erro)) from erro


def executar(treino, procedencia, saida, *, seed=101, fracao=.2):
    origem, fonte = verificar_origem(treino, procedencia)
    saida = Path(saida)
    # Não permitir a reserva de uma saída dentro de qualquer entrada.
    for entrada in (Path(treino).resolve().parent, Path(procedencia).resolve().parent):
        if saida.resolve() == entrada or entrada in saida.resolve().parents:
            raise ErroDivisao('Saída deve ficar fora dos diretórios de entrada.')
    dev, val = dividir_interno(origem, seed=seed, fracao=fracao)
    auditoria = _auditar(origem, dev, val)
    execucao = iniciar_identificacao(saida)
    dev.to_csv(saida/'desenvolvimento.csv', index=False, mode='x')
    val.to_csv(saida/'validacao.csv', index=False, mode='x')
    _json(saida/'auditoria.json', auditoria)
    if assinatura(treino) != fonte['treino'] or assinatura(procedencia) != fonte['manifesto_procedencia']:
        raise ErroDivisao('Fonte mudou durante a execução.')
    manifesto = {'esquema':ESQUEMA, 'versao_esquema':VERSAO, 'execucao_id':execucao,
        'criado_em':datetime.now(timezone.utc).isoformat(), 'fonte':fonte,
        'parametros_divisao':{'seed':seed,'fracao_validacao':fracao,
            'algoritmo':ALGORITMO,'n_validacao':REGRA},
        'protocolo_futuro':{'relevante':4.,'referencias':[1,2,3,4,5],
            'seed_referencias_proposta':201,'min_usuario_proposto':5,'min_filme_proposto':5,
            'sem_positivos_suficientes':'não elegível para aquele tamanho, sem fallback',
            'historico_excluido':'todas as avaliações do desenvolvimento individual',
            'validacao':'somente métricas posteriores à geração; não executadas nesta etapa'},
        'contagens':auditoria,'arquivos':{n:assinatura(saida/n) for n in ARQUIVOS},
        'codigo':{n:assinatura(Path(__file__).parent/n) for n in ('divisao_interna.py','recomendador.py','avaliacao_perfil.py')},
        'ambiente':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__}}
    _json(saida/MANIFESTO, manifesto)
    (saida/PENDENTE).unlink()
    validar_execucao(saida)
    return manifesto


def _manifesto(pasta, execucao_esperada=None):
    pasta = Path(pasta)
    try:
        m = json.loads((pasta/MANIFESTO).read_text())
        if ((pasta/PENDENTE).exists() or m['esquema'] != ESQUEMA or m['versao_esquema'] != VERSAO
                or set(m['arquivos']) != set(ARQUIVOS)
                or not isinstance(m['execucao_id'],str)
                or (execucao_esperada is not None and m['execucao_id'] != execucao_esperada)):
            raise ErroDivisao('Esquema, execução ou conjunto de artefatos incompatível.')
        # Valida parâmetros sem abrir CSV algum.
        p = m['parametros_divisao']
        if (type(p['seed']) is not int or p['seed'] < 0
                or type(p['fracao_validacao']) not in (int,float)
                or not 0 < p['fracao_validacao'] < 1
                or p['algoritmo'] != ALGORITMO or p['n_validacao'] != REGRA):
            raise ErroDivisao('Parâmetros de divisão inválidos.')
        if (m['fonte']['dataset']['nome'] != 'MovieLens Latest Small'
                or m['fonte']['dataset']['versao'] != '2018-09-26'
                or m['fonte']['seed_divisao_original'] != 42
                or not {'origem','desenvolvimento','validacao'}.issubset(m['contagens'])):
            raise ErroDivisao('Identidade ou contagens ausentes.')
        for papel in ('origem','desenvolvimento','validacao'):
            c = m['contagens'][papel]
            if set(c) != {'avaliacoes','usuarios','filmes'} or any(type(v) is not int or v<0 for v in c.values()):
                raise ErroDivisao('Contagens incompatíveis: ' + papel)
        return m
    except (KeyError, TypeError, OSError, json.JSONDecodeError) as erro:
        raise ErroDivisao('Manifesto ausente ou inválido: ' + str(erro)) from erro


def _ler_particao(pasta, m, nome):
    try:
        if assinatura(Path(pasta)/nome) != m['arquivos'][nome]:
            raise ErroDivisao('Integridade inválida: ' + nome)
        t = pd.read_csv(Path(pasta)/nome)
        # Uma origem sintética só com históricos unitários produz validação vazia legítima.
        if t.empty and nome == 'validacao.csv' and list(t.columns) == COLUNAS:
            return t
        return _tabela(t)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as erro:
        raise ErroDivisao('Partição ausente ou ilegível: ' + nome) from erro


class DesenvolvimentoInterno:
    """Capacidade de preparação sem caminho ou referência para a validação.

    Interface contra erros acidentais, não sandbox contra código Python hostil.
    """
    def __init__(self, tabela, execucao_id, capacidade):
        if capacidade is not _CAPACIDADE:
            raise ErroDivisao('Use carregar_desenvolvimento; tabelas avulsas não são aceitas.')
        self.__tabela = tabela.copy()
        self.execucao_id = execucao_id

    def avaliacoes(self):
        return self.__tabela.copy()


def carregar_desenvolvimento(pasta, *, execucao_esperada=None):
    """Abre somente manifesto e desenvolvimento; não lê notas de validação."""
    m = _manifesto(pasta, execucao_esperada)
    dev = _ler_particao(pasta, m, 'desenvolvimento.csv')
    if _contagens(dev) != m['contagens']['desenvolvimento']:
        raise ErroDivisao('Contagens de desenvolvimento incompatíveis.')
    return DesenvolvimentoInterno(dev, m['execucao_id'], _CAPACIDADE)


@dataclass
class PreparacaoDesenvolvimento:
    execucao_id: str
    estatisticas: pd.DataFrame
    referencias: dict
    historicos: dict
    parametros: dict


def preparar_desenvolvimento(contexto, *, seed_referencias=201, min_usuario=5, min_filme=5):
    """Preparação existente, só em memória; não cria modelo nem recomendações."""
    if type(contexto) is not DesenvolvimentoInterno:
        raise ErroDivisao('Preparação exige capacidade de desenvolvimento, não DataFrame ou diretório.')
    if any(type(x) is not int for x in (seed_referencias,min_usuario,min_filme)) or seed_referencias < 0 or min_usuario < 1 or min_filme < 1:
        raise ErroDivisao('Parâmetros de preparação inválidos.')
    dev = contexto.avaliacoes()
    cont = dev.groupby('userId').size()
    dev = dev[dev.userId.isin(cont[cont>=min_usuario].index)]
    if dev.empty:
        raise ErroDivisao('Nenhum usuário atende ao mínimo no desenvolvimento.')
    return PreparacaoDesenvolvimento(contexto.execucao_id, ranking(dev,min_filme),
        selecionar_referencias(dev,seed_referencias),
        {int(u):frozenset(g.movieId) for u,g in dev.groupby('userId')},
        {'seed_referencias':seed_referencias,'min_usuario':min_usuario,'min_filme':min_filme,'relevante':4.})


def carregar_validacao(pasta, *, execucao_esperada):
    """Entrada explícita para futuro cálculo de métricas, nunca para preparação."""
    if not execucao_esperada:
        raise ErroDivisao('Informe a execução das listas para impedir mistura de execuções.')
    m = _manifesto(pasta, execucao_esperada)
    val = _ler_particao(pasta, m, 'validacao.csv')
    if _contagens(val) != m['contagens']['validacao']:
        raise ErroDivisao('Contagens de validação incompatíveis.')
    return val


def validar_execucao(pasta):
    """Auditoria das duas partições; não entrega contexto para treinar."""
    m = _manifesto(pasta)
    dev = _ler_particao(pasta,m,'desenvolvimento.csv')
    val = _ler_particao(pasta,m,'validacao.csv')
    uniao = pd.concat([dev,val],ignore_index=True)
    if identidade_registros(uniao) != m['fonte']['identidade_registros']:
        raise ErroDivisao('União diverge da identidade da origem.')
    esperado_dev, esperado_val = dividir_interno(uniao,
        seed=m['parametros_divisao']['seed'], fracao=m['parametros_divisao']['fracao_validacao'])
    for a,b in ((dev,esperado_dev),(val,esperado_val)):
        if a.empty and b.empty:
            continue
        # Ordenação/serialização não mudam pertencimento ou valores.
        if not a.sort_values(['userId','movieId']).reset_index(drop=True).equals(
                b.sort_values(['userId','movieId']).reset_index(drop=True)):
            raise ErroDivisao('Partição não corresponde ao algoritmo/semente declarados.')
    auditoria = _auditar(uniao,dev,val)
    if assinatura(Path(pasta)/'auditoria.json') != m['arquivos']['auditoria.json']:
        raise ErroDivisao('Auditoria sem integridade.')
    if json.loads((Path(pasta)/'auditoria.json').read_text()) != auditoria or auditoria != m['contagens']:
        raise ErroDivisao('Contagens ou auditoria incompatíveis.')
    return auditoria


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--treino', type=Path, required=True)
    p.add_argument('--procedencia', type=Path, required=True)
    p.add_argument('--saida', type=Path, required=True)
    p.add_argument('--seed', type=int, default=101)
    p.add_argument('--fracao', type=float, default=.2)
    a = p.parse_args()
    print(json.dumps(executar(a.treino,a.procedencia,a.saida,seed=a.seed,fracao=a.fracao)['contagens'],indent=2))
