"""Contrato RF-02A. Sem transporte HTTP, credenciais, sessão ou recomendador.

O chamador injeta uma consulta; nesta etapa, somente testes a utilizam.
"""
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import re
from urllib.parse import urlparse

from identidades import IdentidadeConteudo, TipoConteudo, conteudo_movielens
from posteres import carregar_links
from preferencias_streaming import Modo, PreferenciasStreaming

FONTE = 'tmdb.watch_providers/justwatch'


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


def ler_cache(cache,chave,agora):
    entrada = cache.get(chave)
    if entrada and entrada.consultado_em<=agora<entrada.expira_em:
        cache.move_to_end(chave)
        return entrada
    return None


def gravar_cache(cache,chave,entrada,limite):
    cache[chave] = entrada
    cache.move_to_end(chave)
    while len(cache)>limite:
        cache.popitem(last=False)


class Modalidade(Enum):
    ASSINATURA = 'flatrate'
    ALUGUEL = 'rent'
    COMPRA = 'buy'
    GRATIS = 'free'
    ANUNCIOS = 'ads'


class Estado(Enum):
    CONFIRMADA = 'confirmada'
    DESCONHECIDA = 'desconhecida'
    ERRO = 'erro'


class Compatibilidade(Enum):
    INCLUIDO_ASSINATURA = 'incluido_assinatura'
    NAO_CONFIRMADO = 'nao_confirmado_nas_assinaturas'
    DESCONHECIDA = 'desconhecida'
    ERRO = 'erro'
    INDISPONIVEL_CONFIRMADO = 'indisponivel_confirmado'
    SEM_SELECAO = 'sem_assinaturas_selecionadas'


def _id(valor):
    if type(valor) is not int or valor<=0:
        raise ValueError('Identificador deve ser inteiro positivo.')
    return valor


def _regiao(valor):
    if not isinstance(valor,str) or not re.fullmatch('[A-Z]{2}',valor):
        raise ValueError('Região deve ser código de duas letras maiúsculas.')


def _horario(valor):
    if not isinstance(valor,datetime) or valor.utcoffset() is None:
        raise ValueError('Horário deve informar fuso explícito.')


@dataclass(frozen=True)
class Oferta:
    provedor_id: int
    modalidade: Modalidade
    nome: str

    def __post_init__(self):
        _id(self.provedor_id)
        if not isinstance(self.modalidade,Modalidade) or not isinstance(self.nome,str) or not self.nome.strip():
            raise ValueError('Oferta inválida.')


@dataclass(frozen=True)
class Disponibilidade:
    conteudo: IdentidadeConteudo
    tmdb_id: int | None
    regiao: str
    consultado_em: datetime
    expira_em: datetime
    estado: Estado
    ofertas: tuple[Oferta,...] = ()
    fonte: str = FONTE
    motivo: str = ''
    link_tmdb: str | None = None
    ausencia_confirmada: bool = False
    evidencia_ausencia: str | None = None

    def __post_init__(self):
        if not isinstance(self.conteudo,IdentidadeConteudo) or not isinstance(self.estado,Estado):
            raise ValueError('Identidade ou estado inválido.')
        if self.tmdb_id is not None: _id(self.tmdb_id)
        _regiao(self.regiao)
        _horario(self.consultado_em)
        _horario(self.expira_em)
        if self.expira_em<=self.consultado_em or not isinstance(self.fonte,str) or not self.fonte:
            raise ValueError('Validade ou origem inválida.')
        if not isinstance(self.ofertas,tuple) or any(not isinstance(o,Oferta) for o in self.ofertas):
            raise ValueError('Ofertas devem ser uma tupla imutável.')
        if self.estado is not Estado.CONFIRMADA and self.ofertas:
            raise ValueError('Informação não confirmada não pode anunciar ofertas.')
        if type(self.ausencia_confirmada) is not bool:
            raise ValueError('Confirmação de ausência deve ser explícita.')
        if self.ausencia_confirmada:
            if (self.fonte==FONTE or self.estado is not Estado.CONFIRMADA or self.ofertas
                    or not isinstance(self.evidencia_ausencia,str) or not self.evidencia_ausencia.strip()):
                raise ValueError('Ausência exige outra fonte explícita e evidência; TMDB não a comprova.')
        elif self.estado is Estado.CONFIRMADA and not self.ofertas:
            raise ValueError('Sem ofertas não significa indisponibilidade confirmada.')


