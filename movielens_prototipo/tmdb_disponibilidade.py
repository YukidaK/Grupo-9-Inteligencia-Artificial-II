"""RF-02B: transporte especializado, desativado por padrão e fora da aplicação."""
from collections import OrderedDict
from dataclasses import dataclass
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
from urllib.parse import urlencode

from disponibilidade import (
    Disponibilidades, Estado, FONTE, FalhaConsulta, _id, _regiao, _horario,
    catalogo_provedores, ler_cache, gravar_cache, ConsultaControlada,
)
from operacao_externa import (ControleExterno, controle_credencial, ConsultasPorChave,
    LimiteOperacional, espera_permitida)
from identidades import IdentidadeConteudo, TipoConteudo

API = 'https://api.themoviedb.org/3'


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

    def consultar_filme(self,tmdb_id,regiao='BR'):
        _id(tmdb_id)
        _regiao(regiao)
        if tmdb_id not in self._ids:
            raise ValueError('TMDB ID não pertence ao mapeamento validado de filmes.')
        # Este endpoint retorna países no corpo; região não é idioma nem query aqui.
        return self._json(f'/movie/{tmdb_id}/watch/providers')

    def consultar_catalogo(self,regiao='BR',idioma='pt-BR'):
        _regiao(regiao)
        if not isinstance(idioma,str) or not re.fullmatch('[a-z]{2}-[A-Z]{2}',idioma):
            raise ValueError('Idioma deve usar formato como pt-BR.')
        return self._json('/watch/providers/movie?'+urlencode({'watch_region':regiao,'language':idioma}))


@dataclass(frozen=True)
class CatalogoRegional:
    regiao: str
    idioma: str
    consultado_em: datetime
    expira_em: datetime
    estado: Estado
    provedores: tuple
    motivo: str
    fonte: str = FONTE


class ClienteDisponibilidadeTMDB:
    def __init__(self,links,*,habilitado=False,termos_aprovados=False,abrir=None,
                 relogio=None,monotono=None,esperar=None,timeout=3.,max_bytes=1024*1024,
                 limite=512,limite_catalogo=32,controle=None):
        if type(limite_catalogo) is not int or limite_catalogo<1:
            raise ValueError('Limite de catálogo inválido.')
        self._voos=ConsultasPorChave()
        self._trava = self._voos.trava
        self._catalogos = OrderedDict()
        self._limite_catalogo = limite_catalogo
        self._agora = relogio or (lambda:datetime.now(timezone.utc))
        # Validação dos vínculos é feita ANTES de construir o transporte.
        self._disponibilidades = Disponibilidades(links,lambda *a:None,relogio=self._agora,limite=limite)
        ids = [i for c,i in self._disponibilidades.links.items() if c.tipo is TipoConteudo.FILME]
        self._transporte = TransporteTMDB(ids,habilitado=habilitado,termos_aprovados=termos_aprovados,
            abrir=abrir,relogio=self._agora,monotono=monotono,esperar=esperar,timeout=timeout,max_bytes=max_bytes,controle=controle)
        self._disponibilidades.consultar = self._transporte.consultar_filme

    def obter(self,conteudo,regiao='BR'):
        return self.obter_controlado(conteudo,regiao,permitir_consulta=True).disponibilidade

    def obter_controlado(self,conteudo,regiao='BR',*,permitir_consulta=False):
        if type(permitir_consulta) is not bool:raise ValueError('Permissão deve ser explícita.')
        def ler():
            local=self._disponibilidades.obter_sem_consulta(conteudo,regiao)
            return local if local.origem!='NAO_VERIFICADO' or not permitir_consulta else None
        def produzir():
            base=self._disponibilidades
            # Cache privado transitório: a rede nunca mantém a trava do cache compartilhado.
            isolado=Disponibilidades({conteudo:base.links[conteudo]},base.consultar,relogio=base.agora,ttl=base.ttl,
                ttl_desconhecido=base.ttl_desconhecido,ttl_erro=base.ttl_erro,limite=base.limite)
            dados=isolado.obter(conteudo,regiao)
            return ConsultaControlada(dados,'CONSULTA',getattr(self._transporte._local,'chamadas',0))
        def gravar(retorno):
            dados=retorno.disponibilidade
            chave=(conteudo,dados.tmdb_id,regiao,FONTE)
            gravar_cache(self._disponibilidades.cache,chave,dados,self._disponibilidades.limite)
        # Valida antes de construir chave. ler() faz também validação da região.
        with self._trava:
            anterior=ler()
            if anterior is not None:return anterior
        try:
            retorno,lider=self._voos.executar(('filme',conteudo,regiao),ler,produzir,gravar)
            return retorno
        except LimiteOperacional as erro:
            from datetime import timedelta
            from disponibilidade import Disponibilidade
            agora=self._agora()
            dados=Disponibilidade(conteudo,self._disponibilidades.links.get(conteudo),regiao,
                agora,agora+timedelta(seconds=60),Estado.ERRO,motivo='TIMEOUT')
            return ConsultaControlada(dados,'LOCAL')

    def provedores(self,regiao='BR',idioma='pt-BR'):
        _regiao(regiao)
        if not isinstance(idioma,str) or not re.fullmatch('[a-z]{2}-[A-Z]{2}',idioma):
            raise ValueError('Idioma deve usar formato como pt-BR.')
        chave=('catalogo_filmes',regiao,idioma,FONTE)
        def ler():return ler_cache(self._catalogos,chave,self._agora())
        try:
            resposta,_=self._voos.executar(chave,ler,lambda:self._produzir_catalogo(regiao,idioma),
                lambda r:gravar_cache(self._catalogos,chave,r,self._limite_catalogo))
            return resposta
        except LimiteOperacional:
            agora=self._agora()
            return CatalogoRegional(regiao,idioma,agora,agora+self._disponibilidades.ttl_erro,Estado.ERRO,(),'TIMEOUT')

    def _produzir_catalogo(self,regiao='BR',idioma='pt-BR'):
        _regiao(regiao)
        if not isinstance(idioma,str) or not re.fullmatch('[a-z]{2}-[A-Z]{2}',idioma):
            raise ValueError('Idioma deve usar formato como pt-BR.')
        agora = self._agora()
        _horario(agora)
        chave = ('catalogo_filmes',regiao,idioma,FONTE)
        try:
            dados = catalogo_provedores(self._transporte.consultar_catalogo(regiao,idioma))
            estado,motivo = (Estado.CONFIRMADA,'PROVEDORES_REPORTADOS') if dados else (Estado.DESCONHECIDA,'SEM_PROVEDORES_REPORTADOS')
            ttl = self._disponibilidades.ttl if dados else self._disponibilidades.ttl_desconhecido
        except (FalhaConsulta,ValueError,TypeError,KeyError) as erro:
            dados,estado = (),Estado.ERRO
            motivo = erro.codigo if isinstance(erro,FalhaConsulta) else 'RESPOSTA_INVALIDA'
            ttl = self._disponibilidades.ttl_erro
        resposta = CatalogoRegional(regiao,idioma,agora,agora+ttl,estado,dados,motivo)
        return resposta
