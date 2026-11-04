"""Identidades de domínio, independentes de pandas, HTTP e persistência.

O namespace da fonte não é uma URL nem o UUID de uma execução. Não há
correspondência automática entre obras, mesmo quando seus metadados coincidem.
"""
from dataclasses import dataclass
from enum import Enum
from numbers import Integral
import re

FONTE_MOVIELENS = 'movielens'


class TipoConteudo(Enum):
    FILME = 'FILME'
    SERIE = 'SERIE'  # Reservado no contrato; não habilita catálogo/recomendação.


def _validar_fonte(fonte):
    if not isinstance(fonte, str) or not re.fullmatch(r'[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*', fonte):
        raise ValueError('Fonte deve ser um namespace minúsculo, sem espaços ou URL.')


def _validar_id_original(identificador):
    if (not isinstance(identificador, str) or not identificador
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in identificador)):
        raise ValueError('Identificador original deve ser texto não vazio, sem espaços ou controles.')


@dataclass(frozen=True)
class IdentidadeConteudo:
    fonte: str
    tipo: TipoConteudo
    id_original: str

    def __post_init__(self):
        _validar_fonte(self.fonte)
        if not isinstance(self.tipo, TipoConteudo):
            raise ValueError('Tipo deve ser um membro de TipoConteudo.')
        _validar_id_original(self.id_original)


@dataclass(frozen=True)
class IdentidadeUsuario:
    """Usuário histórico de uma fonte; nunca representa cookie de visitante."""
    fonte: str
    id_original: str

    def __post_init__(self):
        _validar_fonte(self.fonte)
        _validar_id_original(self.id_original)


def _inteiro_movielens(valor):
    # bool é Integral em Python, mas não é um ID válido. Floats e textos não
    # são coercidos: a coerção apagaria diferenças como as de 1, True e 1.5.
    if isinstance(valor, bool) or not isinstance(valor, Integral) or valor <= 0:
        raise ValueError('ID MovieLens deve ser inteiro positivo, sem coerção implícita.')
    return str(int(valor))


def conteudo_movielens(movie_id):
    return IdentidadeConteudo(FONTE_MOVIELENS, TipoConteudo.FILME, _inteiro_movielens(movie_id))


def usuario_movielens(user_id):
    return IdentidadeUsuario(FONTE_MOVIELENS, _inteiro_movielens(user_id))


def _original_movielens(identificador):
    if not re.fullmatch(r'[1-9][0-9]*', identificador):
        raise ValueError('ID original MovieLens deve ser decimal canônico, sem zeros à esquerda.')
    return int(identificador)


def movie_id_legado(identidade):
    if (not isinstance(identidade, IdentidadeConteudo)
            or identidade.fonte != FONTE_MOVIELENS or identidade.tipo is not TipoConteudo.FILME):
        raise ValueError('Somente conteúdo FILME da fonte MovieLens possui movieId legado.')
    return _original_movielens(identidade.id_original)


def user_id_legado(identidade):
    if not isinstance(identidade, IdentidadeUsuario) or identidade.fonte != FONTE_MOVIELENS:
        raise ValueError('Somente usuário histórico MovieLens possui userId legado.')
    return _original_movielens(identidade.id_original)
