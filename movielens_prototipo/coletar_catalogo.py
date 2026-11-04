"""Coleta explícita, separada da aplicação; nunca promove catálogo público."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from disponibilidade import catalogo_provedores
from tmdb_disponibilidade import TransporteTMDB

VERSAO='1'
URL='https://api.themoviedb.org/3/watch/providers/movie?watch_region=BR&language=pt-BR'


def aprovacoes(caminho):
    dados=json.loads(Path(caminho).read_text(encoding='utf-8'))
    if (set(dados)!={'termos_aprovados','autorizacao_operacional','responsavel','aprovado_em','escopo','documentos'}
            or dados['termos_aprovados'] is not True or dados['autorizacao_operacional'] is not True
            or dados['escopo']!=['catalogo_filmes_BR']
            or not isinstance(dados['responsavel'],str) or not dados['responsavel'].strip()
            or not isinstance(dados['documentos'],list) or not dados['documentos']):
        raise ValueError('Aprovações humanas documentadas são obrigatórias.')
    data=datetime.fromisoformat(dados['aprovado_em'])
    if data.utcoffset() is None or data>datetime.now(timezone.utc):raise ValueError('Data de aprovação inválida.')
    for doc in dados['documentos']:
        if set(doc)!={'arquivo','sha256'}:raise ValueError('Referência documental inválida.')
        arquivo=Path(caminho).resolve().parent/doc['arquivo']
        if hashlib.sha256(arquivo.read_bytes()).hexdigest()!=doc['sha256']:raise ValueError('Documento sem integridade.')
    return dados


def coletar(caminho_aprovacoes,saida,*,transporte=None):
    # Checagem antes de construir transporte ou ler credencial do ambiente.
    aprovado=aprovacoes(caminho_aprovacoes)
    if Path(saida).exists():raise ValueError('Use um diretório novo; nunca sobrescrever evidências.')
    cliente=transporte or TransporteTMDB([],habilitado=True,termos_aprovados=True)
    resposta=cliente.consultar_catalogo('BR','pt-BR')
    provedores=catalogo_provedores(resposta)
    ids=[p['provider_id'] for p in resposta['results']]
    if len(ids)!=len(set(ids)):raise ValueError('IDs duplicados na coleta.')
    agora=datetime.now(timezone.utc).isoformat()
    envelope={'url':URL,'regiao':'BR','tipo':'FILME','obtido_em':agora,'resposta':resposta}
    bruto=json.dumps(envelope,ensure_ascii=False,indent=2).encode()
    digest=hashlib.sha256(bruto).hexdigest()
    candidatos={'esquema':'cinematch.catalogo_streaming','versao':1,'regiao':'BR',
        'verificado_em':agora,'provedores':[{'id':i,'nome':nome,'regiao':'BR','estado':'pendente',
            'verificado_em':agora,'motivo_pendencia':'Aguarda revisão humana; não publicado.',
            'procedencia':{'url':URL,'arquivo':'evidencia.json','sha256':digest}} for i,nome in provedores]}
    pasta=Path(saida);pasta.mkdir(parents=True,exist_ok=False)
    arquivos={'evidencia.json':bruto,'candidatos.json':json.dumps(candidatos,ensure_ascii=False,indent=2).encode()}
    for nome,conteudo in arquivos.items():
        with (pasta/nome).open('xb') as f:f.write(conteudo)
    manifesto={'procedimento':'coleta_catalogo_BR','versao':VERSAO,'fonte':URL,'regiao':'BR',
        'obtido_em':agora,'candidatos':len(provedores),'homologados':0,
        'aprovacoes_sha256':hashlib.sha256(Path(caminho_aprovacoes).read_bytes()).hexdigest(),
        'arquivos':{n:hashlib.sha256(c).hexdigest() for n,c in arquivos.items()}}
    with (pasta/'manifesto.json').open('x',encoding='utf-8') as f:json.dump(manifesto,f,indent=2)
    return manifesto


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executar',action='store_true');parser.add_argument('--aprovacoes');parser.add_argument('--saida')
    args=parser.parse_args()
    if not args.executar:
        print('SEM REDE: procedimento preparado. Exige revisão dos termos, aprovação humana documentada e autorização operacional; coleta não homologa nem publica.')
    elif not args.aprovacoes or not args.saida:parser.error('Informe --aprovacoes e --saida nova.')
    else:
        try:print(json.dumps(coletar(args.aprovacoes,args.saida)))
        except (ValueError,OSError,TypeError,KeyError):raise SystemExit('Coleta não concluída. Verifique aprovações, integridade e configuração sem registrar credenciais.') from None
