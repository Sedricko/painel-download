"""Teste sem internet: servidor local com botao de download (cookie + _token) e um form de login que deve ser ignorado.
Rodar: python teste_painel.py"""
import http.server, os, sys, tempfile, threading, types

for m in ('tkinter', 'tkinter.filedialog', 'tkinter.scrolledtext'):  # o teste nao abre janela
    sys.modules.setdefault(m, types.ModuleType(m))
sys.modules['tkinter'].filedialog, sys.modules['tkinter'].scrolledtext = sys.modules['tkinter.filedialog'], sys.modules['tkinter.scrolledtext']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import painel_download as p

PAGINA = b'''<html><a href="/outra">outra</a><a href="/ferramenta">ferramenta</a>
<form action="/baixar" method="POST"><input type="hidden" name="_token" value="abc"><button type="submit"></button></form>
<form action="/login" method="POST"><input type="hidden" name="_token" value="abc"><input type="password" name="senha"></form></html>'''


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path not in ('/', '/sitemap.xml', '/outra', '/escondida', '/ferramenta', '/sub/app.js', '/bin/tool.dll', '/s/x.ps1'):
            self.send_response(404); self.end_headers(); return
        corpo = {'/': PAGINA, '/ferramenta': b'<html><base href="/sub/"><script src="app.js"></script></html>',
                 '/sub/app.js': b'URL.createObjectURL(blob); a.href="%%23topo"; nextHref = "/cap/" + nome; d="http://127.0.0.1:%d/bin/tool.dll?v=1"; p=`http://127.0.0.1:%d/s/x.ps1`' % (porta, porta), '/sitemap.xml': b'<urlset><url><loc>http://127.0.0.1:%d/escondida</loc></url></urlset>' % porta}.get(self.path, b'<html>ok</html>')
        self.send_response(200)
        self.send_header('Set-Cookie', 'sessao=1')
        self.end_headers()
        self.wfile.write(corpo)

    def do_POST(self):
        dados = self.rfile.read(int(self.headers['Content-Length']))
        if self.path == '/login':
            raise AssertionError('nao pode enviar form de login')
        ok = self.path == '/baixar' and dados == b'_token=abc' and 'sessao=1' in (self.headers['Cookie'] or '')
        self.send_response(200 if ok else 419)
        self.send_header('Content-Disposition', 'attachment; filename=script.lua')
        self.end_headers()
        self.wfile.write(b'print("oi")' if ok else b'')


srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
porta = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
raiz = os.path.join(tempfile.mkdtemp(), 'espelho')
falhas = []
p.espelhar([f'http://127.0.0.1:{porta}/'], raiz, lambda m: (print(m), m.startswith('falhou') and falhas.append(m)), threading.Event(), robots=False, pausa=0, gerar_zip=False, formularios=True)
site = os.path.join(raiz, f'127.0.0.1_{porta}')
assert open(os.path.join(site, 'script.lua')).read() == 'print("oi")', 'botao de download'
assert os.path.exists(os.path.join(site, 'escondida.html')), 'sitemap'
assert os.path.exists(os.path.join(site, 'sub', 'app.js')), '<base href>'
assert '<base' not in open(os.path.join(site, 'ferramenta.html')).read(), 'base removido no espelho'
assert os.path.exists(os.path.join(site, 'bin', 'tool.dll')), 'dll por endereco completo'
assert os.path.exists(os.path.join(site, 's', 'x.ps1')), 'qualquer formato por endereco completo'
assert not falhas, falhas
mapa = open(os.path.join(raiz, 'mapa.html'), encoding='utf-8').read()
assert f'127.0.0.1_{porta}/script.lua' in mapa and f'127.0.0.1_{porta}/sub/app.js' in mapa, 'mapa com todos os arquivos'
assert f'src="127.0.0.1_{porta}/index.html"' in open(os.path.join(raiz, 'index.html'), encoding='utf-8').read(), 'inicio'
print('TESTE OK')
