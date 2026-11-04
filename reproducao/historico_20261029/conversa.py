"""Interpretação local limitada, catálogo e estado explícito por sessão."""
from dataclasses import dataclass, field
import re
from recomendador import normalizar, interpretar


@dataclass
class Sessao:
    assistidos: list = field(default_factory=list)
    referencias: list = field(default_factory=list)
    rejeitados: set = field(default_factory=set)
    positivos: set = field(default_factory=set)
    negativos: set = field(default_factory=set)
    recomendacoes: list = field(default_factory=list)
    pendentes: set = field(default_factory=set)


def interpretar_mensagem(texto):
    """Gramática deliberadamente restrita; nunca infere títulos ou IDs."""
    t = normalizar(texto.strip()).rstrip('.!?')
    if t == 'limpar minhas preferencias':
        return ('limpar', None)
    if t.startswith('por que'):
        return ('explicar', re.sub(r'^por que (?:voce recomendou )?', '', t).strip())
    for prefixo, acao in [('assisti ', 'assistiu'), ('quero considerar ', 'considerar')]:
        if t.startswith(prefixo):
            alvo = t[len(prefixo):]
            rejeita = bool(re.search(r',? mas nao gostei$', alvo))
            alvo = re.sub(r',? mas nao gostei$', '', alvo).strip()
            return (acao, (alvo, rejeita))
    # Cada oração precisa ter uma intenção explícita. Negação nunca vira positivo.
    partes = re.split(r'\s*(?:[;.!]|\s+e\s+(?=nao gosto|quero|prefiro|gosto))\s*', t)
    preferencias = []
    for parte in partes:
        if not parte:
            continue
        m = re.fullmatch(r'(nao gosto de|quero evitar|sem|quero mais|quero|prefiro|gosto de)\s+(.+)', parte)
        if not m:
            return ('desconhecida', None)
        generos = interpretar(m[2])
        # Rejeita qualificadores que o parser não sabe respeitar ("só", "sem", anos…).
        from recomendador import VOCAB
        sobra = re.sub(r'[^a-z0-9 ]', ' ', m[2])
        for palavra in sorted({p for vs in VOCAB.values() for p in vs}, key=len, reverse=True):
            sobra = re.sub(r'\b' + re.escape(palavra) + r'\b', ' ', sobra)
        sobra = re.sub(r'\b(e|de|com)\b', ' ', sobra)
        if not generos or sobra.strip():
            return ('desconhecida', None)
        preferencias.append((m[1] in ('nao gosto de', 'quero evitar', 'sem'), generos))
    return ('preferencias', preferencias) if preferencias else ('desconhecida', None)


