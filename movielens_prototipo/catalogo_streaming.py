"""Catálogo local verificável. Só entradas homologadas e comprovadas são expostas.

Não obtém evidências da rede. Hash não substitui revisão/autenticidade da fonte.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse,parse_qs

ESQUEMA='cinematch.catalogo_streaming'


def _data(valor):
    if not isinstance(valor,str):raise ValueError('Data de verificação ausente.')
    try:d=datetime.fromisoformat(valor.replace('Z','+00:00'))
    except ValueError:raise ValueError('Data de verificação inválida.') from None
    if d.utcoffset() is None:raise ValueError('Data deve informar fuso.')
    return d


def carregar_catalogo(caminho):
    """Falha explícita para auditoria; a camada web faz fallback vazio seguro."""
    caminho=Path(caminho)
    dados=json.loads(caminho.read_text(encoding='utf-8'))
    if (not isinstance(dados,dict) or dados.get('esquema')!=ESQUEMA or type(dados.get('versao')) is not int
            or dados['versao']!=1 or dados.get('regiao')!='BR'
            or not isinstance(dados.get('provedores'),list)):
        raise ValueError('Esquema/região de catálogo incompatível.')
    revisado=_data(dados.get('verificado_em'))
    ids=set();homologados=[]
    for p in dados['provedores']:
        if not isinstance(p,dict):raise ValueError('Entrada de provedor inválida.')
        i=p.get('id');nome=p.get('nome')
        if (type(i) is not int or i<=0 or i in ids or not isinstance(nome,str) or not nome.strip()
                or p.get('regiao')!='BR' or p.get('estado') not in ('homologado','pendente')):
            raise ValueError('ID/nome/região/estado de provedor inválido.')
        ids.add(i)
        quando=_data(p.get('verificado_em'))
        evidencia=p.get('procedencia',{})
        if not isinstance(evidencia,dict) or not isinstance(evidencia.get('url'),str) or quando>revisado:
            raise ValueError('Procedência/data inválida.')
        if p['estado']=='pendente':
            if not isinstance(p.get('motivo_pendencia'),str) or not p['motivo_pendencia'].strip():
                raise ValueError('Pendência sem justificativa.')
            continue
        url=urlparse(evidencia['url'])
        query=parse_qs(url.query)
        if (url.scheme!='https' or url.netloc!='api.themoviedb.org'
                or url.path!='/3/watch/providers/movie' or url.fragment
                or query.get('watch_region')!=['BR']
                or set(query)-{'watch_region','language'}):
            raise ValueError('Fonte regional de filmes incompatível.')
        relativo=evidencia.get('arquivo')
        digest=evidencia.get('sha256')
        if (not isinstance(relativo,str) or Path(relativo).is_absolute()
                or not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest)):
            raise ValueError('Arquivo ou hash de evidência inválido.')
        arquivo=(caminho.parent/relativo).resolve()
        if caminho.parent.resolve() not in arquivo.parents:raise ValueError('Evidência fora do catálogo.')
        bruto=arquivo.read_bytes()
        if hashlib.sha256(bruto).hexdigest()!=digest:raise ValueError('Evidência sem integridade.')
        envelope=json.loads(bruto)
        if not isinstance(envelope,dict) or set(envelope)!={'url','regiao','tipo','obtido_em','resposta'}:
            raise ValueError('Envelope deve conter somente dados públicos e contexto de consulta.')
        obtido=_data(envelope.get('obtido_em'))
        if (envelope.get('url')!=evidencia['url'] or envelope.get('regiao')!='BR'
                or envelope.get('tipo')!='FILME' or not obtido<=quando<=revisado
                or not isinstance(envelope.get('resposta'),dict)
                or not isinstance(envelope['resposta'].get('results'),list)):
            raise ValueError('Evidência sem contexto regional/temporal válido.')
        encontrados=[r for r in envelope['resposta']['results'] if isinstance(r,dict)
            and type(r.get('provider_id')) is int and r['provider_id']==i]
        if len(encontrados)!=1 or encontrados[0].get('provider_name')!=nome:
            raise ValueError('ID/nome não comprovado pela evidência.')
        homologados.append((i,nome))
    return tuple(homologados)