@dataclass(frozen=True)
class ConsultaControlada:
    disponibilidade: Disponibilidade | None
    origem: str  # CACHE, LOCAL, CONSULTA ou NAO_VERIFICADO
    chamadas_transporte: int = 0

    def __post_init__(self):
        if self.origem not in {'CACHE','LOCAL','CONSULTA','NAO_VERIFICADO'}:
            raise ValueError('Origem de consulta inválida.')
        if self.disponibilidade is not None and not isinstance(self.disponibilidade,Disponibilidade):
            raise ValueError('Evidência de disponibilidade inválida.')
        if type(self.chamadas_transporte) is not int or not 0<=self.chamadas_transporte<=1:
            raise ValueError('Uma consulta controlada admite no máximo uma chamada, sem retries.')
        if (self.disponibilidade is None)!=(self.origem=='NAO_VERIFICADO'):
            raise ValueError('Evidência e origem incompatíveis.')
        if self.origem!='CONSULTA' and self.chamadas_transporte:
            raise ValueError('Cache/local/não verificado não podem chamar transporte.')


def compatibilidade(dados, preferencias, agora):
    """Classifica evidência; não filtra candidatos nem relaxa modo flexível."""
    _horario(agora)
    if not preferencias.provedores:
        return Compatibilidade.SEM_SELECAO
    if dados.regiao!=preferencias.regiao or not dados.consultado_em<=agora<dados.expira_em:
        return Compatibilidade.DESCONHECIDA
    if dados.estado is Estado.ERRO:
        return Compatibilidade.ERRO
    if dados.estado is Estado.DESCONHECIDA:
        return Compatibilidade.DESCONHECIDA
    if dados.ausencia_confirmada:
        return Compatibilidade.INDISPONIVEL_CONFIRMADO
    if any(o.provedor_id in preferencias.provedores and o.modalidade is Modalidade.ASSINATURA for o in dados.ofertas):
        return Compatibilidade.INCLUIDO_ASSINATURA
    return Compatibilidade.NAO_CONFIRMADO


def links_movielens(caminho):
    """Reutiliza a leitura que rejeita conflitos; nunca busca obra por título."""
    return {conteudo_movielens(i):t for i,t in carregar_links(caminho).items()}


def catalogo_provedores(dados):
    """Normaliza IDs, não marcas por nome. A região pertence à requisição futura."""
    if not isinstance(dados,dict) or not isinstance(dados.get('results'),list):
        raise ValueError('Catálogo de provedores inválido.')
    mapa = {}
    for p in dados['results']:
        if not isinstance(p,dict): raise ValueError('Provedor inválido.')
        i = _id(p.get('provider_id'))
        nome = p.get('provider_name')
        if not isinstance(nome,str) or not nome.strip() or (i in mapa and mapa[i]!=nome):
            raise ValueError('Nome ou ID de provedor conflitante.')
        mapa[i] = nome
    return tuple(sorted(mapa.items()))


def interpretar(dados,conteudo,tmdb_id,regiao,agora,ttl,ttl_desconhecido):
    """Normaliza o envelope de movie/watch/providers. Falhas de formato propagam."""
    if (not isinstance(dados,dict) or type(dados.get('id')) is not int or dados['id']!=tmdb_id
            or not isinstance(dados.get('results'),dict)):
        raise ValueError('Resposta/ID incompatível.')
    if regiao not in dados['results']:
        return Disponibilidade(conteudo,tmdb_id,regiao,agora,agora+ttl_desconhecido,
            Estado.DESCONHECIDA,motivo='SEM_DADOS_REGIAO')
    regional = dados['results'][regiao]
    if not isinstance(regional,dict) or set(regional)-{'link',*(m.value for m in Modalidade)}:
        raise ValueError('Região ou modalidade inválida.')
    link = regional.get('link')
    if link is not None:
        if not isinstance(link,str): raise ValueError('Link inválido.')
        u = urlparse(link)
        if (u.scheme!='https' or u.netloc!='www.themoviedb.org'
                or not re.fullmatch(rf'/movie/{tmdb_id}(?:-[A-Za-z0-9%_-]+)?/watch',u.path)
                or u.fragment):
            raise ValueError('Link TMDB inválido.')
    ofertas = {}
    for modalidade in Modalidade:
        lista = regional.get(modalidade.value,[])
        if not isinstance(lista,list): raise ValueError('Lista de ofertas inválida.')
        for p in lista:
            if not isinstance(p,dict): raise ValueError('Oferta inválida.')
            oferta = Oferta(p.get('provider_id'),modalidade,p.get('provider_name'))
            chave = (oferta.provedor_id,modalidade.value)
            if chave in ofertas and ofertas[chave]!=oferta: raise ValueError('Oferta conflitante.')
            ofertas[chave] = oferta
    valores = tuple(ofertas[k] for k in sorted(ofertas))
    estado = Estado.CONFIRMADA if valores else Estado.DESCONHECIDA
    return Disponibilidade(conteudo,tmdb_id,regiao,agora,
        agora+(ttl if valores else ttl_desconhecido),estado,valores,
        motivo='OFERTAS_REPORTADAS' if valores else 'SEM_OFERTAS_REPORTADAS',link_tmdb=link)


