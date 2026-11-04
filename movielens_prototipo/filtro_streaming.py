"""RF-02C: filtro interno de candidatos já ordenados; sem conexão ao fluxo web."""
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import math
from numbers import Real
import time
from operacao_externa import Prazo, usar_prazo

from disponibilidade import (
    Disponibilidade, Estado, ConsultaControlada, compatibilidade, Compatibilidade,
)
from preferencias_streaming import PreferenciasStreaming, Modo
from identidades import IdentidadeConteudo, TipoConteudo, conteudo_movielens


@dataclass(frozen=True)
class CandidatoStreaming:
    conteudo: IdentidadeConteudo
    dados: dict

    def __post_init__(self):
        if not isinstance(self.conteudo,IdentidadeConteudo) or self.conteudo.tipo is not TipoConteudo.FILME:
            raise ValueError('Esta etapa admite somente identidades de filmes.')
        if (not isinstance(self.dados,dict) or isinstance(self.dados.get('pontuacao'),bool)
                or not isinstance(self.dados.get('pontuacao'),Real)
                or not math.isfinite(self.dados['pontuacao'])):
            raise ValueError('Candidato deve ter pontuação prévia finita.')
        if ('movieId' in self.dados and self.conteudo.fonte=='movielens'
                and conteudo_movielens(self.dados['movieId'])!=self.conteudo):
            raise ValueError('movieId legado não corresponde à identidade do candidato.')

    @classmethod
    def movielens(cls,dados):
        return cls(conteudo_movielens(dados['movieId']),deepcopy(dados))


@dataclass(frozen=True)
class LimitesStreaming:
    consultas: int = 20
    candidatos: int = 50
    segundos: float = 5.
    tamanho: int = 10

    def __post_init__(self):
        if (type(self.consultas) is not int or self.consultas<0
                or type(self.candidatos) is not int or self.candidatos<1
                or type(self.tamanho) is not int or not 1<=self.tamanho<=10
                or isinstance(self.segundos,bool) or not isinstance(self.segundos,(int,float))
                or not math.isfinite(self.segundos) or self.segundos<0):
            raise ValueError('Limites operacionais inválidos.')


@dataclass(frozen=True)
class ItemStreaming:
    candidato: CandidatoStreaming
    disponibilidade: Disponibilidade | None
    classificacao: Compatibilidade | None
    verificado: bool


@dataclass(frozen=True)
class ResultadoStreaming:
    itens: tuple[ItemStreaming,...]
    configurado: bool
    ativo: bool
    parcial: bool
    limites_atingidos: tuple[str,...]
    estatisticas: dict
    mensagem: str


def _desconhecida(conteudo,regiao,agora,motivo):
    return Disponibilidade(conteudo,None,regiao,agora,agora+timedelta(minutes=15),
        Estado.DESCONHECIDA,motivo=motivo)


