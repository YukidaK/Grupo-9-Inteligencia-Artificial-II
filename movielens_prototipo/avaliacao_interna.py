"""Avaliação dos três métodos existentes na divisão interna aprovada.

Nenhuma leitura de notas reservadas ocorre antes de gerar e salvar as listas.
Hashes de validação são conferidos como bytes na fase administrativa inicial.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform

import pandas as pd

from artefatos_resultados import assinatura, iniciar_identificacao, MANIFESTO, PENDENTE
from divisao_interna import carregar_desenvolvimento, carregar_validacao, validar_execucao
from avaliacao_perfil import gerar_listas, pontuar_listas, METODOS, METRICAS

ROOT = Path(__file__).resolve().parent
ESQUEMA = 'cinematch.experimento.avaliacao_interna'
ARQUIVOS = ('listas.csv','estatisticas_desenvolvimento.csv','avaliacao_por_usuario.csv',
            'resumo.csv','resumo.json','usuarios.csv','auditoria.json')
CODIGO = ('avaliacao_interna.py','avaliacao_perfil.py','divisao_interna.py',
          'recomendador.py','conversa.py','identidades.py','artefatos_resultados.py')


def _json(pasta, nome, valor):
    with (pasta/nome).open('x',encoding='utf-8') as f:
        json.dump(valor,f,ensure_ascii=False,indent=2,allow_nan=False)


def gerar_coorte(contexto, filmes, *, progresso=None):
    """Somente desenvolvimento entra na geração; estatísticas usam todos os aptos.

    Filtrar o treino para os 594 antes de calcular ranking alteraria suas médias.
    Por isso a restrição da coorte é aplicada às listas, após gerar_listas().
    """
    listas, stats, auditoria = gerar_listas(contexto.avaliacoes(),filmes,
        min_filme=5,min_usuario=5,seed=201,progresso=progresso)
    listas = listas[listas.coorte_fixa_5].reset_index(drop=True)
    if listas.empty:
        raise ValueError('Nenhum usuário possui cinco positivos no desenvolvimento.')
    grupos = listas.groupby(['userId','n_referencias'])
    if (not listas.elegivel.all() or not grupos.metodo.agg(set).map(lambda s:s==set(METODOS)).all()
            or not grupos.hash_candidatos.nunique().eq(1).all()
            or not grupos.n_candidatos.nunique().eq(1).all()
            or not listas.groupby('n_referencias').userId.agg(set).map(
                lambda s:s==set(listas.userId)).all()):
        raise ValueError('População ou candidatos divergentes entre configurações.')
    return listas, stats, auditoria


def pontuar_coorte(listas, validacao):
    """Reutiliza métricas originais; renomeia apenas rótulos de teste para validação."""
    detalhes, resumo = pontuar_listas(listas,validacao)
    detalhes = detalhes.rename(columns={'relevantes_teste':'relevantes_validacao'})
    resumo = resumo[resumo.coorte=='fixa_5'].rename(
        columns={'usuarios_sem_positivos_teste':'usuarios_sem_positivos_validacao'}).reset_index(drop=True)
    candidatos = listas[listas.metodo=='perfil'].groupby('n_referencias').n_candidatos.agg(
        candidatos_min='min',candidatos_mediana='median',candidatos_media='mean',candidatos_max='max')
    resumo = resumo.merge(candidatos,on='n_referencias',how='left')
    avaliados = detalhes[detalhes.avaliado_metricas].groupby(['metodo','n_referencias']).userId.agg(set)
    if len(avaliados) and not all(s==avaliados.iloc[0] for s in avaliados):
        raise ValueError('Coorte avaliável varia entre métodos ou tamanhos de perfil.')
    usuarios = detalhes[['userId','relevantes_validacao','avaliado_metricas']].drop_duplicates().sort_values('userId')
    return detalhes, resumo, usuarios


def _entradas(divisao, treino, procedencia, filmes):
    # O loader de desenvolvimento valida o esquema antes de chamar esta função.
    m = json.loads((divisao/MANIFESTO).read_text())
    p = json.loads(procedencia.read_text())
    if (p['esquema']!='cinematch.experimento.perfil' or p['versao_esquema']!=1
            or p['parametros']['seed_divisao_preservada']!=42
            or p['parametros']['fracao_teste']!=.2
            or p['dataset']!=m['fonte']['dataset']
            or treino.name!='treino.csv'
            or assinatura(procedencia)!=m['fonte']['manifesto_procedencia']
            or assinatura(treino)!=m['fonte']['treino']
            or assinatura(treino)!=p['entradas']['resultados/treino.csv']
            or assinatura(filmes)!=p['entradas']['resultados/filmes.csv']):
        raise ValueError('Procedência do treino ou catálogo incompatível.')
    if m['parametros_divisao']['seed']!=101 or m['parametros_divisao']['fracao_validacao']!=.2:
        raise ValueError('Esperada divisão interna aprovada com semente 101 e fração 0,20.')
    caminhos = {**{f'divisao/{n}':divisao/n for n in m['arquivos']},
        'divisao/manifesto.json':divisao/MANIFESTO,
        'treino_origem':treino,'manifesto_procedencia':procedencia,'catalogo':filmes}
    assinaturas = {n:assinatura(c) for n,c in caminhos.items()}
    for n,s in m['arquivos'].items():
        if assinaturas['divisao/'+n]!=s:
            raise ValueError('Artefato interno sem integridade: '+n)
    return m,caminhos,assinaturas


def executar(divisao, treino, procedencia, filmes, saida, *, progresso=None):
    divisao,treino,procedencia,filmes,saida = map(Path,(divisao,treino,procedencia,filmes,saida))
    for entrada in (divisao.resolve(),treino.resolve().parent,procedencia.resolve().parent,filmes.resolve().parent):
        if saida.resolve()==entrada or entrada in saida.resolve().parents:
            raise ValueError('Saída deve ficar fora dos diretórios de entrada.')
    contexto = carregar_desenvolvimento(divisao)
    m,caminhos,antes = _entradas(divisao,treino,procedencia,filmes)
    codigo = {n:assinatura(ROOT/n) for n in CODIGO}
    execucao = iniciar_identificacao(saida)
    catalogo = pd.read_csv(filmes)
    dev = contexto.avaliacoes()
    if (catalogo.movieId.duplicated().any() or not set(dev.movieId).issubset(set(catalogo.movieId))):
        raise ValueError('Catálogo inválido ou desenvolvimento com filmes desconhecidos.')
    listas,stats,auditoria = gerar_coorte(contexto,catalogo,progresso=progresso)
    # Publica todas as listas antes de abrir validação como tabela.
    listas.to_csv(saida/'listas.csv',index=False,mode='x')
    stats.to_csv(saida/'estatisticas_desenvolvimento.csv',index=False,mode='x')
    hash_listas = assinatura(saida/'listas.csv')
    if progresso: progresso('Listas salvas; iniciando auditoria semântica e pontuação da validação.')
    isolamento = validar_execucao(divisao)  # Leitura administrativa; não constrói rankings.
    validacao = carregar_validacao(divisao,execucao_esperada=contexto.execucao_id)
    if not set(validacao.movieId).issubset(set(catalogo.movieId)):
        raise ValueError('Validação contém filme fora do catálogo.')
    detalhes,resumo,usuarios = pontuar_coorte(listas,validacao)
    if assinatura(saida/'listas.csv')!=hash_listas:
        raise ValueError('Listas mudaram durante a pontuação.')
    detalhes.to_csv(saida/'avaliacao_por_usuario.csv',index=False,mode='x')
    resumo.to_csv(saida/'resumo.csv',index=False,mode='x')
    usuarios.to_csv(saida/'usuarios.csv',index=False,mode='x')
    _json(saida,'resumo.json',json.loads(resumo.to_json(orient='records',double_precision=15)))
    auditoria.update({'isolamento_divisao':isolamento,
        'usuarios_coorte_fixa':len(usuarios),'usuarios_avaliaveis':int(usuarios.avaliado_metricas.sum()),
        'usuarios_sem_positivos_validacao':usuarios.loc[~usuarios.avaliado_metricas,'userId'].tolist(),
        'listas_geradas_antes_de_ler_notas_validacao':True,
        'hash_listas_antes_validacao':hash_listas,
        'estatisticas_somente_desenvolvimento':True,
        'baselines_condicionados_ao_perfil':True})
    _json(saida,'auditoria.json',auditoria)
    if antes!={n:assinatura(c) for n,c in caminhos.items()} or codigo!={n:assinatura(ROOT/n) for n in CODIGO}:
        raise ValueError('Entradas ou código mudaram durante a avaliação.')
    _json(saida,MANIFESTO,{'esquema':ESQUEMA,'versao_esquema':1,'execucao_id':execucao,
        'criado_em':datetime.now(timezone.utc).isoformat(),'dataset':m['fonte']['dataset'],
        'divisao_execucao_id':contexto.execucao_id,'entradas':antes,'codigo':codigo,
        'parametros':{'seed_divisao':101,'fracao_validacao':.2,'seed_referencias':201,
            'referencias':[1,2,3,4,5],'min_usuario':5,'min_filme':5,'k':10,'relevante':4.,
            'coorte':'fixa: pelo menos cinco positivos de desenvolvimento',
            'historico_excluido':'todo o desenvolvimento individual',
            'candidatos':'suporte >=5 em desenvolvimento; não vistos; interseção de gêneros com referências >0',
            'preferencias_explicitas':'vazias','metodos':list(METODOS)},
        'ambiente':{'python':platform.python_version(),**{n:importlib.metadata.version(n) for n in ('numpy','pandas','scipy')}},
        'arquivos':{n:assinatura(saida/n) for n in ARQUIVOS}})
    (saida/PENDENTE).unlink()
    validar_saida(saida)
    return detalhes,resumo,auditoria


def validar_saida(saida):
    """Integridade do conjunto experimental; não é loader de produção."""
    saida = Path(saida)
    m = json.loads((saida/MANIFESTO).read_text())
    if ((saida/PENDENTE).exists() or m['esquema']!=ESQUEMA or m['versao_esquema']!=1
            or set(m['arquivos'])!=set(ARQUIVOS)):
        raise ValueError('Manifesto de avaliação interna incompatível ou execução incompleta.')
    for n,s in m['arquivos'].items():
        if assinatura(saida/n)!=s:
            raise ValueError('Artefato experimental corrompido: '+n)
    return m


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--divisao',type=Path,required=True)
    p.add_argument('--treino',type=Path,required=True)
    p.add_argument('--procedencia',type=Path,required=True)
    p.add_argument('--filmes',type=Path,required=True)
    p.add_argument('--saida',type=Path,required=True)
    a = p.parse_args()
    _,resumo,_ = executar(a.divisao,a.treino,a.procedencia,a.filmes,a.saida,progresso=lambda s:print(s,flush=True))
    print(resumo.to_string(index=False))
