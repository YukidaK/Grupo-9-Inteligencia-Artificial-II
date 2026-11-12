"""Transporte TMDB do piloto de títulos, desativado por padrão."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from operacao_externa import (ControleExterno, controle_credencial, LimiteOperacional, espera_permitida)
API = 'https://api.themoviedb.org/3'


def _id(valor):
    if type(valor) is not int or valor <= 0:
        raise ValueError('Identificador deve ser inteiro positivo.')
    return valor


def _horario(valor):
    if not isinstance(valor, datetime) or valor.utcoffset() is None:
        raise ValueError('Horário deve informar fuso explícito.')


class FalhaConsulta(OSError):
    """Falha sanitizada de transporte; nunca conserva erro remoto ou token."""
    CODIGOS = frozenset({'HTTP_401','HTTP_403','HTTP_404','HTTP_429','HTTP_5XX','HTTP_OUTRO',
        'TIMEOUT','CONEXAO','RESPOSTA_INVALIDA','RESPOSTA_EXCESSIVA',
        'INTEGRACAO_DESATIVADA','SEM_CREDENCIAL','CREDENCIAL_INVALIDA',
        'CONSULTA_SUSPENSA','REDIRECIONAMENTO_BLOQUEADO'})

    def __init__(self,codigo):
        if codigo not in self.CODIGOS: raise ValueError('Código de falha não permitido.')
        self.codigo = codigo
        super().__init__(codigo)



class SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise FalhaConsulta('REDIRECIONAMENTO_BLOQUEADO') from None


class TransporteTMDB:
    def __init__(self,ids_permitidos,*,habilitado=False,termos_aprovados=False,
                 abrir=None,timeout=3.,max_bytes=1024*1024,relogio=None,monotono=None,esperar=None,controle=None):
        if type(habilitado) is not bool or type(termos_aprovados) is not bool:
            raise ValueError('Habilitação e aprovação devem ser booleanas explícitas.')
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or timeout<=0:
            raise ValueError('Timeout deve ser positivo e finito.')
        if type(max_bytes) is not int or max_bytes<1: raise ValueError('Limite de resposta inválido.')
        self._ids = frozenset(_id(i) for i in ids_permitidos)
        self._token = os.environ.get('TMDB_READ_ACCESS_TOKEN','').strip()
        self._habilitado = habilitado and termos_aprovados
        self.timeout,self.max_bytes = float(timeout),max_bytes
        # Construir opener não abre rede. Sem proxy implícito ou redirecionamento.
        self._abrir = abrir or urllib.request.build_opener(
            urllib.request.ProxyHandler({}),SemRedirecionamento()).open
        self._agora = relogio or (lambda:datetime.now(timezone.utc))
        self._monotono = monotono or time.monotonic
        self._esperar = esperar or time.sleep
        self._pausa_ate = 0.
        self._ultima = None
        self._requisicoes = 0
        self._trava = threading.RLock()
        self._local = threading.local()
        self.controle = controle or (ControleExterno(relogio=self._monotono) if abrir else controle_credencial(self._token))

    @property
    def requisicoes_iniciadas(self):
        with self._trava:
            return self._requisicoes

    def _erro_http(self,codigo,cabecalhos):
        pausa = 0.
        if codigo in (401,403):
            motivo,pausa = 'HTTP_'+str(codigo),600.
        elif codigo==404: motivo = 'HTTP_404'
        elif codigo==429:
            motivo,pausa = 'HTTP_429',60.
            valor = cabecalhos.get('Retry-After','') if cabecalhos else ''
            try:
                if re.fullmatch(r'[0-9]+',valor.strip()):
                    pausa = float(int(valor))
                else:
                    data = parsedate_to_datetime(valor)
                    _horario(data)
                    pausa = max(0.,(data-self._agora()).total_seconds())
                if not math.isfinite(pausa): pausa = 60.
            except (ValueError,TypeError,OverflowError):
                pausa = 60.
        elif 500<=codigo<=599: motivo,pausa = 'HTTP_5XX',60.
        elif 300<=codigo<=399: motivo = 'REDIRECIONAMENTO_BLOQUEADO'
        else: motivo = 'HTTP_OUTRO'
        with self._trava:self._pausa_ate = max(self._pausa_ate,self._monotono()+pausa)
        if pausa:self.controle.suspender(pausa)
        raise FalhaConsulta(motivo) from None

    def _json(self,rota):
        self._local.chamadas=0
        if not self._habilitado:raise FalhaConsulta('INTEGRACAO_DESATIVADA')
        if not self._token:raise FalhaConsulta('SEM_CREDENCIAL')
        if not re.fullmatch(r'[A-Za-z0-9._~+/-]+=*',self._token):raise FalhaConsulta('CREDENCIAL_INVALIDA')
        try:
            with self.controle.admitir():return self._json_admitido(rota)
        except LimiteOperacional as erro:
            raise FalhaConsulta('TIMEOUT' if erro.codigo=='TIMEOUT' else 'CONSULTA_SUSPENSA') from None

    def _json_admitido(self,rota):
        with self._trava:
            if self._monotono()<self._pausa_ate: raise FalhaConsulta('CONSULTA_SUSPENSA')
        with self._trava:
            agora=self._monotono()
            alvo=max(agora,self._ultima+.2) if self._ultima is not None else agora
            intervalo=alvo-agora
            if intervalo>=espera_permitida():raise FalhaConsulta('TIMEOUT')
            self._ultima=alvo
        if intervalo>0:self._esperar(intervalo)
        url = API+rota
        pedido = urllib.request.Request(url,headers={'Authorization':'Bearer '+self._token,
            'Accept':'application/json'},method='GET')
        try:
            self.controle.verificar()
            restante=espera_permitida(self.timeout)
            if restante<=0:raise FalhaConsulta('TIMEOUT')
            with self._trava:self._requisicoes += 1
            self._local.chamadas=1
            with self._abrir(pedido,timeout=restante) as resposta:
                if resposta.geturl()!=url:
                    raise FalhaConsulta('REDIRECIONAMENTO_BLOQUEADO')
                if resposta.status!=200:
                    self._erro_http(resposta.status,resposta.headers)
                tipo = resposta.headers.get('Content-Type','').split(';')[0].strip().lower()
                if tipo!='application/json': raise FalhaConsulta('RESPOSTA_INVALIDA')
                tamanho = resposta.headers.get('Content-Length')
                if tamanho is not None:
                    try: tamanho = int(tamanho)
                    except (ValueError,TypeError): raise FalhaConsulta('RESPOSTA_INVALIDA') from None
                    if tamanho<0: raise FalhaConsulta('RESPOSTA_INVALIDA')
                    if tamanho>self.max_bytes: raise FalhaConsulta('RESPOSTA_EXCESSIVA')
                bruto = resposta.read(self.max_bytes+1)
                if len(bruto)>self.max_bytes: raise FalhaConsulta('RESPOSTA_EXCESSIVA')
                if tamanho is not None and len(bruto)!=tamanho:
                    raise FalhaConsulta('RESPOSTA_INVALIDA')
                # Não aceita um corpo que ecoe a credencial recebida do ambiente.
                if self._token.encode() in bruto: raise FalhaConsulta('RESPOSTA_INVALIDA')
                dados = json.loads(bruto.decode('utf-8'))
                if not isinstance(dados,dict): raise FalhaConsulta('RESPOSTA_INVALIDA')
                if self._token in json.dumps(dados,ensure_ascii=False):
                    raise FalhaConsulta('RESPOSTA_INVALIDA')
                return dados
        except LimiteOperacional as erro:
            raise FalhaConsulta('TIMEOUT' if erro.codigo=='TIMEOUT' else 'CONSULTA_SUSPENSA') from None
        except FalhaConsulta as erro:
            raise erro from None
        except urllib.error.HTTPError as erro:
            try: self._erro_http(erro.code,erro.headers)
            finally: erro.close()
        except TimeoutError:
            self._pausa_ate = self._monotono()+60.
            raise FalhaConsulta('TIMEOUT') from None
        except urllib.error.URLError as erro:
            self._pausa_ate = self._monotono()+60.
            codigo = 'TIMEOUT' if isinstance(erro.reason,TimeoutError) else 'CONEXAO'
            raise FalhaConsulta(codigo) from None
        except OSError:
            self._pausa_ate = self._monotono()+60.
            raise FalhaConsulta('CONEXAO') from None
        except HTTPException:
            raise FalhaConsulta('RESPOSTA_INVALIDA') from None
        except (ValueError,UnicodeError,TypeError,AttributeError):
            raise FalhaConsulta('RESPOSTA_INVALIDA') from None
