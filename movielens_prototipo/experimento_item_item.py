"""Experimento único item–item; controles congelados da avaliação interna aprovada."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import resource
from time import perf_counter

import pandas as pd
from scipy.sparse import save_npz

from artefatos_resultados import assinatura, iniciar_identificacao, MANIFESTO, PENDENTE
from divisao_interna import carregar_desenvolvimento, carregar_validacao, validar_execucao
from avaliacao_interna import _entradas, pontuar_coorte, validar_saida
from avaliacao_perfil import selecionar_referencias, METRICAS
from item_item_experimental import ItemItem

ROOT = Path(__file__).resolve().parent
METODO = 'item_item'
ARQUIVOS = ('listas.csv','avaliacao_por_usuario.csv','resumo.csv','resumo.json',
    'usuarios.csv','auditoria.json','similaridades.npz','suportes.npz','indices.json','configuracao_previa.json')


def _json(pasta,nome,dados):
    with (pasta/nome).open('x',encoding='utf-8') as f:
        json.dump(dados,f,ensure_ascii=False,indent=2,allow_nan=False)


def gerar_item_item(controles, desenvolvimento, filmes, modelo):
    refs = selecionar_referencias(desenvolvimento,201)
    vistos = {int(u):set(g.movieId) for u,g in desenvolvimento.groupby('userId')}
    generos = {int(f.movieId):set(f.genres.split('|'))-{'(no genres listed)'} for f in filmes.itertuples()}
    linhas = []
    import hashlib
    for f in controles[controles.metodo=='perfil'].itertuples():
        selecionadas = refs[f.userId][:f.n_referencias]
        if len(refs[f.userId])<5 or json.loads(f.referencias)!=selecionadas:
            raise ValueError('Referências congeladas não conferem com desenvolvimento/seed 201.')
        uniao = set().union(*(generos[i] for i in selecionadas))
        candidatos = {i for i in modelo.movie_ids if i not in vistos[f.userId] and generos[i]&uniao}
        fingerprint = hashlib.sha256(json.dumps(sorted(candidatos)).encode()).hexdigest()
        if len(candidatos)!=f.n_candidatos or fingerprint!=f.hash_candidatos:
            raise ValueError('Universo de candidatos difere dos controles aprovados.')
        rec,pontuaveis = modelo.recomendar(selecionadas,candidatos,vistos[f.userId])
        linha = f._asdict()
        linha.pop('Index',None)
        linha.update(metodo=METODO,recomendacoes=json.dumps([i['movieId'] for i in rec]),
            n_recomendacoes=len(rec),n_pontuaveis=pontuaveis,
            scores=json.dumps([i['pontuacao'] for i in rec]))
        linhas.append(linha)
    originais = controles.copy()
    originais['n_pontuaveis'] = originais.n_candidatos
    originais['scores'] = None
    return pd.concat([originais,pd.DataFrame(linhas)],ignore_index=True)


def pontuar_quatro(listas,validacao):
    # O componente atual calcula métricas em TODAS as linhas; seu resumo lista
    # só os três nomes antigos. Estendemos apenas a agregação do novo método.
    detalhes,resumo,usuarios = pontuar_coorte(listas,validacao)
    extras = []
    for n,g in detalhes[detalhes.metodo==METODO].groupby('n_referencias'):
        avaliados = g[g.avaliado_metricas]
        base = resumo[resumo.n_referencias==n].iloc[0].to_dict()
        base.update(metodo=METODO,usuarios_avaliados=len(avaliados),
            usuarios_sem_positivos_validacao=len(g)-len(avaliados),
            media_recomendacoes=float(g.n_recomendacoes.mean()),
            cobertura_usuarios=float(g.n_recomendacoes.gt(0).mean()),
            **{c:float(avaliados[c].mean()) if len(avaliados) else None for c in METRICAS})
        extras.append(base)
    resumo = pd.concat([resumo,pd.DataFrame(extras)],ignore_index=True)
    pontuaveis = listas.groupby(['n_referencias','metodo']).agg(
        usuarios_sem_candidatos_pontuaveis=('n_pontuaveis',lambda s:int(s.eq(0).sum())),
        candidatos_pontuaveis_media=('n_pontuaveis','mean'))
    resumo = resumo.merge(pontuaveis,on=['n_referencias','metodo']).sort_values(['n_referencias','metodo']).reset_index(drop=True)
    return detalhes,resumo,usuarios


def executar(divisao,treino,procedencia,filmes,controles,configuracao,saida):
    inicio = perf_counter()
    divisao,treino,procedencia,filmes,controles,configuracao,saida = map(Path,
        (divisao,treino,procedencia,filmes,controles,configuracao,saida))
    for entrada in (divisao,treino.parent,procedencia.parent,filmes.parent,controles,configuracao.parent):
        if saida.resolve()==entrada.resolve() or entrada.resolve() in saida.resolve().parents:
            raise ValueError('Saída deve ficar fora dos diretórios de entrada.')
    contexto = carregar_desenvolvimento(divisao)
    m,caminhos,antes = _entradas(divisao,treino,procedencia,filmes)
    anterior = validar_saida(controles)
    if (anterior['divisao_execucao_id']!=contexto.execucao_id or anterior['entradas']!=antes
            or anterior['parametros']['seed_referencias']!=201):
        raise ValueError('Controles não pertencem à divisão/protocolo atuais.')
    for n,s in anterior['codigo'].items():
        if assinatura(ROOT/n)!=s:
            raise ValueError('Código dos controles diverge: '+n)
    caminhos.update({f'controles/{n}':controles/n for n in anterior['arquivos']})
    caminhos['controles/manifesto.json'] = controles/MANIFESTO
    caminhos['configuracao_previa'] = configuracao
    antes = {n:assinatura(c) for n,c in caminhos.items()}
    config = json.loads(configuracao.read_text())
    if ({k:config[k] for k in ('min_filme','min_coavaliadores','shrinkage','bloco_itens','seed_referencias','k')}
            !=dict(min_filme=5,min_coavaliadores=5,shrinkage=10,bloco_itens=128,seed_referencias=201,k=10)):
        raise ValueError('Configuração difere do registro único prévio.')
    codigo = {n:assinatura(ROOT/n) for n in (*anterior['codigo'],'item_item_experimental.py','experimento_item_item.py')}
    execucao = iniciar_identificacao(saida)
    _json(saida,'configuracao_previa.json',config)
    dev = contexto.avaliacoes()
    if not dev.groupby('userId').size().ge(5).all():
        raise ValueError('Experimento requer o mínimo individual do protocolo aprovado.')
    catalogo = pd.read_csv(filmes)
    congeladas = pd.read_csv(controles/'listas.csv')
    modelo = ItemItem(dev)
    print('Modelo construído: '+json.dumps(modelo.auditoria),flush=True)
    t = perf_counter()
    listas = gerar_item_item(congeladas,dev,catalogo,modelo)
    segundos_listas = perf_counter()-t
    listas.to_csv(saida/'listas.csv',index=False,mode='x')
    save_npz(saida/'similaridades.npz',modelo.similaridades)
    save_npz(saida/'suportes.npz',modelo.suportes)
    _json(saida,'indices.json',{'movieIds':modelo.movie_ids})
    hash_listas = assinatura(saida/'listas.csv')
    print('Listas dos quatro métodos salvas; agora abrindo validação.',flush=True)
    isolamento = validar_execucao(divisao)
    val = carregar_validacao(divisao,execucao_esperada=contexto.execucao_id)
    detalhes,resumo,usuarios = pontuar_quatro(listas,val)
    # Controles devem coincidir com sua avaliação aprovada (nenhum recálculo de ranking).
    esperado = pd.read_csv(controles/'resumo.csv').sort_values(['n_referencias','metodo']).reset_index(drop=True)
    atual = resumo[resumo.metodo!=METODO][esperado.columns].sort_values(['n_referencias','metodo']).reset_index(drop=True)
    pd.testing.assert_frame_equal(esperado,atual,check_dtype=False,atol=1e-12,rtol=1e-12)
    detalhes.to_csv(saida/'avaliacao_por_usuario.csv',index=False,mode='x')
    resumo.to_csv(saida/'resumo.csv',index=False,mode='x')
    usuarios.to_csv(saida/'usuarios.csv',index=False,mode='x')
    _json(saida,'resumo.json',json.loads(resumo.to_json(orient='records',double_precision=15)))
    auditoria = {'modelo':modelo.auditoria,'isolamento':isolamento,
        'usuarios_elegiveis':len(usuarios),'usuarios_avaliaveis':int(usuarios.avaliado_metricas.sum()),
        'listas_salvas_antes_validacao':True,'hash_listas_antes_validacao':hash_listas,
        'controles_conferem_com_avaliacao_anterior':True,
        'segundos_geracao_listas_quatro_inclui_verificacao_candidatos':segundos_listas,
        'segundos_total_ate_auditoria':perf_counter()-inicio,
        'pico_rss_processo_kib_linux':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'perfil_explicito':'só referências; sem notas pessoais adicionais na agregação',
        'influencia_indireta':'usuário alvo não coavalia candidatos inéditos; suas notas ainda integram o modelo global e a elegibilidade das referências'}
    _json(saida,'auditoria.json',auditoria)
    if (antes!={n:assinatura(c) for n,c in caminhos.items()}
            or codigo!={n:assinatura(ROOT/n) for n in codigo}
            or hash_listas!=assinatura(saida/'listas.csv')):
        raise ValueError('Entradas, código ou listas mudaram durante execução.')
    _json(saida,MANIFESTO,{'esquema':'cinematch.experimento.item_item','versao_esquema':1,
        'execucao_id':execucao,'criado_em':datetime.now(timezone.utc).isoformat(),
        'dataset':m['fonte']['dataset'],'divisao_execucao_id':contexto.execucao_id,
        'entradas':antes,'codigo':codigo,'parametros':config,
        'ambiente':{n:importlib.metadata.version(n) for n in ('numpy','pandas','scipy')},
        'arquivos':{n:assinatura(saida/n) for n in ARQUIVOS}})
    (saida/PENDENTE).unlink()
    print(resumo.to_string(index=False),flush=True)
    return detalhes,resumo,auditoria


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('divisao','treino','procedencia','filmes','controles','configuracao','saida'):
        p.add_argument('--'+n,type=Path,required=True)
    a = p.parse_args()
    executar(**vars(a))
