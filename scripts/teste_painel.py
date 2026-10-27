"""Teste sem internet: servidor local com botao de download (cookie + _token) e um form de login que deve ser ignorado.
Rodar: python teste_painel.py"""
import http.server, os, sys, tempfile, threading, types

for m in ('tkinter', 'tkinter.filedialog', 'tkinter.scrolledtext', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.simpledialog'):  # o teste nao abre janela
    sys.modules.setdefault(m, types.ModuleType(m))
for m in ('filedialog', 'scrolledtext', 'ttk', 'messagebox', 'simpledialog'):
    setattr(sys.modules['tkinter'], m, sys.modules['tkinter.' + m])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import painel_download as p

PAGINA = b'''<html><a href="/outra">outra</a><a href="/ferramenta">ferramenta</a><a href="/vip">vip</a><a href="/loja.php?a=1&amp;b=2">loja</a>
<div data-download-url="/pacotes/mod.pak"></div><!-- "/escondido/velho.dll" --><a href="/v/lista.m3u8">video</a><a href="https://fora.example/pagina">fora</a>
<script src="/sub/app.js" integrity="sha384-x"></script>
<link rel="stylesheet" href="http://localhost:PORTA/cdn/css2?family=X"><link rel="preconnect" href="https://fonts.gstatic.com"><a href="http://localhost:PORTA/fora.html">pagina de outro site</a><a href="/index.html">inicio de novo</a><a href="/privado/x.html">privado</a><img src="https://www.facebook.com/tr.gif"><a href="https://x.com/perfil">x</a><img src="https://cdn.naoquero.example/a.png"><script src="https://analytics.contador.example/script.js"></script>
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
        if self.path == '/robots.txt':  # como Cloudflare: recusa o leitor padrao do Python
            ok = 'Python-urllib' not in (self.headers.get('User-Agent') or '')
            self.send_response(200 if ok else 403); self.end_headers()
            self.wfile.write(b'User-agent: *\nDisallow: /privado/\n' if ok else b'')
            return
        if self.headers['Host'].startswith('localhost'):  # 'outro site' (CDN)
            if self.path == '/fora.html':
                raise AssertionError('nao podia seguir pagina de outro site')
            self.send_response(200); self.send_header('Content-Type', 'text/css' if 'css' in self.path else 'font/woff2'); self.end_headers()
            self.wfile.write(b'@font-face{src:url(fonte.woff2)}' if 'css' in self.path else b'wOF2')
            return
        if self.path.split('?')[0] not in ('/', '/sitemap.xml', '/outra', '/escondida', '/ferramenta', '/sub/app.js', '/bin/tool.dll', '/s/x.ps1', '/sub/scripts/main.lua', '/cfg/jogo.json', '/pacotes/mod.pak', '/escondido/velho.dll', '/loja.php', '/v/lista.m3u8', '/v/p0.ts', '/x/item.ini', '/js_pagina.php', '/index.html', '/cfg/deploy/Dockerfile', '/.htaccess'):
            self.send_response(404); self.end_headers(); return
        corpo = {'/': PAGINA.replace(b'PORTA', str(porta).encode()), '/index.html': PAGINA.replace(b'PORTA', str(porta).encode()), '/ferramenta': b'<html><base href="/sub/"><script src="app.js"></script></html>',
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
p.espelhar([f'http://127.0.0.1:{porta}/'], raiz, lambda m: (print(m), m.startswith('falhou') and falhas.append(m)), threading.Event(), robots=True, pausa=0, gerar_zip=False, formularios=True, bloquear=p.BLOQUEADOS | {'naoquero.example'}, cookies={f'127.0.0.1:{porta}': 'logado=sim'})
site = os.path.join(raiz, f'127.0.0.1_{porta}')
assert open(os.path.join(site, 'script.lua')).read() == 'print("oi")', 'botao de download'
assert os.path.exists(os.path.join(site, 'escondida.html')), 'sitemap'
assert os.path.exists(os.path.join(site, 'sub', 'app.js')), '<base href>'
assert '<base' not in open(os.path.join(site, 'ferramenta.html')).read(), 'base removido no espelho'
assert os.listdir(os.path.join(site, 'bin')) == ['tool.dll'], 'dll por endereco completo; ?v=1 nao duplica'
assert os.path.exists(os.path.join(site, 's', 'x.ps1')), 'qualquer formato por endereco completo'
assert open(os.path.join(site, 'vip.html')).read().endswith('<html>area vip</html>'), 'area vip com cookie de login'
for c in ('sub/scripts/main.lua', 'cfg/jogo.json', 'x/item.ini', 'pacotes/mod.pak', 'escondido/velho.dll', 'v/p0.ts', 'cfg/deploy/Dockerfile', '.htaccess'):
    assert os.path.exists(os.path.join(site, c)), 'escondido: ' + c
loja = [f for f in os.listdir(site) if f.startswith('loja_')]
assert loja and loja[0].endswith('.php.html'), 'pagina .php salva como .html (com &amp; desfeito)'
assert not falhas, falhas
mapa = open(os.path.join(raiz, 'mapa.html'), encoding='utf-8').read()
assert f'127.0.0.1_{porta}/script.lua' in mapa and f'127.0.0.1_{porta}/sub/app.js' in mapa, 'mapa com todos os arquivos'
assert f'url=127.0.0.1_{porta}/index.html' in open(os.path.join(raiz, 'index.html'), encoding='utf-8').read(), 'inicio em tela cheia'
pasta = os.path.dirname(raiz)
for atalho in ('Abrir site.html', 'Esqueleto do site.html', 'Abrir site completo.bat'):
    assert os.path.exists(os.path.join(pasta, atalho)), 'atalho ' + atalho
assert '.painel' not in mapa and 'data-g="Código"' in mapa, 'esqueleto sem a pasta interna, com tipos'
ini = open(os.path.join(site, 'index.html'), encoding='utf-8').read()
assert 'https://fora.example' not in ini and '../nao_baixado.html#https%3A%2F%2Ffora.example%2Fpagina' in ini, 'link de fora nao abre a internet'
assert 'Content-Security-Policy' in ini and 'integrity' not in ini, 'trava de rede e sem integrity'
assert 'href="http' not in mapa.split('class="nao"')[0], 'arvore do esqueleto sem links para a internet (so a secao Nao copiados tem)'
assert [f for f in os.listdir(site) if f.startswith('js_pagina')], 'pagina citada no js, dentro da profundidade'
# profundidade 0 e saindo do dominio: so a pagina inicial e seus arquivos; rede social nunca
raiz0, log0 = os.path.join(tempfile.mkdtemp(), 'espelho'), []
p.espelhar([f'http://127.0.0.1:{porta}/'], raiz0, log0.append, threading.Event(), profundidade=0, mesmo_site=False, robots=False, pausa=0, gerar_zip=False, sitemap=False,
           bloquear=p.BLOQUEADOS | {'https://www.naoquero.example/qualquer'})
site0 = os.path.join(raiz0, f'127.0.0.1_{porta}')
assert os.path.exists(os.path.join(site0, 'sub', 'app.js')) and not os.path.exists(os.path.join(site0, 'outra.html')), 'profundidade 0'
assert not [f for f in os.listdir(site0) if f.startswith('js_pagina')], 'pagina citada no js respeita a profundidade'
assert not [d for d in os.listdir(raiz0) if 'facebook' in d or d.startswith('x.com')], 'rede social bloqueada'
assert not [m for m in log0 if 'facebook' in m or '//x.com' in m or 'naoquero' in m or 'contador' in m], log0
cdn = os.path.join(raiz, f'localhost_{porta}', 'cdn')
assert os.path.exists(os.path.join(cdn, 'fonte.woff2')) and [f for f in os.listdir(cdn) if f.endswith('.css')], 'arquivos da pagina vindos de outro site (CDN)'
assert '.css' in open(os.path.join(site, 'index.html'), encoding='utf-8').read().split('localhost_')[1][:60], 'pagina aponta para o .css local'
assert not os.path.exists(os.path.join(site, 'privado')), 'robots.txt respeitado (lido com o nome do painel)'
assert os.path.exists(os.path.join(site, 'robots.txt')) and os.path.exists(os.path.join(site, 'sitemap.xml')), 'robots.txt e sitemap.xml salvos na copia'
assert 'fora.example/pagina' in mapa and 'target="_blank"' in mapa and 'data-g="Não copiados"' in mapa, 'esqueleto lista o que nao foi copiado com link direto'
assert 'privado/x.html' in mapa and 'proibido pelo robots.txt' in mapa and 'página de outro site' in mapa, 'motivo exato do bloqueio'
assert 'achado em:' in mapa, 'esqueleto mostra em qual pagina o link nao copiado apareceu'
assert 'fonts.gstatic.com' not in mapa, 'preconnect nao e link'
print('TESTE OK')

# --- download: nome real, tipo, logout, continuar .part, repetir falhas, atualizar ---
pedidos, versao, instavel = [], [1], [0]
CHEIO = bytes(range(256)) * 400


class H2(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        pedidos.append((self.path, self.headers.get('If-None-Match'), self.headers.get('Range')))
        if self.path in ('/robots.txt', '/sitemap.xml', '/imagem-quebrada.png'):  # 404 (sitemap/robots silenciosos; a imagem entra em falhas)
            self.send_response(404); self.end_headers(); return
        if self.path == '/':
            etag = f'"v{versao[0]}"'
            if self.headers.get('If-None-Match') == etag:
                self.send_response(304); self.end_headers(); return
            self.send_response(200); self.send_header('ETag', etag); self.send_header('Content-Type', 'text/html'); self.end_headers()
            self.wfile.write(b'<html><img src="/imagem-quebrada.png"><a href="/download.php?id=3">z</a><a href="/api.php">j</a><a href="/conta/logout">sair</a>'
                             b'<a href="/big.bin">b</a><a href="/instavel.txt">i</a><a href="/novo%d.txt">n</a></html>' % versao[0])
        elif self.path == '/download.php?id=3':
            self.send_response(200); self.send_header('Content-Disposition', 'attachment; filename="pacote.zip"'); self.end_headers()
            self.wfile.write(b'PK zip')
        elif self.path == '/api.php':
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(b'{"a": 1}')
        elif self.path == '/big.bin':
            ini = int(re.search(r'\d+', self.headers.get('Range') or '0').group())
            self.send_response(206 if ini else 200); self.send_header('Content-Length', str(len(CHEIO) - ini)); self.end_headers()
            self.wfile.write(CHEIO[ini:])
        elif self.path == '/instavel.txt':
            instavel[0] += 1
            self.send_response(500 if instavel[0] <= 3 else 200); self.end_headers()
            self.wfile.write(b'' if instavel[0] <= 3 else b'agora foi')
        elif self.path.startswith('/novo'):
            self.send_response(200); self.end_headers(); self.wfile.write(b'novo')
        else:
            raise AssertionError('nao podia pedir ' + self.path)


import re
srv2 = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H2)
p2 = srv2.server_address[1]
threading.Thread(target=srv2.serve_forever, daemon=True).start()
raiz2, log2 = os.path.join(tempfile.mkdtemp(), 'espelho'), []
site2 = os.path.join(raiz2, f'127.0.0.1_{p2}')
os.makedirs(site2)
open(os.path.join(site2, 'big.bin.part'), 'wb').write(CHEIO[:10000])  # download cortado no meio
rodar = lambda **k: p.espelhar([f'http://127.0.0.1:{p2}/'], raiz2, log2.append, threading.Event(), robots=False, pausa=0, gerar_zip=False, sitemap=False, **k)
rodar()
assert open(os.path.join(site2, 'pacote.zip'), 'rb').read() == b'PK zip', 'nome real pelo Content-Disposition'
assert os.path.exists(os.path.join(site2, 'api.php.json')), 'tipo real pelo Content-Type'
assert open(os.path.join(site2, 'big.bin'), 'rb').read() == CHEIO and ('/big.bin', None, 'bytes=10000-') in pedidos, 'continua o .part'
assert open(os.path.join(site2, 'instavel.txt')).read() == 'agora foi', 'tenta de novo o que falhou'
assert not any('logout' in x[0] for x in pedidos), 'nunca abre logout'
ftxt = open(os.path.join(raiz2, '.painel', 'falhas.txt')).read()
assert 'imagem-quebrada.png' in ftxt and 'achado em:' in ftxt, 'falhas.txt mostra a pagina de origem do arquivo que faltou'
# rodar de novo (sem atualizar): nada novo e nenhum pedido de lixo vindo das paginas ja reescritas
del pedidos[:]; del log2[:]
rodar()
assert [x[0] for x in pedidos if x[0] not in ('/robots.txt', '/sitemap.xml', '/imagem-quebrada.png')] == [], pedidos  # meta sem 404-cache: re-pedido ok
# atualizar: pagina nao mudou -> 304; depois muda -> baixa de novo e acha o arquivo novo
rodar(atualizar=True)
assert ('/', '"v1"', None) in pedidos and not os.path.exists(os.path.join(site2, 'novo2.txt')), 'atualizar usa ETag'
versao[0] = 2
rodar(atualizar=True)
assert os.path.exists(os.path.join(site2, 'novo2.txt')), 'atualizar baixa o que mudou'
assert 'nao_baixado' not in ''.join(x[0] for x in pedidos), 'nao segue links reescritos'
print('TESTE DOWNLOAD OK')

# --- automacao: perfil rodado sem janela (o que o agendamento do Windows chama) ---
tmp = tempfile.mkdtemp()
p.PERFIS, p.LISTA_BLOQUEIO, p.LISTA_FORMATOS = os.path.join(tmp, 'perfis'), os.path.join(tmp, 'b.txt'), os.path.join(tmp, 'f.txt')
os.makedirs(p.PERFIS)
open(p.LISTA_FORMATOS, 'w').write('zip\n')
import json
json.dump({'enderecos': f'http://127.0.0.1:{p2}/', 'pasta': tmp, 'robots': False, 'pausa': 0, 'zip': False, 'sitemap': False,
           'desmarcados': ['Dados']}, open(os.path.join(p.PERFIS, 'meu-site.json'), 'w'))
p.rodar_perfis(['meu-site', 'nao-existe'], atualizar=True)
site3 = os.path.join(tmp, 'espelho', f'127.0.0.1_{p2}')
assert os.path.exists(os.path.join(site3, 'index.html')) and os.path.exists(os.path.join(tmp, 'Abrir site completo.bat')), 'perfil rodou'
assert not os.path.exists(os.path.join(site3, 'pacote.zip')), 'formato bloqueado na lista'
assert not os.path.exists(os.path.join(site3, 'api.php.json')), 'tipo desmarcado no perfil'
assert 'PRONTO' in open(os.path.join(tmp, 'espelho', '.painel', 'ultimo.log')).read(), 'registro do agendamento'
# varios sites, cada um separado e ao mesmo tempo (127.0.0.1 e localhost contam como dois sites)
json.dump({'enderecos': f'http://127.0.0.1:{p2}/\nhttp://localhost:{p2}/', 'pasta': tmp, 'robots': False, 'pausa': 0, 'zip': False,
           'sitemap': False, 'separados': True}, open(os.path.join(p.PERFIS, 'dois.json'), 'w'))
p.rodar_perfis(['dois'])
for site in (f'127.0.0.1_{p2}', f'localhost_{p2}'):
    assert os.path.exists(os.path.join(tmp, site, 'espelho', site, 'index.html')), 'site separado: ' + site
    assert os.path.exists(os.path.join(tmp, site, 'Abrir site.html')), 'atalhos de cada site'
assert p.separar(['http://a.com/x', 'http://a.com/y'], '/p', True) == [(['http://a.com/x', 'http://a.com/y'], os.path.join('/p', 'espelho'))], 'mesmo site fica junto'
print('TESTE AUTOMACAO OK')

# --- codigo que parece endereco mas nao e (achados em sites reais) ---
js = '''const e=new URL(this.config.iconUrl,window.location); a={api:"https://vimeo.com/api/oembed.json?url={0}"};
el.style.background = "radial-gradient(circle, rgba(3,167,211,0.8) 0%, transparent 70%)"; c="title.class";
css="body{background:url(img/bg.png)}"; h='<a href="docs/foto (1).png">x</a>'; f=".lua,.txt"; g=Ra("googletag.cmd"); i='<img data-src="false"><img src="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=">'; r="@2x.png" '''
assert sorted(set(p.links(js, 'https://s.com/'))) == ['https://s.com/docs/foto (1).png', 'https://s.com/img/bg.png'], p.links(js, 'https://s.com/')
assert p.links('a="ext.fandom.X.css"; b="skin.fandomdesktop.rail.css"; c="vendor.tippy.css"; ok="libs/real.css"', 'https://s.com/') == ['https://s.com/libs/real.css'], 'nomes de modulo do MediaWiki nao viram arquivo'
print('TESTE FALSOS ENDERECOS OK')

# --- servicos de arquivo viram link direto; formulario escondido que nao e download nao e apertado ---
assert p.normal('https://drive.google.com/file/d/1Uq0sHSq9uSqtb2mYw35Si9_r20Y_bnzm/view?usp=sharing') == 'https://drive.google.com/uc?export=download&id=1Uq0sHSq9uSqtb2mYw35Si9_r20Y_bnzm'
assert p.normal('https://github.com/user/repo/blob/main/src/x.lua') == 'https://raw.githubusercontent.com/user/repo/main/src/x.lua'
assert p.normal('https://www.dropbox.com/s/abc/f.zip?dl=0') == 'https://www.dropbox.com/s/abc/f.zip?dl=1'
forms = '''<form action="/x-download" method="POST"><input type="hidden" name="_token" value="t"><button></button></form>
<form action="/index.php?do=cookieConsentToggle" method="POST"><input type="hidden" name="a" value="1"></form>
<form action="/forum/login/" method="POST"><input type="hidden" name="a" value="1"></form>'''
assert [a for a, _ in p.formularios_de_download(forms, 'https://s.com/')] == ['https://s.com/x-download'], p.formularios_de_download(forms, 'https://s.com/')
print('TESTE SERVICOS DE ARQUIVO OK')

# --- DNS pela internet quando o DNS do PC falha ---
import socket as _sock
chamou = []
_orig_resolver = p.resolver_doh
p.resolver_doh = lambda h: (chamou.append(h), '93.184.216.34')[1]  # finge o DoH (sem rede)
r = p._getaddrinfo('site-que-nao-existe.invalid', 443)  # .invalid sempre falha no DNS do sistema
assert chamou == ['site-que-nao-existe.invalid'] and r, 'cai no DNS da internet quando o do sistema falha'
del chamou[:]
p._getaddrinfo('127.0.0.1', 80)  # host que resolve: nao usa o DoH
assert chamou == [], 'DNS do sistema tem prioridade'
p.resolver_doh = _orig_resolver
print('TESTE DNS OK')

# --- atualizacao pelo GitHub: compara VERSAO, so aceita arquivo que parece o painel ---
import urllib.request as _ur
_orig_open = _ur.urlopen
def _fake(resp):
    class R:
        def read(self_): return resp.encode('utf-8')
    p._ur_saved = None
    _ur.urlopen = lambda *a, **k: R()
novo = f'VERSAO_PAINEL = {p.VERSAO_PAINEL + 1}\ndef versao_nova(): pass\n# resto'
_fake(novo);  assert p.versao_nova() == novo, 'versao maior e valida -> atualiza'
_fake(f'VERSAO_PAINEL = {p.VERSAO_PAINEL}\ndef versao_nova(): pass'); assert p.versao_nova() is None, 'mesma versao -> nao atualiza'
_fake(f'VERSAO_PAINEL = {p.VERSAO_PAINEL + 1}\n# sem a funcao'); assert p.versao_nova() is None, 'arquivo estranho -> nao atualiza'
def _erro(*a, **k): raise OSError('sem rede')
_ur.urlopen = _erro; assert p.versao_nova() is None, 'sem internet -> nao atualiza'
_ur.urlopen = _orig_open
print('TESTE UPDATE OK')

# --- aviso quando a entrada e bloqueada mas o resto vem ---
import http.server as _h, threading as _t, tempfile as _tf
class H3(_h.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == '/':  # entrada bloqueada
            self.send_response(403); self.end_headers(); return
        if self.path == '/robots.txt':
            self.send_response(200); self.end_headers(); self.wfile.write(b'Sitemap: http://127.0.0.1:%d/sitemap.xml\n' % p3); return
        if self.path == '/sitemap.xml':
            self.send_response(200); self.end_headers()
            self.wfile.write(b'<urlset><url><loc>http://127.0.0.1:%d/pagina-interna</loc></url></urlset>' % p3); return
        self.send_response(200); self.end_headers(); self.wfile.write(b'<html>conteudo</html>')
srv3 = _h.ThreadingHTTPServer(('127.0.0.1', 0), H3); p3 = srv3.server_address[1]
_t.Thread(target=srv3.serve_forever, daemon=True).start()
raiz3, msgs = os.path.join(_tf.mkdtemp(), 'espelho'), []
p.espelhar([f'http://127.0.0.1:{p3}/'], raiz3, msgs.append, threading.Event(), robots=False, pausa=0, gerar_zip=False)
assert any('entrada foi bloqueada' in m and 'segui pelo sitemap' in m for m in msgs), ['SEM AVISO'] + [m for m in msgs if 'aviso' in m]
assert os.path.exists(os.path.join(raiz3, f'127.0.0.1_{p3}', 'pagina-interna.html')), 'pegou a pagina interna pelo sitemap mesmo com a entrada bloqueada'
print('TESTE AVISO ENTRADA OK')

# --- "so as paginas coladas": profundidade 0 (nao segue links de pagina), mas traz arquivos ate de outro site ---
alvos_sc, kw_sc = p.argumentos({'enderecos': 'https://site.com/pagina', 'pasta': '/p', 'so_coladas': True, 'prof': 5, 'sitemap': True})
assert kw_sc['profundidade'] == 0 and kw_sc['sitemap'] is False, 'so_coladas forca profundidade 0 e sem sitemap'
alvos_n, kw_n = p.argumentos({'enderecos': 'https://site.com/pagina', 'pasta': '/p', 'so_coladas': False, 'prof': 5, 'sitemap': True})
assert kw_n['profundidade'] == 5 and kw_n['sitemap'] is True, 'sem a opcao, usa a profundidade normal'
assert kw_sc['recursos_fora'] is True, 'arquivos de fora continuam vindo (hospedados fora do site)'
print('TESTE SO COLADAS OK')

# --- Modo leitura: remove scripts (anti-adblock/anuncio) e mostra imagem preguicosa ---
tmpl = tempfile.mkdtemp()
site_l = os.path.join(tmpl, 'espelho', 's.com')
os.makedirs(site_l)
open(os.path.join(site_l, 'logo.png'), 'wb').write(b'PNG')
pag = '''<html><head><script src="antiadblock.js"></script></head><body>
<img src="data:image/gif;base64,R0lGOD" data-src="logo.png"><p>conteudo do wiki</p>
<script>alert("please allow ads")</script></body></html>'''
dest_l = os.path.join(site_l, 'index.html')
open(dest_l, 'w', encoding='utf-8').write(pag)
import json as _json
_json.dump({'http://s.com/': {'dest': os.path.join('s.com', 'index.html')}, 'http://s.com/logo.png': {'dest': os.path.join('s.com', 'logo.png')}},
           open(os.path.join(tmpl, 'espelho', '.painel', 'estado.json') if os.path.isdir(os.path.join(tmpl, 'espelho', '.painel')) else os.path.join(site_l, 'x'), 'w')) if False else None
# reescreve direto, com os dois arquivos ja no mapa
mp = {'http://s.com/': dest_l, 'http://s.com/logo.png': os.path.join(site_l, 'logo.png')}
# chama espelhar em cima do que ja existe: so_coladas + leitura, sem baixar (ja tem)
log_l = []
class SL(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == '/':
            self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers(); self.wfile.write(pag.encode()); return
        if self.path == '/logo.png':
            self.send_response(200); self.end_headers(); self.wfile.write(b'PNG'); return
        self.send_response(404); self.end_headers()
srv_l = http.server.ThreadingHTTPServer(('127.0.0.1', 0), SL); pl = srv_l.server_address[1]
threading.Thread(target=srv_l.serve_forever, daemon=True).start()
raizl = os.path.join(tempfile.mkdtemp(), 'espelho')
p.espelhar([f'http://127.0.0.1:{pl}/'], raizl, log_l.append, threading.Event(), robots=False, pausa=0, gerar_zip=False, sitemap=False, leitura=True)
pagina = open(os.path.join(raizl, f'127.0.0.1_{pl}', 'index.html'), encoding='utf-8').read()
assert '<script' not in pagina.lower(), 'modo leitura tira os scripts'
assert 'allow ads' not in pagina, 'tira o pop-up de anti-adblock'
assert 'src="logo.png"' in pagina or 'src=logo.png' in pagina, 'imagem preguicosa aparece (data-src vira src)'
assert 'conteudo do wiki' in pagina, 'o conteudo continua la'
print('TESTE MODO LEITURA OK')

# --- extensao no meio do caminho (Fandom: TW8.jpg/revision/latest) ---
assert p.extensao('https://static.wikia.nocookie.net/x/images/a/a5/TW8.jpg/revision/latest?cb=1') == 'jpg', 'acha a extensao no meio do caminho'
assert p.extensao('https://s/x/TW8.jpg/revision/latest/scale-to-width-down/185?cb=1') == 'jpg', 'acha ate no thumb redimensionado'
assert p.extensao('https://s/pagina') == '' and p.extensao('https://s/a/b.php') == 'php', 'pagina normal nao muda'
assert p.caminho_local('/r', 'https://static.wikia.nocookie.net/x/a/TW8.jpg/revision/latest?cb=1').endswith('.jpg'), 'salva com .jpg, nao .html'
print('TESTE IMAGEM FANDOM OK')

# --- lista de novos: 2a rodada sobre a mesma pasta deve registrar 0 novos ---
tmpn = os.path.join(tempfile.mkdtemp(), 'espelho')
ln = []
rodar_n = lambda: p.espelhar([f'http://127.0.0.1:{p2}/'], tmpn, ln.append, threading.Event(), robots=False, pausa=0, gerar_zip=False, sitemap=False)
rodar_n()
assert any('arquivos novos nesta rodada' in m for m in ln), 'informa quantos novos'
primeiros = len(open(os.path.join(tmpn, '.painel', 'novos.txt')).read().split())
assert primeiros > 0, 'primeira rodada tem novos'
del ln[:]; rodar_n()
assert open(os.path.join(tmpn, '.painel', 'novos.txt')).read().strip() == '' and any('0 arquivos novos' in m for m in ln), 'rodar de novo sem mudanca: 0 novos'
print('TESTE NOVOS OK')

# --- motivo da falha: explica em portugues por que nao baixou ---
assert 'nome de imagem aberto como pagina' in p.motivo_falha('https://x.fandom.com/wiki/CM45.jpg', 404), 'nome de imagem como pagina'
assert 'editar/historico' in p.motivo_falha('https://x.fandom.com/wiki/SPELLS?action=edit', 200), 'link de editar'
assert 'File:CM45.jpg' not in '' and '404' in p.motivo_falha('https://x.fandom.com/wiki/Category:Videos', 404), 'pagina real some: so o 404'
assert 'rede' in p.motivo_falha('https://x/y', 'timeout'), 'erro de rede'
print('TESTE MOTIVO FALHA OK')

# --- nao inventar /wiki/NOME.jpg a partir de data-image-name (bug Fandom RM2) ---
fandom_fig = '''<figure><a href="https://static.wikia.nocookie.net/x/images/c/c9/RM2.jpg/revision/latest?cb=1" class="image"><img alt="RM2" src="data:image/gif;base64,R0lGODlhAQAB" class="lazyload" data-image-name="RM2.jpg" data-image-key="RM2.jpg" data-src="https://static.wikia.nocookie.net/x/images/c/c9/RM2.jpg/revision/latest/scale-to-width-down/850?cb=1" /></a><figcaption><a href="/wiki/File:RM2.jpg" class="info-icon"></a></figcaption></figure>'''
achados = p.links(fandom_fig, 'https://heroic-magic-duel.fandom.com/wiki/RARE_MINIONS')
assert not any(u.endswith('/wiki/RM2.jpg') for u in achados), 'nao inventa /wiki/RM2.jpg de data-image-name'
assert any('static.wikia' in u and u.endswith('RM2.jpg/revision/latest') for u in achados), 'a imagem real (static.wikia) continua sendo pega'
assert any(u.endswith('/wiki/File:RM2.jpg') for u in achados), 'a pagina File: continua sendo pega'
# nome de arquivo real escondido em script (com caminho) nao pode ser perdido
assert any(u.endswith('/js/app.lua') for u in p.links('var x="/js/app.lua"', 'https://s/p')), 'arquivo com caminho em script continua'
print('TESTE SEM LINK FANTASMA OK')

# --- "Só o que faltou": seed vem da falhas.txt, nao revarre o site ---
tmpf = os.path.join(tempfile.mkdtemp(), 'espelho')
os.makedirs(os.path.join(tmpf, '.painel'))
open(os.path.join(tmpf, '.painel', 'falhas.txt'), 'w').write(
    f'http://127.0.0.1:{p2}/  -> erro de rede (sem resposta do servidor)\n# comentario ignorado\n')
lf = []
p.espelhar(['http://nao-usado.invalido/'], tmpf, lf.append, threading.Event(),
           robots=False, pausa=0, gerar_zip=False, so_faltou=True)
assert any('só o que faltou' in m for m in lf), 'anuncia o modo'
# baixou a raiz que estava na falhas.txt, mas NAO seguiu os links dela (prof 0): so 1 arquivo
baixou = [m for m in lf if m.startswith('ok (') or m.startswith('(ja tinha) ok (')]
assert any(f'127.0.0.1:{p2}/' in m for m in baixou), 'pegou o endereco que faltou'
assert not any('/vip' in m or '/ferramenta' in m for m in baixou), 'nao seguiu links novos (nao revarre o site)'
print('TESTE SO FALTOU OK')

# --- "Só o que faltou" ignora lixo conhecido vindo de uma falhas.txt antiga ---
assert p.pulavel('https://x.fandom.com/wiki/SUNSET1.jpg'), 'nome de imagem como pagina e pulavel'
assert p.pulavel('https://x.fandom.com/wiki/SPELLS?action=edit'), 'botao editar e pulavel'
assert not p.pulavel('https://x.fandom.com/wiki/SPELLS'), 'pagina real nao e pulavel'
assert not p.pulavel('https://static.wikia.nocookie.net/x/a/RM2.jpg/revision/latest'), 'imagem real nao e pulavel'
tmpi = os.path.join(tempfile.mkdtemp(), 'espelho')
os.makedirs(os.path.join(tmpi, '.painel'))
open(os.path.join(tmpi, '.painel', 'falhas.txt'), 'w').write(
    f'http://127.0.0.1:{p2}/  -> erro de rede\n'
    'https://x.fandom.com/wiki/SUNSET1.jpg  -> nome de imagem\n'
    'https://x.fandom.com/wiki/SPELLS?action=edit  -> editar\n')
li = []
p.espelhar(['http://nao.invalido/'], tmpi, li.append, threading.Event(), robots=False, pausa=0, gerar_zip=False, so_faltou=True)
assert any('2 ignorados' in m for m in li), 'ignora os 2 lixos conhecidos'
print('TESTE SO FALTOU IGNORA LIXO OK')

# --- CDN que estrangula (403 na 1a vez, 200 na 2a) deve ser tentado de novo ---
class ST(http.server.BaseHTTPRequestHandler):
    vistos = set()
    def log_message(self, *a): pass
    def do_GET(self):
        p0 = self.path.split('?')[0]
        if p0 == '/foto.jpg':  # 403 na primeira vez, ok na repeticao
            if p0 not in ST.vistos:
                ST.vistos.add(p0); self.send_response(403); self.end_headers(); return
            self.send_response(200); self.send_header('Content-Type', 'image/jpeg'); self.end_headers(); self.wfile.write(b'JPEGDATA'); return
        if p0 == '/':
            self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers()
            self.wfile.write(b'<img src="/foto.jpg">'); return
        self.send_response(404); self.end_headers()
srv_t = http.server.ThreadingHTTPServer(('127.0.0.1', 0), ST); pt = srv_t.server_address[1]
threading.Thread(target=srv_t.serve_forever, daemon=True).start()
raizt = os.path.join(tempfile.mkdtemp(), 'espelho')
lt = []
_sleep = p.time.sleep; p.time.sleep = lambda *a: None  # nao esperar os 10s no teste
p.espelhar([f'http://127.0.0.1:{pt}/'], raizt, lt.append, threading.Event(), robots=False, pausa=0, gerar_zip=False, sitemap=False)
p.time.sleep = _sleep
assert any('excesso de pedidos' in m for m in lt), 'avisa que vai tentar de novo os estrangulados'
assert os.path.exists(os.path.join(raizt, f'127.0.0.1_{pt}', 'foto.jpg')), 'a imagem 403 foi baixada na repeticao'
print('TESTE ESTRANGULADO OK')