class Conversa:
    def __init__(self, modelo):
        self.modelo = modelo
        self.filmes = modelo.filmes.set_index('movieId', drop=False).rename_axis('catalogo_id')

    def filme(self, movie_id):
        f = self.filmes.loc[movie_id]
        return {'movieId': int(movie_id), 'titulo': f.title,
                'ano': int(f.ano) if str(f.ano) not in ('<NA>', 'nan') else None,
                'generos': f.genres}

    def buscar(self, consulta):
        q = normalizar(consulta.strip())
        if not q:
            return []
        titulos = self.filmes.title.map(normalizar)
        # Ano omitido não desfaz a ambiguidade de remakes.
        exato = titulos.str.replace(r'\s*\(\d{4}\)\s*$', '', regex=True).eq(q) | titulos.eq(q)
        achados = self.filmes[exato]
        if achados.empty:
            achados = self.filmes[titulos.str.contains(q, regex=False)]
        return [self.filme(i) for i in achados.sort_values(['title', 'movieId']).index[:30]]

    def resposta(self, s, mensagem):
        quantidade = len(s.referencias)
        if quantidade == 0:
            # Também protege respostas de estado/busca/comandos desconhecidos
            # contra listas em cache quando não há mais referências ativas.
            s.recomendacoes = []
            mensagem += ' Selecione pelo menos um filme como referência ativa para receber recomendações.'
        elif quantidade <= 2:
            rotulo = 'referência ativa' if quantidade == 1 else 'referências ativas'
            mensagem += (f' Com {quantidade} {rotulo}, o perfil pode ficar abrangente.'
                         ' Fornecer mais filmes, até cinco referências, pode ajudar a identificar'
                         ' melhor suas preferências, sem garantir maior precisão.')
        return {'mensagem': mensagem, 'assistidos': [self.filme(i) for i in s.assistidos],
                'referencias': [self.filme(i) for i in s.referencias],
                'excedentes': [self.filme(i) for i in s.assistidos if i not in s.referencias and i not in s.rejeitados],
                'rejeitados': [self.filme(i) for i in s.assistidos if i in s.rejeitados],
                'preferencias': {'positivas': sorted(s.positivos), 'negativas': sorted(s.negativos)},
                'recomendacoes': s.recomendacoes}

    def atualizar(self, s):
        s.recomendacoes = self.modelo.recomendar_perfil(s)
        if not s.referencias:
            return ''  # resposta() fornece a orientação, sem alegar falta de candidatos.
        return (' Há apenas ' + str(len(s.recomendacoes)) + ' candidatos adequados; mantive suas restrições.') if len(s.recomendacoes) < 10 else ''

    def considerar(self, s, movie_id, substituir=None):
        if type(movie_id) is not int or movie_id not in s.assistidos:
            raise ValueError('Adicione e confirme esse filme primeiro.')
        if movie_id in s.rejeitados:
            raise ValueError('Esse filme foi rejeitado. Ele permanece apenas no histórico.')
        if movie_id in s.referencias:
            return 'Esse filme já é uma referência ativa.'
        if len(s.referencias) >= 5:
            if substituir not in s.referencias:
                return 'Escolha no controle de referências qual dos cinco filmes substituir.'
            s.referencias[s.referencias.index(substituir)] = movie_id
        else:
            s.referencias.append(movie_id)
        return 'Referências atualizadas.' + self.atualizar(s)

    def executar(self, s, dados):
        acao = dados.get('acao', 'mensagem')
        if acao == 'reiniciar':
            s.__dict__.update(Sessao().__dict__)
            return self.resposta(s, 'Quais filmes você já assistiu? Busque e confirme de 1 a 5 referências.')
        if acao == 'estado':
            return self.resposta(s, 'Quais filmes você já assistiu? Busque os títulos e confirme a seleção.' if not s.assistidos else 'Sua sessão foi mantida.')
        if acao == 'buscar':
            texto = dados.get('texto', '')
            if not isinstance(texto, str) or not 0 < len(texto) <= 2000:
                raise ValueError('Informe títulos separados por ponto e vírgula ou uma linha por título.')
            consultas = [p.strip() for p in re.split(r'[;\n]', texto) if p.strip()]
            buscas = [{'consulta': q, 'opcoes': self.buscar(q)} for q in consultas]
            s.pendentes = {f['movieId'] for b in buscas for f in b['opcoes']}
            d = self.resposta(s, 'Revise os títulos e anos antes de confirmar. Se não encontrar, tente parte do título em inglês. Cada busca mostra até 30 opções; acrescente o ano para restringir.')
            d['buscas'] = buscas
            return d
        if acao in ('confirmar', 'confirmar_selecao'):
            ids = dados.get('ids')
            permitidos = s.pendentes if acao == 'confirmar' else self.filmes.index
            if not isinstance(ids, list) or not ids or any(type(i) is not int or i not in permitidos for i in ids):
                raise ValueError('Selecione pelo menos um filme da busca atual e confirme o ano.')
            novos = list(dict.fromkeys(ids))
            inicial = not s.assistidos
            for i in novos:
                if i not in s.assistidos:
                    s.assistidos.append(i)
                    if len(s.referencias) < 5:
                        s.referencias.append(i)
            s.pendentes.clear()
            msg = 'Filmes confirmados. Os títulos são referências provisórias, sem presumir que você gostou. Você pode dizer “assisti TÍTULO, mas não gostei”.' if inicial else 'Histórico atualizado. Os novos filmes preencheram as referências disponíveis, até cinco; os demais podem ser considerados pelos controles.'
            if len(s.assistidos) > 5:
                msg += (' Os filmes usados estão em “Referências ativas”. Os demais não rejeitados'
                        ' estão em “Assistidos fora do perfil”, apenas no histórico e também'
                        ' excluídos das sugestões; você pode considerar um deles.')
            return self.resposta(s, msg + self.atualizar(s))
        if acao == 'considerar':
            return self.resposta(s, self.considerar(s, dados.get('movieId'), dados.get('substituir')))
        if acao == 'rejeitar':
            i = dados.get('movieId')
            if type(i) is not int or i not in self.filmes.index:
                raise ValueError('Selecione um filme válido.')
            if i not in s.assistidos:
                s.assistidos.append(i)
            s.rejeitados.add(i)
            if i in s.referencias:
                s.referencias.remove(i)
            return self.resposta(s, 'Retirei o filme das referências. Ele continua no histórico e não será recomendado.' + self.atualizar(s))
        if acao != 'mensagem':
            raise ValueError('Ação desconhecida.')
        texto = dados.get('texto', '')
        if not isinstance(texto, str) or not 0 < len(texto.strip()) <= 2000:
            raise ValueError('Escreva uma mensagem de até 2000 caracteres.')
        if not s.assistidos:
            return self.resposta(s, 'Para começar, busque e confirme pelo menos um filme assistido. Pode estar registrado em inglês no catálogo.')
        intencao, valor = interpretar_mensagem(texto)
        if intencao == 'limpar':
            s.positivos.clear(); s.negativos.clear()
            return self.resposta(s, 'Preferências de gêneros limpas; histórico, referências e rejeições mantidos.' + self.atualizar(s))
        if intencao == 'preferencias':
            for negativo, generos in valor:
                destino, outro = (s.negativos, s.positivos) if negativo else (s.positivos, s.negativos)
                destino.update(generos); outro.difference_update(generos)
            return self.resposta(s, 'Preferências atualizadas. Gêneros rejeitados são excluídos.' + self.atualizar(s))
        if intencao in ('assistiu', 'considerar'):
            alvo, rejeita = valor
            filmes = self.buscar(alvo)
            # Conversa exige título exato e único. Partial só com revisão visual.
            exatos = [f for f in filmes if normalizar(f['titulo']) == alvo or re.sub(r'\s*\(\d{4}\)$', '', normalizar(f['titulo'])) == alvo]
            if len(exatos) != 1:
                return self.resposta(s, 'Não identifiquei um título único. Use “Adicionar filmes” para buscar, revisar o ano e confirmar; suas recomendações foram mantidas.')
            i = exatos[0]['movieId']
            if intencao == 'considerar':
                return self.resposta(s, self.considerar(s, i))
            if rejeita:
                return self.executar(s, {'acao': 'rejeitar', 'movieId': i})
            if i not in s.assistidos:
                s.assistidos.append(i)
            return self.resposta(s, 'Adicionei ao histórico. Para usar como referência, escolha “Considerar”.' + self.atualizar(s))
        if intencao == 'explicar':
            alvo = valor
            if alvo in ('esse', 'esse filme', 'isso'):
                return self.resposta(s, 'Indique o título ou a posição (1 a 10), por exemplo: “Por que 1?”.')
            rec = [f for n, f in enumerate(s.recomendacoes, 1) if alvo == str(n) or normalizar(f['titulo']) == alvo or re.sub(r'\s*\(\d{4}\)$', '', normalizar(f['titulo'])) == alvo]
            return self.resposta(s, rec[0]['titulo'] + ': ' + rec[0]['motivo'] if len(rec) == 1 else 'Indique o título com ano ou a posição na lista atual, como “Por que 1?”.')
        return self.resposta(s, 'Não entendi esse comando no modo local. Tente “Quero mais suspense”, “Não gosto de terror”, “Prefiro ficção científica”, “Por que 1?” ou “Limpar minhas preferências”. Para escolher aquele outro filme, use “Considerar” na lista. Mantive seu perfil e suas sugestões.')