class Disponibilidades:
    """Cache somente em memória, chave completa. Nenhum transporte padrão existe."""
    def __init__(self,links,consultar,*,relogio=None,ttl=timedelta(hours=24),
                 ttl_desconhecido=timedelta(minutes=15),ttl_erro=timedelta(seconds=60),limite=512):
        if not callable(consultar): raise ValueError('Consulta deve ser injetada explicitamente.')
        if type(limite) is not int or limite<1: raise ValueError('Limite de cache inválido.')
        for valor in (ttl,ttl_desconhecido,ttl_erro):
            if not isinstance(valor,timedelta) or valor<=timedelta(0): raise ValueError('TTL inválido.')
        self.links = dict(links)
        for identidade,tmdb_id in self.links.items():
            if not isinstance(identidade,IdentidadeConteudo): raise ValueError('Mapeamento exige identidade completa.')
            _id(tmdb_id)
        self.consultar = consultar
        self.agora = relogio or (lambda:datetime.now(timezone.utc))
        self.ttl,self.ttl_desconhecido,self.ttl_erro = ttl,ttl_desconhecido,ttl_erro
        self.limite = limite
        self.cache = OrderedDict()

    def obter_sem_consulta(self,conteudo,regiao='BR'):
        """Somente cache válido ou resultado local; nunca chama a função injetada."""
        if not isinstance(conteudo,IdentidadeConteudo): raise ValueError('Informe identidade completa.')
        _regiao(regiao)
        agora = self.agora()
        _horario(agora)
        tmdb_id = self.links.get(conteudo)
        anterior = ler_cache(self.cache,(conteudo,tmdb_id,regiao,FONTE),agora)
        if anterior: return ConsultaControlada(anterior,'CACHE')
        if conteudo.tipo is not TipoConteudo.FILME or tmdb_id is None:
            return ConsultaControlada(self.obter(conteudo,regiao),'LOCAL')
        return ConsultaControlada(None,'NAO_VERIFICADO')

    def obter(self,conteudo,regiao='BR'):
        if not isinstance(conteudo,IdentidadeConteudo): raise ValueError('Informe identidade completa.')
        _regiao(regiao)
        agora = self.agora()
        _horario(agora)
        tmdb_id = self.links.get(conteudo)
        chave = (conteudo,tmdb_id,regiao,FONTE)
        anterior = ler_cache(self.cache,chave,agora)
        if anterior:
            return anterior
        if conteudo.tipo is not TipoConteudo.FILME or tmdb_id is None:
            resposta = Disponibilidade(conteudo,None,regiao,agora,agora+self.ttl_desconhecido,
                Estado.DESCONHECIDA,motivo='TIPO_NAO_SUPORTADO' if conteudo.tipo is not TipoConteudo.FILME else 'SEM_MAPEAMENTO_TMDB')
        else:
            try:
                resposta = interpretar(self.consultar(tmdb_id,regiao),conteudo,tmdb_id,regiao,
                    agora,self.ttl,self.ttl_desconhecido)
            except FalhaConsulta as erro:
                resposta = Disponibilidade(conteudo,tmdb_id,regiao,agora,agora+self.ttl_erro,
                    Estado.ERRO,motivo=erro.codigo)
            except OSError:
                # Não conserva mensagens arbitrárias que possam conter credenciais/URLs.
                resposta = Disponibilidade(conteudo,tmdb_id,regiao,agora,agora+self.ttl_erro,
                    Estado.ERRO,motivo='FALHA_FONTE')
            except (ValueError,TypeError,KeyError):
                resposta = Disponibilidade(conteudo,tmdb_id,regiao,agora,agora+self.ttl_erro,
                    Estado.ERRO,motivo='RESPOSTA_INVALIDA')
        gravar_cache(self.cache,chave,resposta,self.limite)
        return resposta
