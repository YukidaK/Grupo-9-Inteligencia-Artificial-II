"""Enriquecimento visual opcional. Não importa nem modifica o recomendador."""
import csv
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
PLACEHOLDER = '/static/poster-placeholder.svg'
API = 'https://api.themoviedb.org/3'
IMAGE_BASE = 'https://image.tmdb.org/t/p/'
TTL = 7 * 24 * 3600
FAILURE_TTL = 60
TIMEOUT = 3


def carregar_ambiente(pasta=ROOT):
    """Lê somente as duas opções conhecidas; variáveis exportadas têm precedência."""
    try:
        linhas = (Path(pasta) / '.env').read_text(encoding='utf-8').splitlines()
    except OSError:
        return
    for linha in linhas:
        chave, separador, valor = linha.strip().partition('=')
        if separador and chave in ('TMDB_READ_ACCESS_TOKEN', 'MOVIELENS_LINKS_CSV'):
            os.environ.setdefault(chave, valor.strip().strip('\"\''))


def identificador(valor):
    try:
        n = Decimal(str(valor).strip())
        return int(n) if n.is_finite() and n > 0 and n == n.to_integral_value() else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def carregar_links(caminho):
    """Ausências e conflitos não viram outro filme. Nenhuma busca por título."""
    mapa, conflitos = {}, set()
    try:
        with Path(caminho).open(encoding='utf-8-sig', newline='') as arquivo:
            for linha in csv.DictReader(arquivo):
                movie_id, tmdb_id = identificador(linha.get('movieId')), identificador(linha.get('tmdbId'))
                if movie_id is None or tmdb_id is None:
                    continue
                if movie_id in mapa and mapa[movie_id] != tmdb_id:
                    conflitos.add(movie_id)
                mapa[movie_id] = tmdb_id
    except (OSError, UnicodeError, csv.Error):
        return {}
    return {i: t for i, t in mapa.items() if i not in conflitos}


def poster_path(valor):
    return valor if isinstance(valor, str) and re.fullmatch(r'/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)', valor) else None


