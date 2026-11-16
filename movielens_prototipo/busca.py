"""Autocomplete local, determinístico. Nenhuma chamada a serviços externos."""
from difflib import SequenceMatcher
import re
from recomendador import normalizar


def chave(texto):
    return ' '.join(re.sub(r'[^\w\s]', ' ', normalizar(texto)).split())


class BuscaCatalogo:
    def __init__(self, filmes, aliases=None):
        aliases = aliases or {}
        self.itens = []
        for f in filmes.drop_duplicates('movieId').itertuples():
            titulo = f.title
            ano = re.search(r'\((\d{4})\)\s*$', titulo)
            sem_ano = re.sub(r'\s*\(\d{4}\)\s*$', '', titulo)
            # Nomes alternativos já presentes no MovieLens; não cria traduções.
            nomes = [titulo, sem_ano, re.sub(r'\([^)]*\)', '', sem_ano).strip()]
            nomes += [re.sub(r'^a\.k\.a\.\s*', '', n, flags=re.I) for n in re.findall(r'\(([^)]+)\)', sem_ano)]
            extra = aliases.get(int(f.movieId))
            if extra:
                nomes += [extra['titulo_br'], *extra['alternativos']]
            variantes = set()
            for nome in nomes:
                variantes.add(chave(nome))
                artigo = re.match(r'(.+),\s*(The|A|An|Le|La|Les|El|Los|Las|O|Os|As)\s*$', nome, re.I)
                if artigo:
                    variantes.add(chave(artigo[2] + ' ' + artigo[1]))
                    variantes.add(chave(artigo[1]))
            exibicao = {}
            if extra:
                exibicao = {'titulo_br': extra['titulo_br'] + (f' ({ano[1]})' if ano else ''),
                            'titulo_original': titulo}
            self.itens.append(({**exibicao, 'movieId': int(f.movieId), 'titulo': titulo,
                                'ano': int(ano[1]) if ano else None, 'generos': f.genres},
                               sorted(v for v in variantes if v)))

    def buscar(self, consulta, limite=8):
        if not isinstance(consulta, str):
            raise ValueError('Informe um título.')
        if len(consulta) > 200:
            raise ValueError('Use até 200 caracteres na busca.')
        if len(consulta.strip()) < 2:
            return []
        ano = re.search(r'\((\d{4})\)\s*$', consulta)
        ano_busca = int(ano[1]) if ano else None
        q = chave(consulta[:ano.start()] if ano else consulta)
        if len(q) < 2:
            return []
        diretos, aproximados, restantes = [], [], []
        for filme, nomes in self.itens:
            if ano_busca is not None and filme['ano'] != ano_busca:
                continue
            tipo = min((0 if q == n else 1 if n.startswith(q) else 2 if q in n else 3 for n in nomes), default=3)
            if tipo < 3:
                diretos.append((tipo, 0, 0, filme['titulo'].casefold(), filme['movieId'], filme))
            else:
                restantes.append((filme, nomes))
        if len(diretos) < limite and len(q) >= 5:
            for filme, nomes in restantes:
                # Compare nomes e janelas de palavras, nunca subsequências soltas.
                tamanho = len(q.split())
                candidatos = set(nomes)
                for n in nomes:
                    palavras = n.split()
                    candidatos.update(' '.join(palavras[i:i+tamanho]) for i in range(len(palavras)-tamanho+1))
                score = max((SequenceMatcher(None, q, n, autojunk=False).ratio() for n in candidatos
                             if abs(len(n)-len(q)) <= max(2, len(q)//5)), default=0)
                if score >= .85:
                    aproximados.append((3, -score, min(abs(len(n)-len(q)) for n in nomes), filme['titulo'].casefold(), filme['movieId'], filme))
        return [dict(f, correspondencia=('aproximada' if tipo == 3 else 'catalogo'))
                for tipo, _, _, _, _, f in sorted(diretos + aproximados)[:max(0, min(8, limite))]]
