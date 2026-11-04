"""Enriquecimento visual opcional. Não importa nem modifica o recomendador."""
import csv
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import json
import math
import os
from pathlib import Path
import re
import threading
import tempfile
import weakref
from http.client import HTTPException
import time
import urllib.error
import urllib.request
from operacao_externa import (ControleExterno, controle_credencial, espera_permitida,
    ConsultasPorChave, LimiteOperacional)

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


class ErroPoster(OSError):
    """Erro público sanitizado: não conserva URL, cabeçalhos ou corpo remoto."""
    def __init__(self,codigo,espera=None):
        self.codigo,self.espera=codigo,espera
        super().__init__(codigo)


class SemRedirecionamentoPoster(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ErroPoster('REDIRECIONAMENTO_BLOQUEADO')


_DISCOS=weakref.WeakValueDictionary()
_DISCOS_TRAVA=threading.Lock()
_SEM_CONSULTA=object()


def _trava_disco(caminho):
    # Coordena instâncias no mesmo processo; nenhuma rede sob esta trava.
    with _DISCOS_TRAVA:
        chave=str(caminho.resolve())
        trava=_DISCOS.get(chave)
        if trava is None:trava=threading.RLock();_DISCOS[chave]=trava
        return trava


class Posteres:
    def __init__(self,links,token='',cache=None,abrir=None,relogio=None,controle=None,
                 *,timeout=TIMEOUT,max_bytes=1024*1024,monotono=None,esperar=None):
        if (isinstance(timeout,bool) or not isinstance(timeout,(int,float))
                or not math.isfinite(timeout) or timeout<=0 or type(max_bytes) is not int or max_bytes<1):
            raise ValueError('Limites de transporte inválidos.')
        self.links=dict(links)
        self._token=token.strip()
        self.controle=controle or (ControleExterno() if abrir else controle_credencial(self._token))
        self.cache_path=Path(cache) if cache else None
        self.abrir=abrir or urllib.request.build_opener(
            urllib.request.ProxyHandler({}),SemRedirecionamentoPoster()).open
        self.agora=relogio or time.time
        self._monotono=monotono or time.monotonic
        self._esperar=esperar or time.sleep
        self.timeout,self.max_bytes=float(timeout),max_bytes
        self._voos=ConsultasPorChave();self.trava=self._voos.trava
        self._transporte_trava=threading.RLock()
        self._disco_trava=_trava_disco(self.cache_path) if self.cache_path else threading.RLock()
        self.cache={};self._alteradas={}
        self.pausa_ate=0;self.ultima_chamada=0
        if self.cache_path:
            with self._disco_trava:self.cache=self._ler_disco()

    @classmethod
    def do_ambiente(cls):
        carregar_ambiente()
        links=os.environ.get('MOVIELENS_LINKS_CSV') or ROOT/'dados/ml-latest-small/links.csv'
        return cls(carregar_links(links),os.environ.get('TMDB_READ_ACCESS_TOKEN',''),ROOT/'cache_tmdb/metadados.json')

    def _ler_disco(self):
        try:
            dados=json.loads(self.cache_path.read_text(encoding='utf-8'))
            if isinstance(dados,dict) and dados.get('versao')==1 and isinstance(dados.get('entradas'),dict):
                return dados['entradas']
        except (OSError,ValueError,TypeError,RecursionError):pass
        return {}

    def _salvar(self):
        if not self.cache_path:return
        temporario=None
        # O snapshot é obtido somente depois de adquirir a trava de escrita.
        with self._disco_trava:
            try:
                with self.trava:
                    self.cache=dict(list(self.cache.items())[-2000:])
                    self._alteradas={k:v for k,v in self._alteradas.items() if k in self.cache}
                    alteradas=dict(self._alteradas);memoria=dict(self.cache)
                if not alteradas:return
                # Outra instância pode ter publicado entradas depois da nossa leitura inicial.
                dados=self._ler_disco() if self.cache_path.exists() else memoria
                dados.update(alteradas);dados=dict(list(dados.items())[-2000:])
                self.cache_path.parent.mkdir(parents=True,exist_ok=True)
                with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',
                        dir=self.cache_path.parent,prefix='.'+self.cache_path.name+'.',suffix='.tmp',delete=False) as f:
                    temporario=Path(f.name)
                    json.dump({'versao':1,'entradas':dados},f,ensure_ascii=True)
                    f.flush();os.fsync(f.fileno())
                temporario.replace(self.cache_path);temporario=None
                with self.trava:
                    for k,v in alteradas.items():
                        if self._alteradas.get(k)==v:self._alteradas.pop(k,None)
                    # Novas publicações em memória durante o I/O têm precedência.
                    self.cache={**dados,**self._alteradas}
                    self.cache=dict(list(self.cache.items())[-2000:])
            except (OSError,ValueError,TypeError,RecursionError):
                pass  # A memória continua utilizável; não publica arquivo incompleto.
            finally:
                if temporario is not None:
                    try:temporario.unlink()
                    except OSError:pass

    def _suspenso(self):
        with self._transporte_trava:return self.agora()<self.pausa_ate

    def _ler_valido(self,chave):
        entrada=self.cache.get(chave)
        if not isinstance(entrada,dict):return None
        try:expira=float(entrada.get('expira',0))
        except (ValueError,TypeError,OverflowError):return None
        return entrada if math.isfinite(expira) and expira>self.agora() else None

    def _entrada(self,chave,produzir):
        def ler():
            valor=self._ler_valido(chave)
            return valor if valor is not None else (_SEM_CONSULTA if self._suspenso() else None)
        def gravar(valor):
            if valor is not _SEM_CONSULTA:
                self.cache[chave]=valor
                if self.cache_path:self._alteradas[chave]=valor
        try:valor,lider=self._voos.executar(chave,ler,produzir,gravar)
        except LimiteOperacional:return None
        if lider and valor is not _SEM_CONSULTA:self._salvar()
        return None if valor is _SEM_CONSULTA else valor

    def _penalizar(self,erro):
        espera=FAILURE_TTL
        codigo=getattr(erro,'code',None)
        if isinstance(erro,ErroPoster):
            codigo=int(erro.codigo[5:]) if re.fullmatch(r'HTTP_[0-9]{3}',erro.codigo) else None
        if codigo in (401,403):espera=600
        elif codigo==429:
            if isinstance(erro,ErroPoster):espera=erro.espera or FAILURE_TTL
            else:
                valor=erro.headers.get('Retry-After','') if erro.headers else ''
                try:espera=max(60,float(valor))
                except (ValueError,TypeError,OverflowError):
                    try:espera=max(60,parsedate_to_datetime(valor).timestamp()-self.agora())
                    except (ValueError,TypeError,OverflowError):espera=60
        if not math.isfinite(espera) or espera<0:espera=FAILURE_TTL
        with self._transporte_trava:self.pausa_ate=max(self.pausa_ate,self.agora()+espera)
        if codigo==429:self.controle.suspender(espera)
        return espera

    def _json(self,rota):
        if not (rota=='/configuration' or re.fullmatch(
                r'/movie/[1-9][0-9]*\?language=pt-BR&append_to_response=images&include_image_language=pt,en,null',rota)):
            raise ErroPoster('DESTINO_INVALIDO')
        if not self._token or not re.fullmatch(r'[A-Za-z0-9._~+/-]+=*',self._token):
            raise ErroPoster('CREDENCIAL_INVALIDA')
        try:
            if self._suspenso():raise ErroPoster('CONSULTA_SUSPENSA')
            with self.controle.admitir():
                try:return self._json_admitido(rota)
                except urllib.error.HTTPError as erro:
                    codigo=erro.code
                    try:espera=self._penalizar(erro) if codigo!=404 else None
                    finally:erro.close()
                    raise ErroPoster('HTTP_'+str(codigo),espera) from None
        except ErroPoster:raise
        except LimiteOperacional as erro:
            raise ErroPoster('TIMEOUT' if erro.codigo=='TIMEOUT' else 'CONSULTA_SUSPENSA') from None
        except TimeoutError:raise ErroPoster('TIMEOUT') from None
        except (OSError,HTTPException):raise ErroPoster('CONEXAO') from None
        except (ValueError,TypeError,AttributeError,UnicodeError,RecursionError):raise ErroPoster('RESPOSTA_INVALIDA') from None

    def _json_admitido(self,rota):
        with self._transporte_trava:
            agora=self._monotono();alvo=max(agora,self.ultima_chamada+.2)
            intervalo=alvo-agora
            if intervalo>=espera_permitida():raise ErroPoster('TIMEOUT')
            self.ultima_chamada=alvo
        if intervalo>0:self._esperar(intervalo)
        self.controle.verificar()
        restante=espera_permitida(self.timeout)
        if restante<=0:raise ErroPoster('TIMEOUT')
        url=API+rota
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+self._token,'Accept':'application/json'})
        with self.abrir(req,timeout=restante) as resposta:
            if resposta.geturl()!=url:raise ErroPoster('REDIRECIONAMENTO_BLOQUEADO')
            status=resposta.status
            if type(status) is not int or status!=200:
                if type(status) is not int or not 100<=status<=599:raise ErroPoster('RESPOSTA_INVALIDA')
                erro=urllib.error.HTTPError(url,status,'HTTP inválido',resposta.headers,None)
                espera=self._penalizar(erro) if status!=404 else None
                raise ErroPoster('HTTP_'+str(status),espera)
            if resposta.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
                raise ErroPoster('MIME_INVALIDO')
            tamanho=resposta.headers.get('Content-Length')
            if tamanho is not None:
                try:tamanho=int(tamanho)
                except (ValueError,TypeError):raise ErroPoster('RESPOSTA_INVALIDA') from None
                if tamanho<0:raise ErroPoster('RESPOSTA_INVALIDA')
                if tamanho>self.max_bytes:raise ErroPoster('RESPOSTA_EXCESSIVA')
            partes=[];total=0
            while True:
                self.controle.verificar()
                parte=resposta.read(min(65536,self.max_bytes-total+1))
                if not parte:break
                total+=len(parte)
                if total>self.max_bytes:raise ErroPoster('RESPOSTA_EXCESSIVA')
                partes.append(parte)
            if tamanho is not None and tamanho!=total:raise ErroPoster('RESPOSTA_INTERROMPIDA')
            bruto=b''.join(partes)
        if self._token.encode() in bruto:raise ErroPoster('RESPOSTA_INVALIDA')
        dados=json.loads(bruto.decode('utf-8'))
        if not isinstance(dados,dict) or self._token in json.dumps(dados,ensure_ascii=False):
            raise ErroPoster('RESPOSTA_INVALIDA')
        return dados

    def _filme(self,tmdb_id):
        try:
            dados=self._json(f'/movie/{tmdb_id}?language=pt-BR&append_to_response=images&include_image_language=pt,en,null')
            if type(dados.get('id')) is not int or dados['id']!=tmdb_id:raise ValueError('ID inválido')
            imagens=dados.get('images',{})
            posters=imagens.get('posters',[]) if isinstance(imagens,dict) else []
            if not isinstance(posters,list):posters=[]
            opcoes=[p for p in posters if isinstance(p,dict) and poster_path(p.get('file_path'))]
            prioridade={'pt':0,'en':1,None:2}
            opcoes.sort(key=lambda p:prioridade.get(p.get('iso_639_1'),3))
            caminho=opcoes[0]['file_path'] if opcoes else poster_path(dados.get('poster_path'))
            return {'poster_path':caminho,'expira':self.agora()+TTL}
        except (OSError,ValueError,TypeError,KeyError) as erro:
            if isinstance(erro,ErroPoster) and erro.codigo=='HTTP_404':
                return {'poster_path':None,'expira':self.agora()+24*3600}
            self._penalizar(erro);return _SEM_CONSULTA

    def _configuracao(self):
        try:
            imagens=self._json('/configuration').get('images',{})
            tamanhos=imagens.get('poster_sizes',[])
            if imagens.get('secure_base_url')!=IMAGE_BASE or not isinstance(tamanhos,list):raise ValueError('Configuração inválida')
            return {'expira':self.agora()+TTL,'tamanhos':[t for t in tamanhos if t in ('w185','w342','w500')]}
        except (OSError,ValueError,TypeError,AttributeError) as erro:
            self._penalizar(erro);return _SEM_CONSULTA

    def obter(self,movie_id):
        tmdb_id=self.links.get(movie_id)
        if type(tmdb_id) is not int or tmdb_id<=0:tmdb_id=None
        vazio={'poster_url':PLACEHOLDER,'thumbnail_url':PLACEHOLDER,'tmdbId':tmdb_id}
        if tmdb_id is None or not self._token:return vazio
        entrada=self._entrada('filme:'+str(tmdb_id),lambda:self._filme(tmdb_id))
        caminho=poster_path(entrada.get('poster_path')) if entrada else None
        if not caminho:return vazio
        config=self._entrada('config',self._configuracao) or {}
        tamanhos=config.get('tamanhos',[])
        if not isinstance(tamanhos,list):tamanhos=[]
        tamanho='w342' if 'w342' in tamanhos else 'w500'
        mini='w185' if 'w185' in tamanhos else tamanho
        return {'poster_url':IMAGE_BASE+tamanho+caminho,
            'thumbnail_url':IMAGE_BASE+mini+caminho,'tmdbId':tmdb_id}