class Posteres:
    def __init__(self, links, token='', cache=None, abrir=None, relogio=None):
        self.links = links
        self._token = token.strip()
        self.cache_path = Path(cache) if cache else None
        self.abrir = abrir or urllib.request.urlopen
        self.agora = relogio or time.time
        self.trava = threading.RLock()
        self.cache = {}
        self.pausa_ate = 0
        self.ultima_chamada = 0
        if self.cache_path:
            try:
                dados = json.loads(self.cache_path.read_text(encoding='utf-8'))
                if dados.get('versao') == 1 and isinstance(dados.get('entradas'), dict):
                    self.cache = dados['entradas']
            except (OSError, ValueError, AttributeError):
                pass

    @classmethod
    def do_ambiente(cls):
        carregar_ambiente()
        links = os.environ.get('MOVIELENS_LINKS_CSV') or ROOT/'dados/ml-latest-small/links.csv'
        return cls(carregar_links(links), os.environ.get('TMDB_READ_ACCESS_TOKEN', ''), ROOT/'cache_tmdb/metadados.json')

    def _salvar(self):
        if not self.cache_path:
            return
        try:
            # Cache limitado aos metadados recentes, sem token ou dados de sessão.
            self.cache = dict(list(self.cache.items())[-2000:])
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporario = self.cache_path.with_suffix('.tmp')
            temporario.write_text(json.dumps({'versao': 1, 'entradas': self.cache}), encoding='utf-8')
            temporario.replace(self.cache_path)
        except OSError:
            pass  # Falha de disco não impede sugestões ou placeholders.

    def _json(self, rota):
        if self.agora() < self.pausa_ate:
            raise OSError('Consulta temporariamente suspensa')
        # No máximo cinco chamadas/segundo, serializadas, sem repetição automática.
        intervalo = .2 - (time.monotonic() - self.ultima_chamada)
        if intervalo > 0:
            time.sleep(intervalo)
        self.ultima_chamada = time.monotonic()
        req = urllib.request.Request(API + rota, headers={
            'Authorization': 'Bearer ' + self._token, 'Accept': 'application/json'})
        with self.abrir(req, timeout=TIMEOUT) as resposta:
            dados = json.load(resposta)
        if not isinstance(dados, dict):
            raise ValueError('Metadados inválidos')
        return dados

    def _penalizar(self, erro):
        espera = FAILURE_TTL
        if isinstance(erro, urllib.error.HTTPError):
            if erro.code in (401, 403):
                espera = 600
            elif erro.code == 429:
                valor = erro.headers.get('Retry-After', '') if erro.headers else ''
                try:
                    espera = max(60, float(valor))
                except ValueError:
                    try:
                        espera = max(60, parsedate_to_datetime(valor).timestamp() - self.agora())
                    except (ValueError, TypeError, OverflowError):
                        espera = 60
        self.pausa_ate = self.agora() + espera

    def obter(self, movie_id):
        tmdb_id = self.links.get(movie_id)
        vazio = {'poster_url': PLACEHOLDER, 'thumbnail_url': PLACEHOLDER, 'tmdbId': tmdb_id}
        if tmdb_id is None or not self._token:
            return vazio
        with self.trava:
            chave = 'filme:' + str(tmdb_id)
            entrada = self.cache.get(chave, {})
            if not isinstance(entrada, dict):
                entrada = {}
            try:
                valido = float(entrada.get('expira', 0)) > self.agora()
            except (ValueError, TypeError):
                valido = False
            caminho = poster_path(entrada.get('poster_path')) if valido else None
            if not valido:
                if self.agora() < self.pausa_ate:
                    return vazio
                try:
                    # Inclui português e alternativas em uma única consulta de metadados.
                    dados = self._json(f'/movie/{tmdb_id}?language=pt-BR&append_to_response=images&include_image_language=pt,en,null')
                    if type(dados.get('id')) is not int or dados['id'] != tmdb_id:
                        raise ValueError('ID de resposta incompatível')
                    imagens = dados.get('images', {})
                    posters = imagens.get('posters', []) if isinstance(imagens, dict) else []
                    if not isinstance(posters, list):
                        posters = []
                    opcoes = [p for p in posters if isinstance(p, dict) and poster_path(p.get('file_path'))]
                    prioridade = {'pt': 0, 'en': 1, None: 2}
                    opcoes.sort(key=lambda p: prioridade.get(p.get('iso_639_1'), 3))
                    caminho = opcoes[0]['file_path'] if opcoes else poster_path(dados.get('poster_path'))
                    self.cache[chave] = {'poster_path': caminho, 'expira': self.agora() + TTL}
                    self._salvar()
                except (OSError, ValueError, TypeError, KeyError) as erro:
                    if isinstance(erro, urllib.error.HTTPError) and erro.code == 404:
                        self.cache[chave] = {'poster_path': None, 'expira': self.agora() + 24*3600}
                        self._salvar()
                        return vazio
                    self._penalizar(erro)
                    # Falhas não são persistidas: nova tentativa após cooldown ou reinício.
                    return vazio
            if not caminho:
                return vazio
            # Configuração consultada sob demanda; fallback w500 é documentado pelo TMDB.
            config = self.cache.get('config', {})
            if not isinstance(config, dict):
                config = {}
            try:
                config_valida = float(config.get('expira', 0)) > self.agora()
            except (TypeError, ValueError):
                config_valida = False
            if not config_valida and self.agora() >= self.pausa_ate:
                try:
                    imagens = self._json('/configuration').get('images', {})
                    tamanhos = imagens.get('poster_sizes', [])
                    if imagens.get('secure_base_url') != IMAGE_BASE or not isinstance(tamanhos, list):
                        raise ValueError('Configuração de imagens inválida')
                    config = {'expira': self.agora() + TTL, 'tamanhos': [t for t in tamanhos if t in ('w185', 'w342', 'w500')]}
                    self.cache['config'] = config
                    self._salvar()
                except (OSError, ValueError, TypeError, AttributeError) as erro:
                    self._penalizar(erro)
                    config = {}
            tamanhos = config.get('tamanhos', [])
            if not isinstance(tamanhos, list):
                tamanhos = []
            tamanho = 'w342' if 'w342' in tamanhos else 'w500'
            mini = 'w185' if 'w185' in tamanhos else tamanho
            return {'poster_url': IMAGE_BASE + tamanho + caminho,
                    'thumbnail_url': IMAGE_BASE + mini + caminho, 'tmdbId': tmdb_id}
