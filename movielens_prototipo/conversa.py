"""Seleção de referências por sessão e geração inicial de sugestões."""
from dataclasses import dataclass, field


@dataclass
class Sessao:
    assistidos: list = field(default_factory=list)
    referencias: list = field(default_factory=list)
    # Campos de compatibilidade do algoritmo e dos experimentos históricos.
    # O fluxo público essencial sempre os mantém vazios.
    rejeitados: set = field(default_factory=set)
    positivos: set = field(default_factory=set)
    negativos: set = field(default_factory=set)
    recomendacoes: list = field(default_factory=list)


class Conversa:
    """Nome legado preservado para o controlador de seleção usado pela API."""
    def __init__(self, modelo):
        self.modelo = modelo
        self.filmes = modelo.filmes.set_index('movieId', drop=False).rename_axis('catalogo_id')

    def filme(self, movie_id):
        f = self.filmes.loc[movie_id]
        return {'movieId': int(movie_id), 'titulo': f.title,
                'ano': int(f.ano) if str(f.ano) not in ('<NA>', 'nan') else None,
                'generos': f.genres}

    def resposta(self, sessao, mensagem):
        n = len(sessao.referencias)
        if not n:
            sessao.recomendacoes = []
            mensagem += ' Selecione pelo menos um filme para receber recomendações.'
        elif n <= 2:
            mensagem += (' Fornecer mais filmes, até cinco referências, pode ajudar a identificar'
                         ' melhor suas preferências, sem garantir maior precisão.')
        return {'mensagem': mensagem,
                'assistidos': [self.filme(i) for i in sessao.assistidos],
                'referencias': [self.filme(i) for i in sessao.referencias],
                'recomendacoes': sessao.recomendacoes}

    def executar(self, sessao, dados):
        acao = dados.get('acao', 'estado')
        permitidos = {'acao', 'ids'} if acao == 'confirmar_selecao' else {'acao'}
        if set(dados) - permitidos:
            raise ValueError('Pedido de seleção inválido.')
        if acao == 'estado':
            return self.resposta(sessao, 'Busque e confirme de um a cinco filmes.')
        if acao == 'reiniciar':
            sessao.__dict__.update(Sessao().__dict__)
            return self.resposta(sessao, 'Comece uma nova seleção.')
        if acao != 'confirmar_selecao':
            raise ValueError('Ação de seleção desconhecida.')
        ids = dados.get('ids')
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 5
                or any(type(i) is not int or i not in self.filmes.index for i in ids)):
            raise ValueError('Selecione de um a cinco filmes válidos e confira o ano.')
        referencias = list(dict.fromkeys(ids))
        # Calcula antes de publicar a seleção, preservando o estado em caso de falha.
        novos = Sessao(assistidos=list(dict.fromkeys(sessao.assistidos + referencias)),
                       referencias=referencias)
        recomendacoes = self.modelo.recomendar_perfil(novos)
        sessao.__dict__.update(novos.__dict__)
        sessao.recomendacoes = recomendacoes
        msg = 'Seleção confirmada.'
        if len(recomendacoes) < 10:
            msg += f' Há {len(recomendacoes)} sugestões para esta seleção.'
        return self.resposta(sessao, msg)
