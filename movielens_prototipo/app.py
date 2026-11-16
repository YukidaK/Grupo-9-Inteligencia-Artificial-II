"""Servidor local com sessões isoladas por cookie; sem serviços pagos."""
import json
import re
import secrets
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from recomendador import carregar_modelo
from conversa import Conversa, Sessao
from posteres import Posteres, PLACEHOLDER, carregar_links
from titulos_alternativos import carregar_aliases
from busca import BuscaCatalogo
from estado_sessao import EstadoSessao
from operacao_externa import TravaRegistro


class Handler(BaseHTTPRequestHandler):
    modelo = None
    posteres = None
    busca = None
    busca_modelo = None
    sessoes = {}
    trava = TravaRegistro()
    _estados = {}

    def _sessao_atual(self):
        """Chamar sob trava; preserva cookie e expiração anteriores."""
        cookie = SimpleCookie()
        cookie.load(self.headers.get('Cookie', ''))
        sid = cookie['cinematch'].value if 'cinematch' in cookie else None
        agora = time.monotonic()
        for chave, (_, instante) in list(self.sessoes.items()):
            if agora - instante > 7200 and not getattr(self._estados.get(chave),'ativos',0):
                del self.sessoes[chave]
        for chave in list(self._estados):
            if chave not in self.sessoes and not self._estados[chave].ativos:del self._estados[chave]
        if sid not in self.sessoes:
            sid = secrets.token_urlsafe(32)
            self.novo_cookie = sid
            self.sessoes[sid] = (Sessao(), agora)
        return sid,self.sessoes[sid][0],agora

    def responder(self, status, conteudo, tipo):
        self.send_response(status)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(conteudo)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        if getattr(self, 'novo_cookie', None):
            self.send_header('Set-Cookie', 'cinematch=' + self.novo_cookie + '; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(conteudo)

    def do_GET(self):
        caminho = urlparse(self.path).path
        if caminho == '/':
            self.responder(200, Path(__file__).with_name('index.html').read_bytes(), 'text/html; charset=utf-8')
        elif caminho == '/api/filmes':
            try:
                consulta = parse_qs(urlparse(self.path).query).get('q', [''])[0]
                with self.trava:
                    if self.busca_modelo is not self.modelo:
                        links = carregar_links(Path(__file__).with_name('dados') / 'ml-latest-small' / 'links.csv')
                        aliases = carregar_aliases(self.modelo.filmes, links)
                        type(self).busca = BuscaCatalogo(self.modelo.filmes, aliases)
                        type(self).busca_modelo = self.modelo
                    busca = self.busca
                resultado = busca.buscar(consulta)
                self.responder(200, json.dumps({'sugestoes': resultado}, ensure_ascii=False).encode(), 'application/json; charset=utf-8')
            except ValueError as erro:
                self.responder(400, json.dumps({'erro': str(erro)}).encode(), 'application/json; charset=utf-8')
        elif caminho == '/static/autocomplete.js':
            self.responder(200, Path(__file__).with_name('static').joinpath(caminho.rsplit('/',1)[1]).read_bytes(), 'text/javascript; charset=utf-8')
        elif caminho == PLACEHOLDER:
            self.responder(200, Path(__file__).with_name('static').joinpath('poster-placeholder.svg').read_bytes(), 'image/svg+xml')
        elif re.fullmatch(r'/api/poster/[1-9][0-9]{0,9}', caminho):
            movie_id = int(caminho.rsplit('/', 1)[1])
            if self.modelo is None or movie_id not in set(self.modelo.filmes.movieId):
                self.responder(404, b'{}', 'application/json')
                return
            dados = self.posteres.obter(movie_id) if self.posteres else {'poster_url': PLACEHOLDER, 'thumbnail_url': PLACEHOLDER, 'tmdbId': None}
            self.responder(200, json.dumps(dados).encode(), 'application/json; charset=utf-8')
        else:
            self.responder(404, b'Nao encontrado', 'text/plain; charset=utf-8')

    def do_POST(self):
        if self.path != '/api/recomendar':
            self.responder(404, b'{}', 'application/json')
            return
        try:
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                raise ValueError('Origem da requisição inválida.')
            tamanho = int(self.headers.get('Content-Length', '0'))
            if not 0 < tamanho <= 10000:
                raise ValueError('Pedido muito grande ou vazio.')
            dados = json.loads(self.rfile.read(tamanho))
            if not isinstance(dados, dict):
                raise ValueError('Envie um objeto JSON.')
            with self.trava:
                sid,sessao,agora = self._sessao_atual()
                estado=self._estados.get(sid)
                if estado is None or estado.sessao is not sessao:
                    estado=EstadoSessao(sessao);self._estados[sid]=estado
                estado.ativos+=1
            try:
                resposta=estado.executar(lambda s:Conversa(self.modelo).executar(s,dados),
                    mutacao=dados.get('acao')!='estado')
            finally:
                with self.trava:
                    estado.ativos-=1
                    self.sessoes[sid]=(sessao,time.monotonic())
            self.responder(200, json.dumps(resposta, ensure_ascii=False).encode(), 'application/json; charset=utf-8')
        except (ValueError, TypeError, OverflowError) as erro:
            self.responder(400, json.dumps({'erro': str(erro)}, ensure_ascii=False).encode(), 'application/json; charset=utf-8')


if __name__ == '__main__':
    try:
        Handler.modelo = carregar_modelo()
    except RuntimeError as erro:
        raise SystemExit(str(erro)) from None
    Handler.posteres = Posteres.do_ambiente()
    try:
        servidor = ThreadingHTTPServer(('127.0.0.1', 8000), Handler)
        print('Abra http://127.0.0.1:8000 — Ctrl+C encerra.', flush=True)
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
