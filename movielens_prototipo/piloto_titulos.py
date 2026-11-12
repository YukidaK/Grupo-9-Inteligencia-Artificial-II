"""Piloto offline e coleta explícita de traduções. Nenhum efeito na aplicação web."""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import pandas as pd

from transporte_tmdb import FalhaConsulta
from posteres import carregar_links
from titulos_alternativos import ARQUIVO, validar_aliases, titulo_br_tmdb
from transporte_tmdb import TransporteTMDB

ESQUEMA = 'cinematch.piloto_titulos'
VERSAO = 1
API = 'https://api.themoviedb.org/3/movie/'
FINAIS = {'preexistente', 'sem_tmdb', 'candidato', 'sem_traducao', 'conflito'}


def digest(dados):
    return hashlib.sha256(json.dumps(dados, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def planejar(filmes, ratings, links, indice, limite=100, fontes=None):
    if type(limite) is not int or not 1 <= limite <= 100:
        raise ValueError('Limite deve estar entre 1 e 100.')
    if filmes.movieId.duplicated().any():
        raise ValueError('Catálogo com IDs duplicados.')
    aliases = validar_aliases(indice, filmes, links)
    catalogo = {int(f.movieId): f.title for f in filmes.itertuples()}
    if (ratings[['userId', 'movieId', 'rating']].isna().any().any()
            or not set(ratings.movieId).issubset(catalogo)):
        raise ValueError('Avaliações incompatíveis com o catálogo.')
    contagens = ratings.groupby('movieId').size()
    ids = sorted(contagens.index, key=lambda i: (-int(contagens[i]), int(i)))[:limite]
    repetidos = Counter(links.values())
    itens = []
    for mid in ids:
        mid = int(mid)
        tid = links.get(mid)
        ano = re.search(r'\((\d{4})\)\s*$', catalogo[mid])
        status = 'pendente'
        if mid in aliases:
            status = 'preexistente'
        elif type(tid) is not int or tid <= 0:
            tid, status = None, 'sem_tmdb'
        elif repetidos[tid] > 1 or not ano:
            status = 'conflito'
        itens.append({'movieId': mid, 'tmdbId': tid, 'titulo_catalogo': catalogo[mid],
                      'ano': int(ano[1]) if ano else None,
                      'avaliacoes': int(contagens[mid]), 'inicial': status})
    return {'esquema': ESQUEMA, 'versao': VERSAO, 'idioma': 'pt-BR',
            'ordenacao': 'contagem de todas as avaliações decrescente; movieId crescente',
            'fontes': fontes or {}, 'indice_sha256': digest(indice), 'itens': itens}


def interpretar(resposta, tid):
    if not isinstance(resposta, dict) or type(resposta.get('id')) is not int:
        return 'erro', None, 'RESPOSTA_INVALIDA'
    if resposta['id'] != tid:
        return 'conflito', None, 'ID_DIVERGENTE'
    traducoes = resposta.get('translations')
    if not isinstance(traducoes, list) or any(not isinstance(t, dict) for t in traducoes):
        return 'erro', None, 'RESPOSTA_INVALIDA'
    nomes = set()
    for t in traducoes:
        if t.get('iso_639_1') == 'pt' and t.get('iso_3166_1') == 'BR':
            data = t.get('data')
            nome = data.get('title') if isinstance(data, dict) else None
            if not isinstance(nome, str) or len(nome) > 300:
                return 'erro', None, 'RESPOSTA_INVALIDA'
            if nome.strip():
                nomes.add(nome.strip())
    if len(nomes) > 1:
        return 'conflito', None, 'TITULOS_DIVERGENTES'
    titulo = titulo_br_tmdb(resposta, tid) if nomes else None
    if nomes and titulo is None:
        return 'erro', None, 'RESPOSTA_INVALIDA'
    return ('candidato', titulo, None) if titulo else ('sem_traducao', None, None)


class TransporteTraducoesTMDB(TransporteTMDB):
    """Reutiliza timeouts, orçamento, limites e proteção HTTPS do transporte existente."""
    def consultar_traducoes(self, tmdb_id):
        if type(tmdb_id) is not int or tmdb_id <= 0 or tmdb_id not in self._ids:
            raise ValueError('ID fora do mapeamento validado.')
        return self._json(f'/movie/{tmdb_id}/translations')


def salvar(caminho, documento):
    caminho = Path(caminho)
    bruto = json.dumps(documento, ensure_ascii=False, indent=2).encode()
    fd, temporario = tempfile.mkstemp(prefix='.piloto-', suffix='.tmp', dir=caminho.parent)
    try:
        with os.fdopen(fd, 'wb') as arquivo:
            arquivo.write(bruto)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    finally:
        if os.path.exists(temporario):
            os.unlink(temporario)


@contextmanager
def exclusivo(pasta):
    trava = Path(pasta) / '.execucao.lock'
    fd = os.open(trava, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as arquivo:
            arquivo.write(str(os.getpid()))
        yield
    finally:
        trava.unlink()


def carregar_estado(pasta, plano):
    caminho = Path(pasta) / 'estado.json'
    if not caminho.exists():
        return {'plano': plano, 'plano_sha256': digest(plano),
                'registros': {str(i['movieId']): {'estado': i['inicial'], 'tentativas': 0}
                              for i in plano['itens']}, 'pausa_ate': None}
    envelope = json.loads(caminho.read_text(encoding='utf-8'))
    estado = envelope['estado']
    if (envelope['sha256'] != digest(estado) or estado['plano'] != plano
            or estado['plano_sha256'] != digest(plano)
            or set(estado['registros']) != {str(i['movieId']) for i in plano['itens']}):
        raise ValueError('Checkpoint incompatível ou corrompido.')
    for registro in estado['registros'].values():
        if (registro['estado'] not in FINAIS | {'pendente', 'erro'}
                or type(registro['tentativas']) is not int or registro['tentativas'] < 0):
            raise ValueError('Registro de checkpoint inválido.')
    return estado


def checkpoint(pasta, estado):
    salvar(Path(pasta) / 'estado.json', {'sha256': digest(estado), 'estado': estado})


def candidatos(estado):
    entradas = []
    for item in estado['plano']['itens']:
        r = estado['registros'][str(item['movieId'])]
        if r['estado'] == 'candidato':
            entradas.append({k: item[k] for k in ('movieId', 'tmdbId', 'titulo_catalogo', 'ano')} |
                            {'titulo_br': r['titulo'], 'alternativos': [],
                             'fonte': API + str(item['tmdbId']) + '/translations',
                             'verificado_em': r['obtido_em'][:10], 'revisao': 'pendente',
                             'evidencia_sha256': r['resposta_sha256']})
    return {'esquema': 'cinematch.titulos', 'versao': 1, 'idioma': 'pt-BR', 'filmes': entradas}


def resumir(estado):
    c = Counter(r['estado'] for r in estado['registros'].values())
    return {'selecionados': len(estado['registros']), 'estados': dict(c),
            'filmes_consultados': sum(r.get('chamadas_rede', 0) > 0 for r in estado['registros'].values()),
            'chamadas_rede': sum(r.get('chamadas_rede', 0) for r in estado['registros'].values()),
            'tentativas': sum(r['tentativas'] for r in estado['registros'].values()),
            'candidatos_pt_BR': c['candidato'], 'homologados_novos': 0}


def executar(plano, pasta, cliente=None, *, repetir_erros=False, agora=None, max_consultas=100):
    if type(max_consultas) is not int or not 0 <= max_consultas <= 100:
        raise ValueError('Orçamento inválido.')
    agora = agora or (lambda: datetime.now(timezone.utc))
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    with exclusivo(pasta):
        permitidos = {'estado.json', 'candidatos.json', 'resumo.json', '.execucao.lock'}
        if any(p.name not in permitidos or p.is_symlink() for p in pasta.iterdir()):
            raise ValueError('Saída ocupada por arquivos incompatíveis.')
        if not (pasta / 'estado.json').exists() and any((pasta / n).exists() for n in ('candidatos.json', 'resumo.json')):
            raise ValueError('Saída anterior sem checkpoint.')
        estado = carregar_estado(pasta, plano)
        checkpoint(pasta, estado)
        pausa = estado['pausa_ate']
        pausado = pausa is not None and agora().timestamp() < pausa
        usadas = 0
        for item in plano['itens']:
            r = estado['registros'][str(item['movieId'])]
            if (cliente is None or pausado or usadas >= max_consultas
                    or r['estado'] in FINAIS or (r['estado'] == 'erro' and not repetir_erros)):
                continue
            r['tentativas'] += 1
            r['estado'] = 'erro'
            r['motivo'] = 'INTERROMPIDA'
            checkpoint(pasta, estado)  # Uma interrupção deixa um erro retomável explícito.
            usadas += 1
            iniciadas = cliente.requisicoes_iniciadas
            try:
                resposta = cliente.consultar_traducoes(item['tmdbId'])
                status, titulo, motivo = interpretar(resposta, item['tmdbId'])
                r.update(estado=status, motivo=motivo, obtido_em=agora().isoformat())
                if titulo:
                    r.update(titulo=titulo, resposta_sha256=digest(resposta))
                checkpoint(pasta, estado)
            except FalhaConsulta as erro:
                r['motivo'] = erro.codigo
                # Retry-After e cooldown do transporte são persistidos entre processos.
                pausa_transporte = getattr(cliente, '_pausa_ate', 0.)
                monotono = getattr(cliente, '_monotono', lambda: 0.)
                restante = max(0., pausa_transporte - monotono())
                estado['pausa_ate'] = agora().timestamp() + max(60., restante)
                checkpoint(pasta, estado)
                break  # Evita repetir 401/403, 429 ou falhas de rede em todo o piloto.
            finally:
                r['chamadas_rede'] = r.get('chamadas_rede', 0) + max(0, cliente.requisicoes_iniciadas - iniciadas)
                checkpoint(pasta, estado)
        salvar(pasta / 'candidatos.json', candidatos(estado))
        resumo = resumir(estado)
        salvar(pasta / 'resumo.json', resumo)
        return resumo


def autorizar(caminho):
    d = json.loads(Path(caminho).read_text(encoding='utf-8'))
    if (not isinstance(d, dict) or d.get('termos_aprovados') is not True or d.get('autorizacao_operacional') is not True
            or d.get('escopo') != 'titulos_filmes_pt_BR'
            or not isinstance(d.get('documentos'), list) or not d['documentos']):
        raise ValueError('Aprovação de termos e operação ausente para este escopo.')
    for doc in d['documentos']:
        if (not isinstance(doc, dict) or set(doc) != {'arquivo', 'sha256'}
                or not isinstance(doc['arquivo'], str) or not doc['arquivo']
                or not isinstance(doc['sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', doc['sha256'])):
            raise ValueError('Referência documental inválida.')
        p = Path(doc['arquivo'])
        if p.is_absolute() or '..' in p.parts:
            raise ValueError('Referência documental inválida.')
        if hashlib.sha256((Path(caminho).parent / p).read_bytes()).hexdigest() != doc['sha256']:
            raise ValueError('Documento de aprovação sem integridade.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dados', type=Path, default=Path(__file__).parent / 'dados/ml-latest-small')
    p.add_argument('--indice', type=Path, default=ARQUIVO)
    p.add_argument('--saida', type=Path, required=True)
    p.add_argument('--executar', action='store_true')
    p.add_argument('--aprovacoes', type=Path)
    p.add_argument('--repetir-erros', action='store_true')
    p.add_argument('--max-consultas', type=int, default=100)
    a = p.parse_args()
    filmes = pd.read_csv(a.dados / 'movies.csv')
    ratings = pd.read_csv(a.dados / 'ratings.csv')
    links = carregar_links(a.dados / 'links.csv')
    indice = json.loads(a.indice.read_text(encoding='utf-8'))
    fontes = {n: hashlib.sha256((a.dados / n).read_bytes()).hexdigest()
              for n in ('movies.csv', 'ratings.csv', 'links.csv')}
    plano = planejar(filmes, ratings, links, indice, fontes=fontes)
    # Nunca permite saída sobre dados, resultados, fontes ou índice público.
    destino = a.saida.resolve()
    permitida = Path(__file__).resolve().parents[1] / 'local'
    if not destino.is_relative_to(permitida.resolve()):
        raise ValueError('Use uma saída experimental sob local/.')
    cliente = None
    if a.executar:
        if a.aprovacoes is None:
            raise ValueError('Informe as aprovações documentadas.')
        autorizar(a.aprovacoes)
        if not os.environ.get('TMDB_READ_ACCESS_TOKEN', '').strip():
            raise ValueError('Credencial ausente no ambiente.')
        cliente = TransporteTraducoesTMDB([i['tmdbId'] for i in plano['itens']
                                         if i['inicial'] == 'pendente'],
                                        habilitado=True, termos_aprovados=True)
    resumo = executar(plano, a.saida, cliente, repetir_erros=a.repetir_erros,
                      max_consultas=a.max_consultas)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('Piloto não concluído. Confira entradas, checkpoint e autorizações locais.') from None
