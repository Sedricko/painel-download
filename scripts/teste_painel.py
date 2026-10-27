"""Teste sem internet: servidor local com botao de download (cookie + _token) e um form de login que deve ser ignorado.
Rodar: python teste_painel.py"""
import http.server, os, sys, tempfile, threading, types

for m in ('tkinter', 'tkinter.filedialog', 'tkinter.scrolledtext'):  # o teste nao abre janela
    sys.modules.setdefault(m, types.ModuleType(m))
sys.modules['tkinter'].filedialog, sys.modules['tkinter'].scrolledtext = sys.modules['tkinter.filedialog'], sys.modules['tkinter.scrolledtext']
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import painel_download as p

PAGINA = b'''<html><a href="/outra">outra</a><a href="/ferramenta">ferramenta</a><a href="/vip">vip</a><a href="/loja.php?a=1&amp;b=2">loja</a>
<div data-download-url="/pacotes/mod.pak"></div><!-- "/escondido/velho.dll" --><a href="/v/lista.m3u8">video</a><a href="https://fora.example/pagina">fora</a>
<script src="/sub/app.js" integrity="sha384-x"></script><img src="https://www.facebook.com/tr.gif"><a href="https://x.com/perfil">x</a><img src="https://cdn.naoquero.example/a.png">
<form action="/baixar" method="POST"><input type="hidden" name="_token" value="abc"><button type="submit"></button></form>
<form action="/login" method="POST"><input type="hidden" name="_token" value="abc"><input type="password" name="senha"></form></html>'''


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == '/vip':  # so abre com o cookie do login
            ok = 'logado=sim' in (self.headers.get('Cookie') or '')
            self.send_response(200 if ok else 403); self.end_headers()
            self.wfile.write(b'<html>area vip</html>' if ok else b'')
            return
        if self.path.split('?')[0] not in ('/', '/sitemap.xml', '/outra', '/escondida', '/ferramenta', '/sub/app.js', '/bin/tool.dll', '/s/x.ps1', '/sub/scripts/main.lua', '/cfg/jogo.json', '/pacotes/mod.pak', '/escondido/velho.dll', '/loja.php', '/v/lista.m3u8', '/v/p0.ts', '/x/item.ini', '/js_pagina.php', '/cfg/deploy/Dockerfile', '/.htaccess'):
            self.send_response(404); self.end_headers(); return
        corpo = {'/': PAGINA, '/ferramenta': b'<html><base href="/sub/"><script src="app.js"></script></html>',
                 '/sub/app.js': b'URL.createObjectURL(blob); a.href="%%23topo"; nextHref = "/cap/" + nome; d="http://127.0.0.1:%d/bin/tool.dll?v=1"; p=`http://127.0.0.1:%d/s/x.ps1`; require("scripts/main.lua"); go("/js_pagina.php"); console.log("x"); c={"u":"http:\\/\\/127.0.0.1:%d\\/cfg\\/jogo.json"}' % (porta, porta, porta), '/v/lista.m3u8': b'#EXTM3U\n#EXTINF:4,\np0.ts\n', '/cfg/jogo.json': b'{"item": "/x/item.ini", "d": "deploy/Dockerfile", "h": "/.htaccess"}', '/sitemap.xml': b'<urlset><url><loc>http://127.0.0.1:%d/escondida</loc></url></urlset>' % porta}.get(self.path, b'<html>ok</html>')
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
p.espelhar([f'http://127.0.0.1:{porta}/'], raiz, lambda m: (print(m), m.startswith('falhou') and falhas.append(m)), threading.Event(), robots=False, pausa=0, gerar_zip=False, formularios=True, cookies={f'127.0.0.1:{porta}': 'logado=sim'})
site = os.path.join(raiz, f'127.0.0.1_{porta}')
assert open(os.path.join(site, 'script.lua')).read() == 'print("oi")', 'botao de download'
assert os.path.exists(os.path.join(site, 'escondida.html')), 'sitemap'
assert os.path.exists(os.path.join(site, 'sub', 'app.js')), '<base href>'
assert '<base' not in open(os.path.join(site, 'ferramenta.html')).read(), 'base removido no espelho'
assert [f for f in os.listdir(os.path.join(site, 'bin')) if f.endswith('.dll')] and not os.path.exists(os.path.join(site, 'bin', 'tool.dll')), 'dll por endereco completo, com ?v=1, sem duplicar'
assert os.path.exists(os.path.join(site, 's', 'x.ps1')), 'qualquer formato por endereco completo'
assert open(os.path.join(site, 'vip.html')).read().endswith('<html>area vip</html>'), 'area vip com cookie de login'
for c in ('sub/scripts/main.lua', 'cfg/jogo.json', 'x/item.ini', 'pacotes/mod.pak', 'escondido/velho.dll', 'v/p0.ts', 'cfg/deploy/Dockerfile', '.htaccess'):
    assert os.path.exists(os.path.join(site, c)), 'escondido: ' + c
loja = [f for f in os.listdir(site) if f.startswith('loja_')]
assert loja and loja[0].endswith('.php.html'), 'pagina .php salva como .html (com &amp; desfeito)'
assert not falhas, falhas
mapa = open(os.path.join(raiz, 'mapa.html'), encoding='utf-8').read()
assert f'127.0.0.1_{porta}/script.lua' in mapa and f'127.0.0.1_{porta}/sub/app.js' in mapa, 'mapa com todos os arquivos'
assert f'src="127.0.0.1_{porta}/index.html"' in open(os.path.join(raiz, 'index.html'), encoding='utf-8').read(), 'inicio'
ini = open(os.path.join(site, 'index.html'), encoding='utf-8').read()
assert 'https://fora.example' not in ini and '../nao_baixado.html#https%3A%2F%2Ffora.example%2Fpagina' in ini, 'link de fora nao abre a internet'
assert 'Content-Security-Policy' in ini and 'integrity' not in ini, 'trava de rede e sem integrity'
assert 'href="http' not in mapa, 'mapa sem links para a internet'
assert [f for f in os.listdir(site) if f.startswith('js_pagina')], 'pagina citada no js, dentro da profundidade'
# profundidade 0 e saindo do dominio: so a pagina inicial e seus arquivos; rede social nunca
raiz0, log0 = os.path.join(tempfile.mkdtemp(), 'espelho'), []
p.espelhar([f'http://127.0.0.1:{porta}/'], raiz0, log0.append, threading.Event(), profundidade=0, mesmo_site=False, robots=False, pausa=0, gerar_zip=False, sitemap=False,
           bloquear=p.BLOQUEADOS | {'https://www.naoquero.example/qualquer'})
site0 = os.path.join(raiz0, f'127.0.0.1_{porta}')
assert os.path.exists(os.path.join(site0, 'sub', 'app.js')) and not os.path.exists(os.path.join(site0, 'outra.html')), 'profundidade 0'
assert not [f for f in os.listdir(site0) if f.startswith('js_pagina')], 'pagina citada no js respeita a profundidade'
assert not [d for d in os.listdir(raiz0) if 'facebook' in d or d.startswith('x.com')], 'rede social bloqueada'
assert not [m for m in log0 if 'facebook' in m or '//x.com' in m or 'naoquero' in m], log0
print('TESTE OK')
