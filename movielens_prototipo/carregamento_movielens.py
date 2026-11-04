"""Localização, aquisição e leitura dos arquivos originais do MovieLens.

Não faz limpeza, divisão, cálculo de estatísticas ou recomendação.
A raiz é recebida para preservar a configuração do ponto de entrada existente.
"""
from pathlib import Path
import hashlib
import io
import json
import ssl
import urllib.error
import urllib.request
import zipfile

import pandas as pd

URL_MOVIELENS = 'https://files.grouplens.org/datasets/movielens/ml-latest-small.zip'


def carregar_movielens(pasta=None, *, raiz, url=URL_MOVIELENS):
    pasta = Path(pasta) if pasta else raiz / 'dados' / 'ml-latest-small'
    if not all((pasta / f).exists() for f in ['ratings.csv', 'movies.csv']):
        pasta.parent.mkdir(parents=True, exist_ok=True)
        zip_local = pasta.parent / 'ml-latest-small.zip'
        if zip_local.is_file():
            print('Usando ZIP local: ' + str(zip_local), flush=True)
            arquivo = zip_local.read_bytes()
        else:
            print('Baixando MovieLens oficial...', flush=True)
            try:
                with urllib.request.urlopen(url, timeout=60) as resposta:
                    arquivo = resposta.read()
            except urllib.error.URLError as erro:
                certificado = isinstance(erro.reason, ssl.SSLCertVerificationError)
                motivo = 'O Python não conseguiu validar o certificado HTTPS.' if certificado else 'Não foi possível baixar o MovieLens: ' + str(erro.reason)
                raise RuntimeError(motivo + '\nBaixe ' + url + ' pelo navegador e salve em ' + str(zip_local) + '\nDepois execute o aplicativo novamente. Também pode extrair ratings.csv e movies.csv em ' + str(pasta) + '.') from erro
        # Salva a origem e o hash para identificar a versão usada no experimento.
        (pasta.parent / 'origem.json').write_text(json.dumps({'url': url, 'arquivo_local': str(zip_local) if zip_local.is_file() else None, 'sha256_zip': hashlib.sha256(arquivo).hexdigest()}, indent=2))
        with zipfile.ZipFile(io.BytesIO(arquivo)) as z:
            for nome in ['ratings.csv', 'movies.csv', 'tags.csv', 'links.csv', 'README.txt']:
                membro = 'ml-latest-small/' + nome
                pasta.mkdir(parents=True, exist_ok=True)
                (pasta / nome).write_bytes(z.read(membro))
    return pd.read_csv(pasta / 'ratings.csv'), pd.read_csv(pasta / 'movies.csv')
