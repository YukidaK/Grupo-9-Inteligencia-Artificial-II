"""Transporte compartilhado do piloto, somente respostas sintéticas."""
import io
import json
import unittest
from unittest.mock import Mock, patch
from transporte_tmdb import TransporteTMDB, FalhaConsulta
from piloto_titulos import TransporteTraducoesTMDB
TOKEN = 'CREDENCIAL_SINTETICA_SOMENTE_TESTE'

class Resposta:
    def __init__(self,url,dados,*,status=200,headers=None,bruto=None):
        self.url,self.status = url,status
        self.headers = {'Content-Type':'application/json; charset=utf-8',**(headers or {})}
        self.corpo = io.BytesIO(json.dumps(dados).encode() if bruto is None else bruto)
        self.fechada = False
    def __enter__(self): return self
    def __exit__(self,*a): self.fechada=True
    def geturl(self): return self.url
    def read(self,n): return self.corpo.read(n)

class TransporteTests(unittest.TestCase):
    def test_timeout_e_orcamento_compartilhado(self):
        from operacao_externa import ControleExterno, Prazo, usar_prazo
        import time
        abrir = Mock()
        with patch.dict('os.environ', {'TMDB_READ_ACCESS_TOKEN': TOKEN}):
            c = TransporteTraducoesTMDB([100], abrir=abrir, habilitado=True, termos_aprovados=True)
        with usar_prazo(Prazo(time.monotonic(), 0)), self.assertRaises(FalhaConsulta):
            c.consultar_traducoes(100)
        abrir.assert_not_called()
