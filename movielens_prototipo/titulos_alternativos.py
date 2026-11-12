"""Índice auxiliar de nomes revisados. Carregamento local, sem transporte HTTP."""
from datetime import datetime
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ARQUIVO = Path(__file__).with_name('titulos_br.json')


def validar_aliases(documento, filmes, links):
    """Valida associação explícita ao catálogo e ao mapeamento TMDB existente."""
    if (not isinstance(documento, dict)
            or documento.get('esquema') != 'cinematch.titulos'
            or type(documento.get('versao')) is not int or documento['versao'] != 1
            or documento.get('idioma') != 'pt-BR'
            or not isinstance(documento.get('filmes'), list)):
        raise ValueError('Índice de títulos incompatível.')
    catalogo = {int(f.movieId): f.title for f in filmes.itertuples()}
    resultado = {}
    for item in documento['filmes']:
        if not isinstance(item, dict):
            raise ValueError('Registro de título inválido.')
        if item.get('revisao', 'aprovada') != 'aprovada':
            raise ValueError('Título aguarda revisão humana.')
        mid, tid = item.get('movieId'), item.get('tmdbId')
        if (type(mid) is not int or mid <= 0 or mid not in catalogo or mid in resultado
                or type(tid) is not int or tid <= 0 or links.get(mid) != tid):
            raise ValueError('Associação de identificadores inválida.')
        ano = re.search(r'\((\d{4})\)\s*$', catalogo[mid])
        if (item.get('titulo_catalogo') != catalogo[mid]
                or type(item.get('ano')) is not int or not ano
                or item['ano'] != int(ano[1])):
            raise ValueError('Título de origem ou ano incompatível.')
        titulo = item.get('titulo_br')
        outros = item.get('alternativos')
        if (not isinstance(titulo, str) or not titulo.strip() or len(titulo) > 300
                or not isinstance(outros, list) or len(outros) > 30
                or any(not isinstance(n, str) or not n.strip() or len(n) > 300 for n in outros)):
            raise ValueError('Nomes alternativos inválidos.')
        fonte = item.get('fonte')
        if not isinstance(fonte, str):
            raise ValueError('Fonte ausente.')
        url = urlsplit(fonte)
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Fonte inválida.')
        data = item.get('verificado_em')
        if not isinstance(data, str):
            raise ValueError('Data de verificação ausente.')
        try:
            datetime.strptime(data, '%Y-%m-%d')
        except ValueError:
            raise ValueError('Data de verificação inválida.') from None
        resultado[mid] = {'titulo_br': titulo.strip(),
                          'alternativos': list(dict.fromkeys(n.strip() for n in outros))}
    return resultado


def carregar_aliases(filmes, links, caminho=ARQUIVO):
    """Índice ausente ou incompatível mantém pesquisa original, sem consultar API."""
    try:
        documento = json.loads(Path(caminho).read_text(encoding='utf-8'))
        return validar_aliases(documento, filmes, links)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        return {}


def titulo_br_tmdb(resposta, tmdb_id):
    """Interpreta uma resposta já obtida de /movie/{id}/translations.

    Exige tradução explicitamente identificada como pt/BR. O idioma padrão de
    /movie/{id}?language=pt-BR pode retornar fallback, por isso não é prova regional.
    Falha da fonte ou tradução ausente é representada por None.
    """
    if type(tmdb_id) is not int or tmdb_id <= 0:
        raise ValueError('Identificador TMDB inválido.')
    if not isinstance(resposta, dict) or type(resposta.get('id')) is not int or resposta['id'] != tmdb_id:
        return None
    traducoes = resposta.get('translations')
    if not isinstance(traducoes, list):
        return None
    titulos = set()
    for item in traducoes:
        if not isinstance(item, dict):
            return None
        if item.get('iso_639_1') == 'pt' and item.get('iso_3166_1') == 'BR':
            dados = item.get('data')
            titulo = dados.get('title') if isinstance(dados, dict) else None
            if not isinstance(titulo, str) or not titulo.strip() or len(titulo) > 300:
                return None
            titulos.add(titulo.strip())
    return next(iter(titulos)) if len(titulos) == 1 else None