def filtrar_streaming(candidatos,preferencias,servico,*,limites=None,relogio=None,monotono=None):
    """Consome iterável limitado; não calcula nem reordena scores.

    servico.obter_controlado() decide cache/consulta sob sua própria trava.
    A autorização de uma consulta NÃO habilita o transporte RF-02B.
    """
    if preferencias is not None and not isinstance(preferencias,PreferenciasStreaming):
        raise ValueError('Preferências incompatíveis.')
    limites = limites or LimitesStreaming()
    if not isinstance(limites,LimitesStreaming): raise ValueError('Limites incompatíveis.')
    agora = relogio or (lambda:datetime.now(timezone.utc))
    tick = monotono or time.monotonic
    inicio = tick()
    ativo = preferencias is not None and preferencias.ativo
    cont = dict(candidatos_lidos=0,duplicatas=0,cache=0,locais=0,consultas_necessarias=0,
        tentativas_orcadas=0,chamadas_transporte=0,nao_verificados=0,confirmados_assinatura=0,
        desconhecidos=0,erros=0)
    itens,identidades,atingidos = [],set(),set()
    if ativo and preferencias.modo is Modo.RESTRITO and not preferencias.provedores:
        return ResultadoStreaming((),True,True,False,(),cont,
            'Selecione pelo menos um serviço para usar o filtro restrito. Não escolhi serviços automaticamente.')
    if ativo and not callable(getattr(servico,'obter_controlado',None)):
        raise ValueError('Serviço deve oferecer consulta controlada atômica.')
    iterator = iter(candidatos)
    esgotado = False
    while len(itens)<limites.tamanho and cont['candidatos_lidos']<limites.candidatos:
        prazo = ativo and tick()-inicio>=limites.segundos
        if prazo:
            atingidos.add('TEMPO')
            if preferencias.modo is Modo.RESTRITO: break
        try: candidato = next(iterator)
        except StopIteration:
            esgotado = True
            break
        cont['candidatos_lidos']+=1
        if not isinstance(candidato,CandidatoStreaming): raise ValueError('Candidato incompatível.')
        if candidato.conteudo in identidades:
            cont['duplicatas']+=1
            continue
        identidades.add(candidato.conteudo)
        candidato = CandidatoStreaming(candidato.conteudo,deepcopy(candidato.dados))
        if not ativo:
            itens.append(ItemStreaming(candidato,None,None,False))
            continue
        instante = agora()
        if not isinstance(instante,datetime) or instante.utcoffset() is None: raise ValueError('Relógio deve informar fuso.')
        if prazo:
            retorno = ConsultaControlada(None,'NAO_VERIFICADO')
            dados = _desconhecida(candidato.conteudo,preferencias.regiao,instante,'LIMITE_TEMPO')
        else:
            permitir = cont['tentativas_orcadas']<limites.consultas
            with usar_prazo(Prazo(inicio,limites.segundos,tick)):
                retorno = servico.obter_controlado(candidato.conteudo,preferencias.regiao,permitir_consulta=permitir)
            if not isinstance(retorno,ConsultaControlada): raise ValueError('Resposta controlada incompatível.')
            if retorno.origem=='CONSULTA':
                if not permitir: raise ValueError('Serviço violou a proibição de consulta.')
                cont['tentativas_orcadas']+=1
                cont['consultas_necessarias']+=1
            elif retorno.origem=='NAO_VERIFICADO':
                cont['consultas_necessarias']+=1
                atingidos.add('CONSULTAS')
            elif retorno.origem=='CACHE': cont['cache']+=1
            elif retorno.origem=='LOCAL': cont['locais']+=1
            dados = retorno.disponibilidade or _desconhecida(
                candidato.conteudo,preferencias.regiao,instante,'NAO_VERIFICADO_ORCAMENTO')
        instante = agora()
        if not isinstance(instante,datetime) or instante.utcoffset() is None: raise ValueError('Relógio deve informar fuso.')
        cont['chamadas_transporte']+=retorno.chamadas_transporte
        verificado = retorno.origem!='NAO_VERIFICADO'
        if dados.conteudo!=candidato.conteudo or dados.regiao!=preferencias.regiao:
            dados = _desconhecida(candidato.conteudo,preferencias.regiao,instante,'RESPOSTA_INCOMPATIVEL')
            verificado = False
        elif not dados.consultado_em<=instante<dados.expira_em:
            # Preserva a data original; não renova artificialmente a evidência.
            dados = replace(dados,estado=Estado.DESCONHECIDA,ofertas=(),ausencia_confirmada=False,
                evidencia_ausencia=None,motivo='INFORMACAO_VENCIDA_OU_FUTURA')
            verificado = False
        if not verificado: cont['nao_verificados']+=1
        if dados.estado is Estado.DESCONHECIDA: cont['desconhecidos']+=1
        if dados.estado is Estado.ERRO: cont['erros']+=1
        classificacao = compatibilidade(dados,preferencias,instante)
        incluido = classificacao is Compatibilidade.INCLUIDO_ASSINATURA
        if incluido: cont['confirmados_assinatura']+=1
        if incluido or preferencias.modo is Modo.FLEXIVEL:
            itens.append(ItemStreaming(candidato,dados,classificacao,verificado))
    if cont['candidatos_lidos']>=limites.candidatos and len(itens)<limites.tamanho and not esgotado:
        atingidos.add('CANDIDATOS')
    if ativo and tick()-inicio>=limites.segundos: atingidos.add('TEMPO')
    parcial = bool(atingidos) or (ativo and (cont['nao_verificados']>0 or cont['erros']>0))
    if not ativo:
        mensagem = 'Streaming não configurado.' if preferencias is None else 'Filtro de streaming desativado.'
    elif parcial:
        mensagem = 'Verificação parcial: outras opções podem não ter sido verificadas. Mantive suas restrições.'
    else:
        mensagem = 'Opções verificadas no conjunto de candidatos recebido; não alterei suas preferências.'
    return ResultadoStreaming(tuple(itens),preferencias is not None,ativo,parcial,
        tuple(sorted(atingidos)),cont,mensagem)
