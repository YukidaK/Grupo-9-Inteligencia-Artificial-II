"""Preferências imutáveis; sem rede, cache, credencial ou dependência da sessão."""
from dataclasses import dataclass
from enum import Enum
import re


class Modo(Enum):
    RESTRITO = 'restrito'
    FLEXIVEL = 'flexivel'


@dataclass(frozen=True)
class PreferenciasStreaming:
    provedores: frozenset[int] = frozenset()
    regiao: str = 'BR'
    modo: Modo = Modo.RESTRITO
    ativo: bool = False

    def __post_init__(self):
        if not isinstance(self.regiao,str) or not re.fullmatch('[A-Z]{2}',self.regiao):
            raise ValueError('Região deve ser código de duas letras maiúsculas.')
        if not isinstance(self.provedores,frozenset) or not isinstance(self.modo,Modo):
            raise ValueError('Preferências devem usar IDs imutáveis e modo explícito.')
        if type(self.ativo) is not bool: raise ValueError('Ativação deve ser booleana explícita.')
        for i in self.provedores:
            if type(i) is not int or i<=0: raise ValueError('Provedor deve ser inteiro positivo.')
