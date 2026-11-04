"""RF-02D: preferências públicas locais, sem disponibilidade ou transporte."""
from preferencias_streaming import PreferenciasStreaming, Modo
from pathlib import Path
from catalogo_streaming import carregar_catalogo

# Não consulta rede; ausência/corrupção de evidência nunca expõe opções sem prova.
try:
    CATALOGO_BR = carregar_catalogo(Path(__file__).with_name('catalogo_streaming_br.json'))
except (OSError,ValueError,TypeError,KeyError):
    CATALOGO_BR = ()


def preferencias_publicas(sessao,catalogo=CATALOGO_BR,mensagem=''):
    vistos=set()
    provedores=[]
    for identificador,nome in catalogo:
        if (type(identificador) is not int or identificador<=0 or identificador in vistos
                or not isinstance(nome,str) or not nome.strip()):
            raise ValueError('Catálogo interno de streaming inválido.')
        vistos.add(identificador)
        provedores.append({'id':identificador,'nome':nome})
    p=sessao.streaming
    if p and p.provedores-vistos:
        mensagem=(mensagem+' ' if mensagem else '')+'Há provedores salvos fora do catálogo atual. Suas escolhas foram preservadas para revisão; desmarque os IDs incompatíveis e salve para removê-los.'
    return {'catalogo':{'regiao':'BR','provedores':provedores,
                        'estado':'disponivel' if provedores else 'pendente_validacao'},
            'preferencias':None if p is None else {'regiao':p.regiao,'provedores':sorted(p.provedores),
                'modo':p.modo.value,'ativo':False},
            'integracao_ativa':False,'mensagem':mensagem,
            'reconciliacao':{'provedores_ausentes':sorted(p.provedores-vistos) if p else [],
                'revisao_necessaria':bool(p and p.provedores-vistos)}}


def executar_streaming(sessao,dados,catalogo=CATALOGO_BR):
    atual=preferencias_publicas(sessao,catalogo)
    acao=dados.get('acao')
    if acao=='estado' and set(dados)=={'acao'}:return atual
    obrigatorios={'acao','provedores','regiao','modo'}
    if acao!='salvar' or not obrigatorios<=set(dados) or set(dados)-obrigatorios-{'remover_incompativeis'}:
        raise ValueError('Pedido de preferências inválido. O filtro real permanece desativado.')
    ids=dados['provedores']
    if (dados['regiao']!='BR' or not isinstance(ids,list) or len(ids)>100
            or any(type(i) is not int or i<=0 for i in ids) or len(set(ids))!=len(ids)):
        raise ValueError('Informe IDs distintos de provedores do catálogo brasileiro.')
    try:modo=Modo(dados['modo'])
    except (ValueError,TypeError):raise ValueError('Modo de streaming inválido.') from None
    permitidos=frozenset(p['id'] for p in atual['catalogo']['provedores'])
    ausentes=frozenset(atual['reconciliacao']['provedores_ausentes'])
    remover=dados.get('remover_incompativeis',[])
    if (not isinstance(remover,list) or any(type(i) is not int or i<=0 for i in remover)
            or len(set(remover))!=len(remover) or not set(remover)<=ausentes or set(remover)&set(ids)
            or not set(ids)<=permitidos|ausentes):
        raise ValueError('Revisão de provedores inválida. Novos IDs devem pertencer ao catálogo.')
    # Omissão por cliente antigo não apaga preferências históricas silenciosamente.
    p=PreferenciasStreaming(frozenset(ids)|(ausentes-set(remover)),'BR',modo,ativo=False)
    sessao.configurar_streaming(p,provedores_permitidos=permitidos|ausentes,regiao_catalogo='BR')
    return preferencias_publicas(sessao,catalogo,'Preferências salvas nesta sessão. A seleção ainda não altera as recomendações.')
