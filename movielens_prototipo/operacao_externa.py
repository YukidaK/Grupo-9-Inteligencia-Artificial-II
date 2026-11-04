"""Controles internos de processo. Não abre rede e não contém credenciais."""
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import math
import threading
import time

_contexto = ContextVar('prazo_externo',default=None)
_global = threading.local()


class LimiteOperacional(OSError):
    def __init__(self,codigo):
        self.codigo=codigo
        super().__init__(codigo)


class TravaRegistro:
    """Marca a seção crítica global para impedir transporte nos nossos clientes."""
    def __init__(self):self._lock=threading.RLock()
    def __enter__(self):
        self._lock.acquire();_global.profundidade=getattr(_global,'profundidade',0)+1;return self
    def __exit__(self,*a):
        _global.profundidade-=1;self._lock.release()


def exigir_fora_do_registro():
    if getattr(_global,'profundidade',0):raise LimiteOperacional('TRAVA_GLOBAL')


@dataclass(frozen=True)
class Prazo:
    inicio: float
    segundos: float
    relogio: object = time.monotonic
    def restante(self):return max(0.,self.segundos-(self.relogio()-self.inicio))


@contextmanager
def usar_prazo(prazo):
    token=_contexto.set(prazo)
    try:yield
    finally:_contexto.reset(token)


def espera_permitida(maximo=3.):
    prazo=_contexto.get()
    return min(maximo,prazo.restante()) if prazo else maximo


class ControleExterno:
    """Quota local conservadora, não contratual. Sem filas ilimitadas/retries."""
    def __init__(self,*,concorrencia=2,chamadas=60,janela=60.,fila=3.,relogio=time.monotonic):
        if (type(concorrencia) is not int or concorrencia<1 or type(chamadas) is not int or chamadas<1
                or isinstance(janela,bool) or not isinstance(janela,(int,float)) or not math.isfinite(janela) or janela<=0
                or isinstance(fila,bool) or not isinstance(fila,(int,float)) or not math.isfinite(fila) or fila<=0):
            raise ValueError('Limites operacionais inválidos.')
        self._slots=threading.BoundedSemaphore(concorrencia)
        self._lock=threading.Lock();self._inicios=deque();self._pausa=0.
        self.chamadas,self.janela,self.agora=chamadas,float(janela),relogio
        self.fila=float(fila)
        self.iniciadas=0;self.em_andamento=0;self.pico=0

    def suspender(self,segundos):
        if not math.isfinite(segundos) or segundos<0:segundos=60.
        with self._lock:self._pausa=max(self._pausa,self.agora()+segundos)

    def verificar(self):
        exigir_fora_do_registro()
        if espera_permitida()<=0:raise LimiteOperacional('TIMEOUT')
        with self._lock:
            if self.agora()<self._pausa:raise LimiteOperacional('CONSULTA_SUSPENSA')

    @contextmanager
    def admitir(self):
        exigir_fora_do_registro()
        espera=espera_permitida(self.fila)
        if espera<=0 or not self._slots.acquire(timeout=espera):raise LimiteOperacional('TIMEOUT')
        admitida=False
        try:
            with self._lock:
                agora=self.agora()
                while self._inicios and self._inicios[0]<=agora-self.janela:self._inicios.popleft()
                if agora<self._pausa:raise LimiteOperacional('CONSULTA_SUSPENSA')
                if len(self._inicios)>=self.chamadas:raise LimiteOperacional('ORCAMENTO_ESGOTADO')
                if espera_permitida()<=0:raise LimiteOperacional('TIMEOUT')
                self._inicios.append(agora);self.iniciadas+=1;self.em_andamento+=1
                self.pico=max(self.pico,self.em_andamento);admitida=True
            yield
        finally:
            if admitida:
                with self._lock:self.em_andamento-=1
            self._slots.release()


_registro={};_registro_lock=threading.Lock()
def controle_credencial(token):
    """Mesmo token compartilha quota; registro guarda somente SHA-256, sem token."""
    chave=hashlib.sha256(token.encode()).digest()
    with _registro_lock:
        if chave not in _registro:
            if len(_registro)>=64:raise LimiteOperacional('LIMITE_CREDENCIAIS')
            _registro[chave]=ControleExterno()
        return _registro[chave]


class ConsultasPorChave:
    """Cache sob trava curta; produtor fora dela; espera limitada por chave."""
    def __init__(self):self.trava=threading.RLock();self._pendentes={}
    def executar(self,chave,ler,produzir,gravar):
        fim=time.monotonic()+espera_permitida()
        while True:
            with self.trava:
                anterior=ler()
                if anterior is not None:return anterior,False
                evento=self._pendentes.get(chave)
                if evento is None:
                    evento=threading.Event();self._pendentes[chave]=evento;lider=True
                else:lider=False
            if lider:break
            espera=min(espera_permitida(),max(0.,fim-time.monotonic()))
            if espera<=0 or not evento.wait(espera):raise LimiteOperacional('TIMEOUT')
        try:
            resultado=produzir()
            with self.trava:gravar(resultado)
            return resultado,True
        finally:
            with self.trava:self._pendentes.pop(chave,None);evento.set()
