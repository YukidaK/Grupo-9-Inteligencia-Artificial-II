"""Coordenação privada; não modifica Sessao ou o JSON público."""
from copy import deepcopy
from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class SnapshotSessao:
    dono: object
    versao: int
    dados: object


class EstadoSessao:
    def __init__(self,sessao):
        self.sessao=sessao;self.trava=threading.RLock();self.versao=0;self.ativos=0
        self._dono=object()
    def executar(self,funcao,*,mutacao=True):
        with self.trava:
            try:return deepcopy(funcao(self.sessao))
            finally:
                # Erro também pode ocorrer após mutação parcial: invalidação conservadora.
                if mutacao:self.versao+=1
    def snapshot(self):
        with self.trava:return SnapshotSessao(self._dono,self.versao,deepcopy(self.sessao))
    def aplicar(self,snapshot,funcao):
        with self.trava:
            if snapshot.dono is not self._dono or snapshot.versao!=self.versao:return False
            try:funcao(self.sessao)
            finally:self.versao+=1
            return True
