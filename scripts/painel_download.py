"""Painel para espelhar paginas e arquivos publicos para leitura offline (alternativa leve ao HTTrack).

- espelho em pastas (dominio/caminho), com links reescritos para abrir offline; o que nao foi baixado vai para nao_baixado.html
  e uma trava (CSP) impede a pagina de acessar a internet; opcional: .zip no fim
- filtros no estilo HTTrack, um por linha: +*.pdf (inclui, mesmo de outro site)  -*.gif (exclui)
- profundidade (so conta paginas HTML), limite de paginas, MB por arquivo, varias conexoes, pausa entre pedidos
- retoma: arquivo ja baixado nao baixa de novo; respeita robots.txt (desligavel); ignora anuncios e redes sociais
- atualizar: so baixa de novo o que mudou (ETag/Last-Modified); continua download cortado; repete o que falhou por erro de rede
- no fim cria, na pasta escolhida: 'Abrir site.html', 'Esqueleto do site.html' e 'Abrir site completo.bat' (servidor local)
- perfis + agendamento: python painel_download.py --perfil nome [--perfil outro] [--atualizar] roda sem janela
- se o DNS do PC estiver quebrado, resolve o endereco pela internet (DoH 1.1.1.1/8.8.8.8), como o navegador
Le sitemap.xml. Segue href/src/srcset/data-*/css url()/@import/meta refresh/sourcemap, playlists .m3u8 e, dentro de html/js/json/lua/etc.,
enderecos completos e caminhos entre aspas com extensao conhecida ("scripts/main.lua", JSON com \\/). Nao adivinha enderecos.
- opcional: renderiza as paginas num navegador de verdade (Playwright) e pega o que o JavaScript monta e pede"""
import codecs, fnmatch, functools, gzip, hashlib, html as htmllib, http.cookiejar, http.server, json, mimetypes, os, re, socket, subprocess, sys, threading, time, tkinter as tk, urllib.error, urllib.parse, urllib.request, urllib.robotparser, webbrowser, zipfile, zlib
import queue
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

BLOQUEADOS = {  # lixo conhecido (caixa 'Bloquear anuncios e redes sociais'); vale para o site e todos os subdominios
    # anuncios e rastreadores
    'doubleclick.net', 'googlesyndication.com', 'google-analytics.com', 'googletagmanager.com', 'googleadservices.com',
    'adservice.google.com', 'amazon-adsystem.com', 'adnxs.com', 'criteo.com', 'taboola.com', 'outbrain.com', 'hotjar.com',
    'scorecardresearch.com', 'facebook.net', 'addthis.com', 'sharethis.com', 'clarity.ms', 'bat.bing.com', 'mc.yandex.ru',
    'mixpanel.com', 'segment.com', 'segment.io', 'newrelic.com', 'nr-data.net', 'optimizely.com', 'quantserve.com', 'adsrvr.org',
    'rubiconproject.com', 'pubmatic.com', 'openx.net', 'casalemedia.com', 'moatads.com', 'ads-twitter.com', 'hs-analytics.net',
    # avisos de cookie, chats e comentarios
    'onetrust.com', 'cookielaw.org', 'cookiebot.com', 'usercentrics.eu', 'intercom.io', 'tawk.to', 'crisp.chat', 'onesignal.com',
    'disqus.com', 'disquscdn.com',
    # contadores de visita proprios (analytics.site.com etc.)
    'rybbit.com', 'rybbit.io', 'plausible.io', 'umami.is', 'matomo.cloud', 'statcounter.com', 'cloudflareinsights.com',
    'analytics.*', 'stats.*', 'metrics.*', 'tracking.*', 'telemetry.*',
    # redes sociais
    'facebook.com', 'fb.com', 'fb.me', 'fbcdn.net', 'instagram.com', 'cdninstagram.com', 'twitter.com', 'x.com', 't.co', 'twimg.com',
    'tiktok.com', 'tiktokcdn.com', 'linkedin.com', 'licdn.com', 'pinterest.com', 'pinimg.com', 'reddit.com', 'redd.it', 'redditmedia.com',
    'youtube.com', 'youtu.be', 'ytimg.com', 'googlevideo.com', 'whatsapp.com', 'wa.me', 'telegram.org', 't.me', 'discord.com', 'discord.gg',
    'snapchat.com', 'threads.net', 'tumblr.com', 'vk.com', 'kwai.com', 'twitch.tv', 'bsky.app', 'mastodon.social', 'quora.com',
}
ATTR = re.compile(r'''\b(?:href|src|xlink:href|poster|background|data|manifest|lowsrc|longdesc|data-[\w-]*(?:src|href|url|file|original|bg|background|download|lazy))\s*=\s*["']([^"'#]+)'''
                  r'''|(?-i:\burl)\(\s*["']?([^"')#]+)|@import\s+["']([^"']+)|\bcontent\s*=\s*["']\d+\s*;\s*url\s*=\s*([^"'#]+)|sourceMappingURL=([^\s"'*]+)''', re.I)
BASE = re.compile(r'''<base\b[^>]*\bhref\s*=\s*["']([^"']+)''', re.I)
SRCSET = re.compile(r'''srcset\s*=\s*["']([^"']+)''', re.I)
ABS = re.compile(r'''https?://[^\s"'<>()\\/]+/[^\s"'<>()\\]*\.[a-z0-9]{1,8}(?:\?[^\s"'`<>()\\]*)?(?=[#"'`\s<>()\\,;]|$)''', re.I)  # endereco completo de arquivo, qualquer formato


GRUPOS = {
    'Páginas': ('html', 'htm', 'php', 'asp', 'aspx', 'jsp', 'jspx', 'cfm', 'cgi', 'xhtml', 'shtml', 'phtml', 'erb', 'cshtml', ''),
    'Estilos e scripts': ('css', 'scss', 'less', 'js', 'mjs', 'cjs', 'jsx', 'ts', 'tsx', 'vue', 'svelte', 'map', 'wasm', 'webmanifest'),
    'Código': ('lua', 'luac', 'py', 'pyc', 'pyd', 'pyw', 'rb', 'pl', 'tcl', 'r', 'vbs', 'vba', 'ahk', 'au3', 'c', 'h', 'cpp', 'hpp',
               'cs', 'java', 'kt', 'kts', 'scala', 'go', 'rs', 'swift', 'dart', 'el', 'ex', 'exs', 'erl', 'gd', 'nut', 'sqf', 'ipynb'),
    'Config': ('ini', 'cfg', 'config', 'toml', 'properties', 'inf', 'reg', 'plist', 'env', 'lst'),
    'Automação e DevOps': ('sh', 'bash', 'ps1', 'psm1', 'psd1', 'bat', 'cmd', 'conf', 'lock', 'htaccess', 'dockerignore', 'gitignore',
                           'dockerfile', 'makefile', 'procfile', 'jenkinsfile'),
    'Banco de dados': ('sql', 'sqlite', 'db', 'mdb', 'graphql', 'gql', 'prisma', 'mongo', 'bson'),
    'Imagens': ('jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'ico', 'cur', 'bmp', 'tif', 'tiff', 'avif', 'heic', 'heif', 'jxl', 'apng',
                'psd', 'ai', 'eps', 'tga', 'dds', 'raw', 'cr2', 'nef', 'dng'),
    'Documentos': ('pdf', 'doc', 'docx', 'xls', 'xlsx', 'xlsm', 'ppt', 'pptx', 'odt', 'ods', 'odp', 'txt', 'log', 'csv', 'tsv', 'rtf',
                   'md', 'markdown', 'tex', 'epub', 'mobi', 'azw3', 'fb2', 'djvu', 'chm', 'xps'),
    'Dados': ('json', 'jsonl', 'jsonld', 'ndjson', 'geojson', 'xml', 'rss', 'atom', 'yaml', 'yml', 'dat', 'proto', 'parquet', 'kml', 'gpx', 'ics', 'vcf'),
    'Compactados': ('zip', 'rar', '7z', 'tar', 'tgz', 'gz', 'bz2', 'tbz2', 'xz', 'txz', 'zst', 'lz', 'lzma', 'lzh', 'arj', 'cab', 'z'),
    'Programas': ('exe', 'dll', 'msi', 'msix', 'appx', 'com', 'sys', 'ocx', 'cpl', 'scr', 'drv', 'efi', 'apk', 'xapk', 'apks', 'aab',
                  'ipa', 'deb', 'rpm', 'appimage', 'pkg', 'dmg', 'dylib', 'so', 'lib', 'bin', 'elf', 'jar', 'war', 'class', 'dex', 'run', 'iso', 'img', 'vhd', 'vmdk', 'crx', 'xpi', 'vsix', 'swf'),
    'Jogos e 3D': ('pak', 'vpk', 'wad', 'bsp', 'unity3d', 'assets', 'bundle', 'uasset', 'pk3', 'esp', 'esm', 'bsa', 'ba2', 'mod',
                   'obj', 'fbx', 'gltf', 'glb', 'usdz', 'hdr', 'exr', 'stl', 'blend', 'dae', '3ds', 'mdl', 'ct', 'cetrainer', 'sav', 'rom', 'nds', 'gba'),
    'Áudio': ('mp3', 'mp2', 'wav', 'wma', 'ogg', 'oga', 'opus', 'flac', 'aac', 'm4a', 'aiff', 'mid', 'midi', 'amr'),
    'Vídeo': ('mp4', 'm4v', 'mov', 'mpg', 'mpeg', 'avi', 'asf', 'wmv', 'rm', 'vob', 'qt', 'vid', 'ac3', 'mkv', 'webm', 'flv', 'ogv',
              '3gp', 'm3u8', 'm3u', 'mpd', 'srt', 'vtt'),
    'Fontes': ('woff', 'woff2', 'ttf', 'otf', 'eot'),
    'Outros conhecidos': ('torrent', 'crt', 'cer', 'pem', 'gpg', 'sig', 'sha256', 'md5', 'iss', 'nsi'),
}
AQUI = os.path.dirname(os.path.abspath(__file__))
LISTA_BLOQUEIO, LISTA_FORMATOS, CONFIG, PERFIS = (os.path.join(AQUI, n) for n in ('sites_bloqueados.txt', 'formatos_bloqueados.txt', 'painel_config.json', 'perfis'))
CONHECIDAS = {e for g in GRUPOS.values() for e in g}
DINAMICAS = {'php', 'asp', 'aspx', 'jsp', 'jspx', 'cfm', 'cgi', 'shtml', 'phtml', 'erb', 'cshtml'}  # pagina gerada no servidor: salva como .html para abrir offline
LER = {'html', 'htm', 'xhtml', 'css', 'js', 'mjs', 'cjs', 'json', 'xml', 'svg', 'txt', 'm3u8', 'm3u', 'webmanifest', 'rss', 'atom', 'jsonld',
       'vue', 'svelte', 'md', 'markdown', 'graphql', 'gql', 'prisma', *GRUPOS['Código'], *GRUPOS['Config'], *GRUPOS['Automação e DevOps']}  # arquivos de texto onde procurar links escondidos
# nomes que tambem sao palavras de codigo/dominio ("console.log", "site.com"): so contam com '/' no caminho
SEM_PONTO = {'Dockerfile', 'Makefile', 'Procfile', 'Jenkinsfile'}  # arquivos conhecidos sem extensao
DUVIDOSAS = {e for e in CONHECIDAS if len(e) < 3} | {'com', 'log', 'map', 'app', 'key', 'sys', 'lib', 'env', 'dat', 'img', 'bin',
                                                     'run', 'mod', 'obj', 'ct', 'esp', 'sig', 'assets', 'bundle', 'config', 'data', 'lock', 'class', 'cmd'}
# so contam com '/' no caminho: nome de midia/fonte solto num texto e rotulo (data-image-name="RM2.jpg", alt), nao um endereco; o link real vem com caminho no src/href
SO_COM_CAMINHO = {*GRUPOS['Imagens'], *GRUPOS['Áudio'], *GRUPOS['Vídeo'], *GRUPOS['Fontes']}
MODULO = re.compile(r'(?i)^(?:ext|skin|mediawiki|vendor|oojs|wikia|jquery)\.[\w.-]+\.(?:css|js)$')  # nome de modulo do MediaWiki (sem barra), nao um arquivo
QUOTADO = re.compile(r'''["'`]([^"'`\s<>(){}\\|^]+(?:\.(?:%s)|/(?:%s))(?:[?#][^"'`\s]*)?)["'`]''' % ('|'.join(
    sorted((re.escape(e) for e in CONHECIDAS if e), key=len, reverse=True)), '|'.join(SEM_PONTO)), re.I)  # "dir/arquivo.lua" escondido em qualquer texto
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'  # como o navegador; sem isso muitos sites dao 403
VERSAO_PAINEL = 67  # sobe a cada melhoria; a atualizacao automatica compara com a do GitHub
RAW = 'https://raw.githubusercontent.com/Sedricko/painel-download/claude/wonderful-brown-74iy6z/scripts/painel_download.py'


def versao_nova():
    """texto da versao mais nova no GitHub, ou None (sem internet ou ja atualizado)"""
    try:
        url = f'{RAW}?nocache={int(time.time())}'  # fura o cache do GitHub (serve copia antiga por ~5 min apos cada envio)
        txt = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA, 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}), timeout=8).read().decode('utf-8')
    except Exception:
        return None
    m = re.search(r'^VERSAO_PAINEL = (\d+)', txt, re.M)
    return txt if m and int(m.group(1)) > VERSAO_PAINEL and 'def versao_nova' in txt else None
JAR = http.cookiejar.CookieJar()  # guarda o cookie da sessao durante o download, como o navegador
NAVEGADOR = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR))

# DNS pela internet (DoH): quando o DNS do PC esta quebrado, resolve o nome como o navegador faz.
# Os servidores sao IPs fixos, entao nao precisam do DNS do sistema para serem alcancados.
DOH = ('https://1.1.1.1/dns-query', 'https://8.8.8.8/resolve', 'https://9.9.9.9:5053/dns-query')
_dns, _dns_lock, _getaddrinfo_orig, log_dns = {}, threading.Lock(), socket.getaddrinfo, [None]  # log_dns[0]: aviso no registro


def resolver_doh(host):
    """IP do host por varios provedores (o que responder primeiro); None se nenhum resolver"""
    for url in DOH:
        try:
            req = urllib.request.Request(f'{url}?name={urllib.parse.quote(host)}&type=A', headers={'accept': 'application/dns-json'})
            dados = json.load(_getaddrinfo_opener.open(req, timeout=8))
            ips = [a['data'] for a in dados.get('Answer', ()) if a.get('type') == 1]  # type 1 = A (IPv4)
            if ips:
                return ips[0]
        except Exception:
            continue
    return None


_getaddrinfo_opener = urllib.request.build_opener()  # sem cookies: so para as consultas de DNS


def _getaddrinfo(host, *a, **k):
    """usa o DNS do PC; se ele falhar (DNS quebrado), descobre o IP pela internet"""
    try:
        return _getaddrinfo_orig(host, *a, **k)
    except socket.gaierror:
        with _dns_lock:
            ip = _dns.get(host)
        novo = ip is None
        if novo:
            ip = resolver_doh(host) if isinstance(host, str) else None
            with _dns_lock:
                _dns[host] = ip or ''
        if not ip:
            raise
        if novo and log_dns[0]:
            log_dns[0](f'aviso: DNS do PC falhou para {host}; resolvi pela internet ({ip})')
        return _getaddrinfo_orig(ip, *a, **k)  # conecta no IP; o nome continua indo no SNI/certificado


socket.getaddrinfo = _getaddrinfo  # http.client/urllib passam a contornar o DNS quebrado sozinhos
# regra do navegador: scripts da pagina nao acessam a internet (so arquivos locais); formularios nao enviam nada
TRAVA = ('''<meta http-equiv="Content-Security-Policy" content="default-src 'self' file: data: blob: 'unsafe-inline' 'unsafe-eval'; '''
         '''form-action 'none'">''')
NAO_BAIXADO = ('''<!doctype html><meta charset="utf-8"><title>Nao baixado</title><body style="font-family:sans-serif;padding:24px">'''
               '''<h2>Este link nao foi baixado</h2><p>Endereco original (copie se quiser abrir na internet):</p>'''
               '''<p><code id="u"></code></p><p><a href="javascript:history.back()">Voltar</a> &nbsp; '''
               '''<a id="ir" target="_blank" rel="noopener noreferrer">Abrir na internet &#8599;</a></p><script>'''
               '''const u = decodeURIComponent(location.hash.slice(1)); document.getElementById('u').textContent = u;'''
               '''if (/^https?:/.test(u)) document.getElementById('ir').href = u; else document.getElementById('ir').remove()</script>''')
PRECONEXAO = re.compile(r'''<link\b[^>]*\brel\s*=\s*["']?(?:preconnect|dns-prefetch)\b[^>]*>''', re.I)
FORM = re.compile(r'<form\b([^>]*)>(.*?)</form>', re.I | re.S)


def ler_txt(c):
    """(texto, codificacao) sem perder bytes: pagina em iso-8859-1/windows-1252 volta igual ao ser gravada"""
    b = open(c, 'rb').read()
    try:
        return b.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        pass
    m = re.search(rb'''charset\s*=\s*["']?([\w-]+)''', b[:4096], re.I)
    try:
        enc = codecs.lookup(m.group(1).decode('ascii')).name if m else 'cp1252'
    except LookupError:
        enc = 'cp1252'
    return b.decode(enc, 'surrogateescape'), enc


def grava_txt(c, texto, enc):
    open(c, 'w', encoding=enc, errors='surrogateescape' if enc != 'utf-8' else 'xmlcharrefreplace').write(texto)


class Renderizador:
    """navegadores (Playwright), cada um na sua linha: a API sync so funciona na linha que a criou"""
    def __init__(self, log, cookies, abas=1):
        self.fila, self.log, self.cookies, self.abas, self.linhas = queue.Queue(), log, cookies, max(1, abas), []

    def _roda(self):
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            for canal in (None, 'msedge', 'chrome'):  # Edge/Chrome do PC: dispensa o 'playwright install'
                try:
                    nav = pw.chromium.launch(channel=canal) if canal else pw.chromium.launch()
                    break
                except Exception:
                    if canal == 'chrome':
                        pw.stop()
                        raise
        except Exception as e:
            self.log(f'aviso: renderizar JavaScript precisa do Playwright (pip install playwright && playwright install chromium): {e}')
            while (item := self.fila.get()) is not None:  # sem navegador: responde vazio e segue sem renderizar
                item[1].append(None); item[2].set()
            return
        ctx = nav.new_context(user_agent=UA)
        for dom, ck in self.cookies.items():  # cookie so no dominio dele (nunca vai para CDN/anuncio)
            host = dom.split(':')[0]
            ctx.add_cookies([{'name': n.strip(), 'value': v.strip(), 'domain': host, 'path': '/'}
                             for n, _, v in (x.partition('=') for x in ck.split(';')) if n.strip()])
        while (item := self.fila.get()) is not None:
            u, saida, pronto = item
            pg, pedidos = ctx.new_page(), []
            pg.on('request', lambda r: pedidos.append(r.url))  # o que o JavaScript pediu: acha nomes montados por codigo
            try:
                pg.goto(u, wait_until='networkidle', timeout=45000)
                for _ in range(5):  # rola a pagina: carrega imagens preguicosas e listas infinitas
                    pg.mouse.wheel(0, 20000)
                    pg.wait_for_timeout(400)
                saida.append((pg.content(), pedidos))
            except Exception as e:
                self.log(f'aviso: nao consegui renderizar {u}: {e}')
                saida.append(None)
            finally:
                pg.close()
                pronto.set()
        ctx.close(); nav.close(); pw.stop()

    def __call__(self, u):
        """(html depois do JavaScript, [enderecos pedidos]) ou None"""
        if not self.linhas:
            self.linhas = [threading.Thread(target=self._roda, daemon=True) for _ in range(self.abas)]
            for t in self.linhas:
                t.start()
        saida, pronto = [], threading.Event()
        self.fila.put((u, saida, pronto))
        pronto.wait()
        return saida[0]

    def fechar(self):
        for _ in self.linhas:
            self.fila.put(None)
        for t in self.linhas:
            t.join(30)


def atributo(tag, nome):
    m = re.search(r'''\b%s\s*=\s*["']([^"']*)''' % nome, tag, re.I)
    return htmllib.unescape(m.group(1)) if m else ''


def formularios_de_download(texto, base):
    """[(action, dados)] dos forms POST que so tem campos escondidos (botao de download, nunca login/busca)"""
    out = []
    for attrs, corpo in FORM.findall(texto):
        if atributo(attrs, 'method').lower() != 'post':
            continue
        campos = re.findall(r'<input\b[^>]*>', corpo, re.I)
        if any(atributo(c, 'type').lower() not in ('hidden', 'submit') for c in campos) or re.search(r'<(textarea|select)\b', corpo, re.I):
            continue
        dados = {atributo(c, 'name'): atributo(c, 'value') for c in campos if atributo(c, 'type').lower() == 'hidden' and atributo(c, 'name')}
        acao = urllib.parse.urljoin(base, atributo(attrs, 'action') or base)
        if PERIGOSOS.search(acao) or re.search(r'(?i)log-?in|register|sign-?up|cookie|consent|multimod|vote|rate|report|follow|subscribe|password', acao):
            continue  # so tem campos escondidos mas nao e download (aceitar cookies, moderar, entrar...)
        out.append((acao, dados))
    return out


def nome_do_cabecalho(headers):
    """nome do arquivo que o servidor manda em Content-Disposition (ou '')"""
    m = re.search(r'''filename\*?=(?:UTF-8'')?["']?([^"';]+)''', headers.get('Content-Disposition') or '', re.I)
    return re.sub(r'[<>:"/|?*\\]', '_', os.path.basename(urllib.parse.unquote(m.group(1)).strip())) if m else ''


VERSAO = {'v', 'ver', 'version', '_', 't', 'ts', 'cb', 'cache', 'rev', 'hash', 'h'}
PERIGOSOS = re.compile(r'(?i)(?:^|[/?&=_.-])(?:log-?out|sign-?out|log-?off|sair|deslogar|delete|excluir|apagar|remover|unsubscribe)(?:[/?&=_.-]|$)')


DIRETO = re.compile(r'https://drive\.google\.com/uc\?export=download&id=')  # link de download direto (sem extensao no endereco)


def normal(u):
    """app.js?v=3 e app.js?v=4 sao o mesmo arquivo: tira o ?v= (so de arquivo, nunca de pagina);
    pagina de servico de arquivos vira o link direto do arquivo (Google Drive, Dropbox, GitHub)"""
    m = re.match(r'https?://drive\.google\.com/(?:file/d/([\w-]{20,})|open\?id=([\w-]{20,}))', u)
    if m:
        return 'https://drive.google.com/uc?export=download&id=' + (m.group(1) or m.group(2))
    m = re.match(r'https?://github\.com/([^/]+/[^/]+)/blob/(.+)', u)
    if m:
        return f'https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}'
    if re.match(r'https?://(?:www\.)?dropbox\.com/', u) and 'dl=0' in u:
        return u.replace('dl=0', 'dl=1')
    p = urllib.parse.urlparse(u)
    if p.query and extensao(u) not in GRUPOS['Páginas'] and {k for k, _ in urllib.parse.parse_qsl(p.query, True)} <= VERSAO:
        return u.split('?')[0]
    return u


def extensao(url):
    """'lua' de x/main.lua; 'htaccess' de /.htaccess; 'jpg' de .../TW8.jpg/revision/latest (Fandom poe o nome no meio)"""
    caminho = urllib.parse.urlparse(url).path
    n = os.path.basename(caminho)
    if n in SEM_PONTO:
        return n.lower()
    if '.' in n:
        return n.rsplit('.', 1)[1].lower()
    for parte in reversed(caminho.split('/')):  # sem extensao no fim: usa a ultima extensao conhecida do caminho
        if '.' in parte and parte.rsplit('.', 1)[1].lower() in CONHECIDAS:
            return parte.rsplit('.', 1)[1].lower()
    return ''


def pulavel(url):
    """endereco que nunca e arquivo real (nome de imagem aberto como pagina, botao de editar/historico): nem tentar, mesmo vindo de uma falhas.txt antiga"""
    base = os.path.basename(urllib.parse.urlparse(url).path)
    if re.search(r'action=(edit|purge|history|credits)|redlink=1', url):
        return True
    return '/wiki/' in url and '.' in base and ':' not in base and extensao(url) in CONHECIDAS


def motivo_falha(url, codigo):
    """explica em portugues por que um link nao baixou, para o falhas.txt"""
    q = urllib.parse.urlparse(url).query
    base = os.path.basename(urllib.parse.urlparse(url).path)
    if re.search(r'action=(edit|purge|history|credits)|redlink=1', url):
        return 'pagina de editar/historico do wiki, nao e um arquivo'
    if '/wiki/' in url and '.' in base and ':' not in base and extensao(url) in CONHECIDAS:
        return 'nome de imagem aberto como pagina; a imagem real foi baixada em outro endereco'
    if not isinstance(codigo, int):
        return 'erro de rede (sem resposta do servidor)'
    return {403: 'bloqueado pelo servidor (403); costuma ser anuncio/rastreador',
            401: 'exige login (401)', 429: 'pedidos demais, o servidor cortou (429)',
            404: 'nao existe no servidor (404)', 410: 'removido do servidor (410)',
            400: 'endereco invalido (400); costuma ser anuncio/rastreador'}.get(codigo, f'erro {codigo}')


def caminho_local(raiz, url):
    p = urllib.parse.urlparse(url)
    c = p.path
    if c.endswith('/') or not c:
        c += 'index.html'
    nome = re.sub(r'[<>:"|?*\\]', '_', c.strip('/'))
    sufixo = '.' + (extensao(url) or 'html')  # nome real da Fandom (.jpg) em vez de .html, quando o fim do endereco nao tem extensao
    if p.query:
        base, ext = os.path.splitext(nome)
        nome = base + '_' + hashlib.md5(p.query.encode()).hexdigest()[:8] + (ext or sufixo)
    elif '.' not in os.path.basename(nome) and os.path.basename(nome) not in SEM_PONTO:
        nome += sufixo
    if extensao(nome) in DINAMICAS:
        nome += '.html'
    return os.path.join(raiz, re.sub(r'[<>:"|?*]', '_', p.netloc), nome)


def base_de(texto, u):
    """endereco de onde partem os links relativos: a pagina, ou o <base href> dela"""
    m = BASE.search(texto)
    return urllib.parse.urljoin(u, htmllib.unescape(m.group(1))) if m else u


def links(texto, base, extras=()):
    base = base_de(texto, base)
    texto = re.sub(r'<base\b[^>]*>', '', texto, flags=re.I)  # o <base> nao e link para baixar
    texto = PRECONEXAO.sub('', texto)  # <link rel=preconnect href=https://fonts.gstatic.com>: dica de conexao, nao arquivo
    texto = re.sub(r'\\u002[fF]', '/', texto.replace('\\/', '/'))  # JSON escapa a barra: "https:\/\/site\/x.lua"
    achados = [next(x for x in m if x) for m in ATTR.findall(texto)]
    for a in QUOTADO.findall(texto):  # "dir/arquivo.lua" escondido em qualquer texto
        nome = a.split('#')[0]
        if ',' in a or MODULO.match(nome):  # ".lua,.txt" e filtro; "ext.fandom.X.css" e nome de modulo do MediaWiki, nao arquivo
            continue
        if '/' in a or extensao(nome) not in DUVIDOSAS | SO_COM_CAMINHO:
            achados.append(a)
    if extensao(base) in ('m3u8', 'm3u'):  # playlist: cada linha sem '#' e um pedaco do video
        achados += [L.strip() for L in texto.splitlines() if L.strip() and not L.startswith('#')]
    if extras:  # extensions the user asked for: also look for them inside scripts ("dir/file.lua", 'https://x/y.lua')
        e = '|'.join(re.escape(x.lstrip('.*')) for x in extras)
        achados += re.findall(r'''["'`]([^"'`\s<>()]+\.(?:%s))(?:\?[^"'`\s]*)?["'`]''' % e, texto, re.I)
        achados += re.findall(r'''(https?://[^\s"'`<>()\\]+\.(?:%s))\b''' % e, texto, re.I)
    for ss in SRCSET.findall(texto):
        achados += [c.strip().split()[0] for c in ss.split(',') if c.strip()]
    achados += ABS.findall(texto)
    out = []
    for a in achados:
        if '{' in a or '}' in a or a.startswith('%23'):  # modelo de JavaScript ("${base}.lua", "video/{0}") ou ancora, nao e endereco
            continue
        if re.match(r'\s*[\w.-]+\(', a):  # funcao de CSS/JS ("radial-gradient(...)", "t.getAttribute(") e nao arquivo
            continue
        if a.strip().lower() in ('false', 'true', 'null', 'undefined', 'none') or a.startswith('@') or re.fullmatch(r'[A-Za-z0-9+/]{40,}={0,2}', a.strip()):
            continue  # valor de atributo ("false"), sufixo ("@2x.png") ou imagem embutida em base64
        u = urllib.parse.urljoin(base, htmllib.unescape(a.strip())).split('#')[0]  # &amp; do html vira &
        if u.startswith('http'):
            out.append(normal(u))
    return out


def ler_sitemaps(sites, log):
    """enderecos <loc> do /sitemap.xml e dos 'Sitemap:' do robots.txt (segue indices de sitemap)"""
    def baixar(u):
        try:
            b = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30).read()
            return (gzip.decompress(b) if b[:2] == b'\x1f\x8b' else b).decode('utf-8', 'replace')  # sitemap.xml.gz
        except Exception:
            return ''
    fila = [s + '/sitemap.xml' for s in sites] + [m for s in sites for m in re.findall(r'(?im)^\s*sitemap:\s*(\S+)', baixar(s + '/robots.txt'))]
    vistos, achados = set(), []
    while fila and len(vistos) < 1000:  # shortcut: le no maximo 1000 sitemaps; aumentar se algum site precisar
        s = fila.pop()
        if s in vistos:
            continue
        vistos.add(s)
        for loc in re.findall(r'<loc>\s*([^<\s]+)', baixar(s)):
            loc = loc.replace('&amp;', '&')
            (fila if '<sitemapindex' in loc or re.search(r'\.xml(\.gz)?(\?|$)', loc, re.I) else achados).append(loc)
    if achados:
        log(f'sitemap: {len(achados)} enderecos')
    return achados


def tamanho(n):
    return f'{n / (1 << 30):.1f} GB' if n >= 1 << 30 else f'{n / (1 << 20):.1f} MB' if n >= 1 << 20 else f'{max(1, n >> 10)} KB'


def redireciona(alvo, titulo):
    """pagina que so abre outra (atalho)"""
    a = htmllib.escape(alvo)
    return (f'<!doctype html><meta charset="utf-8"><title>{titulo}</title><meta http-equiv="refresh" content="0;url={a}">'
            f'<script>location.replace({json.dumps(alvo)})</script><a href="{a}">{titulo}</a>')


ESQUELETO_CSS = """*{box-sizing:border-box}body{margin:0;font:14px 'Segoe UI',system-ui,sans-serif;background:#f4f6fa;color:#1f2937}
header{background:#111827;color:#fff;padding:16px 24px}header h1{margin:0;font-size:20px}header p{margin:4px 0 0;color:#9ca3af}
main{max-width:1100px;margin:0 auto;padding:16px 24px}.barra{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
input{flex:1;min-width:220px;padding:9px 12px;border:1px solid #dfe3ea;border-radius:8px;font:inherit}input:focus{outline:2px solid #2563eb}
.botao{background:#2563eb;color:#fff;padding:9px 18px;border-radius:8px;text-decoration:none;font-weight:600}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}.chip{border:1px solid #dfe3ea;background:#fff;border-radius:99px;padding:4px 12px;cursor:pointer;font:inherit}
.chip.on{background:#2563eb;color:#fff;border-color:#2563eb}.arvore{background:#fff;border:1px solid #dfe3ea;border-radius:10px;padding:8px 14px}
details{margin-left:14px}details>summary{cursor:pointer;padding:3px 0;font-weight:600}details>summary small{font-weight:400}
ul{list-style:none;margin:0;padding-left:28px}.nao>summary{color:#b45309}li{padding:2px 0}a{color:#2563eb}small{color:#6b7280}.arvore>details{margin-left:0}"""

ESQUELETO_JS = """const q=document.getElementById('q');let g='';
function filtra(){const t=q.value.toLowerCase();
document.querySelectorAll('li[data-b]').forEach(li=>li.hidden=(t&&!li.dataset.b.includes(t))||(g&&li.dataset.g!==g));
document.querySelectorAll('.arvore details').forEach(d=>{const v=d.querySelector('li[data-b]:not([hidden])');d.hidden=!v;if(t||g)d.open=!!v;});}
q.oninput=filtra;document.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{g=c.classList.contains('on')?'':c.dataset.g;
document.querySelectorAll('.chip').forEach(x=>x.classList.toggle('on',x.dataset.g===g));filtra();});"""

BAT_COMPLETO = (  # servidor local (sem internet): com ele funcionam sites React/Vue que abertos da pasta ficam em branco
    '@echo off\r\ncd /d "%~dp0espelho"\r\necho Site aberto no navegador. Feche esta janela para parar.\r\n'
    'python -c "import http.server as h, webbrowser as w; s=h.ThreadingHTTPServer((\'127.0.0.1\', 0), h.SimpleHTTPRequestHandler); '
    'w.open(\'http://127.0.0.1:%%d/index.html\' %% s.server_address[1]); s.serve_forever()"\r\n')


def gerar_auditoria(raiz, publicos, protegidos, dominios, cab, log):
    """auditoria.html do site DO USUARIO: o que ficou publico sem login, o que o robots.txt tentava esconder mas
    respondeu, e o que esta protegido (401/403). So mede o ja acessivel; nao quebra nada."""
    robo = {}
    for d in dominios:  # le o robots.txt de cada dominio para marcar o que ele tentava esconder
        rp = None
        for esquema in ('https', 'http'):
            try:
                end = f'{esquema}://{d}/robots.txt'
                txt = NAVEGADOR.open(urllib.request.Request(end, headers=cab(end)), timeout=20).read().decode('utf-8', 'replace')
                rp = urllib.robotparser.RobotFileParser(); rp.parse(txt.splitlines()); break
            except Exception:
                continue
        robo[d] = rp
    def escondido(u):
        rp = robo.get(urllib.parse.urlparse(u).netloc)
        return rp is not None and not rp.can_fetch('*', u)
    expostos = sorted(u for u in publicos if escondido(u))  # publico mas o robots.txt mandava nao entrar
    esc = htmllib.escape
    lista = lambda us, cls='': ''.join(f'<li class="{cls}"><a href="{esc(u)}" target="_blank" rel="noopener noreferrer">{esc(u)}</a></li>' for u in us) or '<li><small>nenhum</small></li>'
    html = (f'<!doctype html><meta charset="utf-8"><title>Auditoria de exposicao</title><style>{ESQUELETO_CSS}'
            '.alerta{color:#b91c1c;font-weight:600}li.exp{background:#fef2f2}</style>'
            '<header><h1>Auditoria de exposicao</h1><p>So o que ja estava acessivel. Rode no site que voce controla.</p></header><main>'
            f'<div class="arvore"><h2 class="{"alerta" if expostos else ""}">Exposto apesar do robots.txt ({len(expostos)})</h2>'
            f'<p><small>paginas que o robots.txt mandava esconder, mas responderam publicamente -- o classico "escondi no robots e deixei aberto"</small></p>'
            f'<ul>{lista(expostos, "exp")}</ul>'
            f'<h2>Publico sem login ({len(publicos)})</h2><ul>{lista(sorted(publicos))}</ul>'
            f'<h2>Protegido (pediu login / recusou: 401/403) ({len(protegidos)})</h2><ul>{lista(sorted(protegidos))}</ul></div></main>')
    open(os.path.join(raiz, 'auditoria.html'), 'w', encoding='utf-8').write(html)
    log(f'AUDITORIA: {len(publicos)} publicos, {len(expostos)} expostos apesar do robots.txt (veja auditoria.html)')


def gerar_indice(raiz, inicio, origem, nao_copiados=None, origem_link=None):
    """espelho/index.html (o site em tela cheia), espelho/mapa.html (esqueleto) e, na pasta escolhida,
    os atalhos 'Abrir site.html', 'Esqueleto do site.html' e 'Abrir site completo.bat'"""
    esc, arvore, grupo_de = htmllib.escape, {}, {e: g for g, es in GRUPOS.items() for e in es}
    contagem, total, qtd = {}, 0, 0
    for d, ds, fs in os.walk(raiz):
        ds[:] = sorted(x for x in ds if x != '.painel')
        for f in sorted(fs):
            if (d == raiz and f in ('index.html', 'mapa.html', 'nao_baixado.html')) or f.endswith('.part'):
                continue
            c = os.path.join(d, f)
            no = arvore
            for parte in os.path.relpath(d, raiz).split(os.sep):
                if parte != '.':
                    no = no.setdefault(parte + '/', {})
            g = grupo_de.get(extensao(c.replace(os.sep, '/')), 'Outros formatos')
            no.setdefault('', []).append((c, g))
            contagem[g] = contagem.get(g, 0) + 1
            total, qtd = total + os.path.getsize(c), qtd + 1
    rel = lambda c: urllib.parse.quote(os.path.relpath(c, raiz).replace(os.sep, '/'))

    def desenha(no):
        partes = []
        for nome in sorted(k for k in no if k):
            dentro = desenha(no[nome])
            partes.append(f'<details{" open" if no is arvore else ""}><summary>{esc(nome)} <small>{dentro.count("<li ")} arquivo{"s" if dentro.count("<li ") != 1 else ""}</small></summary>{dentro}</details>')
        if no.get(''):
            partes.append('<ul>' + ''.join(
                f'<li data-b="{esc((os.path.basename(c) + " " + (origem.get(c) or "")).lower())}" data-g="{esc(g)}">'
                f'<a href="{rel(c)}">{esc(os.path.basename(c))}</a> <small>{tamanho(os.path.getsize(c))}'
                + (f' &middot; {esc(origem[c])}' if origem.get(c) else '') + '</small></li>' for c, g in no['']) + '</ul>')
        return ''.join(partes)

    tem_inicio = inicio and os.path.exists(inicio)
    nao_copiados, origem_link = nao_copiados or {}, origem_link or {}
    if nao_copiados:  # o que ficou de fora, com o link direto para inspecionar no site ao vivo
        contagem['Não copiados'] = len(nao_copiados)
        nao_html = (f'<details class="nao"><summary>Não copiados <small>{len(nao_copiados)} &middot; o link abre o site ao vivo</small></summary><ul>'
                    + ''.join(f'<li data-b="{esc((u + " " + m + " " + (origem_link.get(u) or "")).lower())}" data-g="Não copiados">'
                              f'<a href="{esc(u)}" target="_blank" rel="noopener noreferrer">{esc(u)} &#8599;</a> <small>{esc(m)}'
                              + (f' &middot; achado em: <a href="{esc(origem_link[u])}" target="_blank" rel="noopener noreferrer">{esc(origem_link[u])}</a>' if origem_link.get(u) else '')
                              + '</small></li>' for u, m in sorted(nao_copiados.items(), key=lambda x: (x[1], x[0])))
                    + '</ul></details>')
    chips = ''.join(f'<button class="chip" data-g="{esc(g)}">{esc(g)} {n}</button>' for g, n in sorted(contagem.items(), key=lambda x: -x[1]))
    open(os.path.join(raiz, 'mapa.html'), 'w', encoding='utf-8').write(
        f'<!doctype html><meta charset="utf-8"><title>Esqueleto do site</title><style>{ESQUELETO_CSS}</style>'
        f'<header><h1>Esqueleto do site</h1><p>{qtd} arquivos &middot; {tamanho(total)}</p></header><main>'
        f'<div class="barra"><input id="q" placeholder="Buscar arquivo ou endereço..." autofocus>'
        + (f'<a class="botao" href="{rel(inicio)}">Abrir site</a>' if tem_inicio else '') + f'</div><div class="chips">{chips}</div>'
        f'<div class="arvore">{desenha(arvore) or "<p>Nenhum arquivo.</p>"}{nao_html if nao_copiados else ""}</div></main><script>{ESQUELETO_JS}</script>')
    open(os.path.join(raiz, 'index.html'), 'w', encoding='utf-8').write(
        redireciona(rel(inicio), 'Abrir site') if tem_inicio else redireciona('mapa.html', 'Inicio nao baixado: veja o esqueleto'))
    pasta = os.path.dirname(os.path.abspath(raiz))
    nome = os.path.basename(os.path.abspath(raiz))
    for arquivo, conteudo in (('Abrir site.html', redireciona(nome + '/index.html', 'Abrir site')),
                              ('Esqueleto do site.html', redireciona(nome + '/mapa.html', 'Esqueleto do site'))):
        open(os.path.join(pasta, arquivo), 'w', encoding='utf-8').write(conteudo)
    open(os.path.join(pasta, 'Abrir site completo.bat'), 'w', encoding='utf-8', newline='').write(BAT_COMPLETO.replace('espelho', nome, 1))


def espelhar(urls, raiz, log, parar, profundidade=3, limite=200, mesmo_site=True, filtros='', max_mb=500,
             conexoes=4, pausa=0.3, robots=True, reescrever=True, gerar_zip=True, ext_excluidas=(), outros=True, extras=(),
             sitemap=True, formularios=False, cookies=None, bloquear=BLOQUEADOS, atualizar=False, recursos_fora=True, leitura=False, so_faltou=False, renderizar=False, prof_fora=1, auditoria=False):
    os.makedirs(raiz, exist_ok=True)
    log_dns[0] = log
    painel = os.path.join(raiz, '.painel')  # estado do espelho: o que ja baixou (para atualizar) e as paginas originais
    os.makedirs(painel, exist_ok=True)
    try:
        estado = json.load(open(os.path.join(painel, 'estado.json'), encoding='utf-8'))
    except (OSError, ValueError):
        estado = {}
    tinha_antes = set(estado)  # o que ja existia: para listar so o que entrou nesta rodada
    if so_faltou:  # nao revarre o site: pega so os enderecos que ficaram na falhas.txt da ultima rodada
        linhas = (open(os.path.join(painel, 'falhas.txt'), encoding='utf-8').read().splitlines()
                  if os.path.exists(os.path.join(painel, 'falhas.txt')) else [])
        todas = [L.split('  ', 1)[0].strip() for L in linhas if L[:4].lower() == 'http']
        urls = [u for u in todas if not pulavel(u)]  # ignora o lixo conhecido mesmo numa falhas.txt antiga
        profundidade, sitemap = 0, False  # nao segue links nem sitemap: so a lista do que faltou
        ignorados = len(todas) - len(urls)
        log(f'só o que faltou: {len(urls)} endereços a tentar' + (f' ({ignorados} ignorados: nunca são arquivo real)' if ignorados else ''))
    original = lambda dest: os.path.join(painel, 'orig', os.path.relpath(dest, raiz))
    frescos, falhas, pai, palpites, certos = set(), {}, {}, set(), set()  # pai: bases das paginas que carregaram cada script
    cookies = cookies or {}
    bloquear = {re.sub(r'^(https?://)?(www\.)?', '', b.strip().lower()).split('/')[0] for b in bloquear if b.strip()}
    dominios = {urllib.parse.urlparse(u).netloc for u in urls}
    render = Renderizador(log, cookies, min(conexoes, 4)) if renderizar else None  # shortcut: no maximo 4 navegadores (memoria)

    def cab(u, extra=None):
        """cabecalhos; junta o cookie da sessao (JAR) com o cookie do login do dominio (areas que pedem login)"""
        h = {'User-Agent': UA}
        req = urllib.request.Request(u)
        JAR.add_cookie_header(req)  # cookies que o site mandou durante o download
        d = urllib.parse.urlparse(u).netloc
        login = next((ck for dom, ck in cookies.items() if d == dom or d.endswith('.' + dom)), '')
        junto = '; '.join(x for x in (req.get_header('Cookie'), login) if x)
        if junto:
            h['Cookie'] = junto
        if extra:
            h.update(extra)
        return h
    filtros = '\n'.join(('+*' + f.strip() if f.strip().startswith('.') else f) for f in filtros.splitlines())  # '.lua' means +*.lua
    mais = [f[1:].strip() for f in filtros.splitlines() if f.startswith('+')]
    menos = [f[1:].strip() for f in filtros.splitlines() if f.startswith('-')]
    rp, lock, ultimo, atraso, saltos = {}, threading.Lock(), {}, {}, {}  # atraso: Crawl-delay; saltos: paginas seguidas fora do site  # ultimo pedido de cada site: a pausa vale por site
    feitos, mapa, baixados, origem_link = set(urls), {}, [0], {}  # origem_link: 1a pagina onde cada link apareceu

    def porque(u):
        """'' se pode baixar; senao o motivo (aparece no esqueleto, em 'Nao copiados')"""
        e = extensao(u)
        if e in ext_excluidas or (e not in CONHECIDAS and not outros):
            return f'tipo .{e} desmarcado' if e else 'tipo desmarcado'
        h = urllib.parse.urlparse(u).netloc.lower().split(':')[0]
        if urllib.parse.urlparse(u).netloc not in dominios and any(h == d or h.endswith('.' + d) or (d.endswith('.*') and h.startswith(d[:-1])) for d in bloquear):
            return 'site bloqueado (anúncio, rede social ou sua lista)'
        if any(fnmatch.fnmatch(u, m) or fnmatch.fnmatch(u.split('//', 1)[-1], m) for m in menos):
            return 'filtro -'
        p = urllib.parse.urlparse(u)
        if e in GRUPOS['Páginas'] and not DIRETO.match(u) and PERIGOSOS.search(p.path + '?' + p.query):  # nunca clica em sair/excluir (derruba o login ou apaga algo)
            return 'link de sair/excluir (nunca abre)'
        if any(fnmatch.fnmatch(u, m) or fnmatch.fnmatch(u.split('//', 1)[-1], m) for m in mais):
            return ''
        if mesmo_site and p.netloc not in dominios and not (
                recursos_fora and ((e in CONHECIDAS and e not in GRUPOS['Páginas']) or re.search(r'/css2?$', p.path) or DIRETO.match(u))):  # shortcut: /css e /css2 = Google Fonts sem extensao
            return 'página de outro site ("Só o mesmo site" marcado)'  # arquivos que a pagina usa (CDN, fontes, icones) vem sempre
        if robots and (e in GRUPOS['Páginas'] or p.netloc in dominios):  # arquivo da pagina vindo de CDN: o navegador tambem nao consulta robots
            h = urllib.parse.urlparse(u)
            with lock:
                if h.netloc not in rp:
                    endereco, r = f'{h.scheme}://{h.netloc}/robots.txt', urllib.robotparser.RobotFileParser()
                    try:  # com o mesmo nome e cookies do resto: o leitor do Python ("Python-urllib") e recusado por Cloudflare
                        r.parse(NAVEGADOR.open(urllib.request.Request(endereco, headers=cab(endereco)), timeout=20).read().decode('utf-8', 'replace').splitlines())
                    except Exception:
                        r = None  # robots.txt com erro ou inexistente: nada proibido (como o Google faz)
                    rp[h.netloc] = r
                    if r and r.crawl_delay('leitura-pessoal'):  # o site pede intervalo entre pedidos
                        atraso[h.netloc] = min(30.0, float(r.crawl_delay('leitura-pessoal')))
            r = rp[h.netloc]
            if r and not r.can_fetch('leitura-pessoal', u):  # casa as regras de User-agent: * do site
                return 'proibido pelo robots.txt do site'
        return ''

    def permitido(u):
        return not porque(u)

    def nome_real(u, dest, r):
        """nome pelo servidor: download.php?id=3 que manda um .zip vira arquivo.zip, nao .html"""
        nome = nome_do_cabecalho(r.headers)
        tipo = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        if nome:
            novo = os.path.join(os.path.dirname(dest), nome)
            if os.path.exists(novo):  # outro endereco ja usou esse nome
                b, e = os.path.splitext(nome)
                novo = os.path.join(os.path.dirname(dest), b + '_' + hashlib.md5(u.encode()).hexdigest()[:6] + e)
            return novo
        if extensao(u) in GRUPOS['Páginas'] and tipo and 'html' not in tipo and dest.endswith('.html'):
            return dest[:-5] + (mimetypes.guess_extension(tipo) or '.bin')
        return dest

    def pegar(u):
        """(caminho, ja_tinha) -- baixa em pedacos; continua um .part cortado; no modo atualizar so baixa o que mudou"""
        info = estado.get(u, {})
        dest = os.path.join(raiz, info['dest']) if info.get('dest') else caminho_local(raiz, u)
        if os.path.exists(dest) and not atualizar:
            return dest, True
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        site, part = urllib.parse.urlparse(u).netloc, dest + '.part'
        for tentativa in range(3):
            if parar.is_set():
                return None, False
            with lock:
                pz = max(pausa, atraso.get(site, 0.0))
                espera = ultimo.get(site, 0.0) + pz - time.time()
                ultimo[site] = max(time.time(), ultimo.get(site, 0.0)) + (pz if espera > 0 else 0)
            if espera > 0:
                time.sleep(espera)
            extra, ja_part = {}, os.path.getsize(part) if os.path.exists(part) else 0
            if ja_part:
                extra['Range'] = f'bytes={ja_part}-'
            elif extensao(u) in LER or extensao(u) in GRUPOS['Páginas']:  # texto vem compactado (menos internet); .gz/.zip nunca
                extra['Accept-Encoding'] = 'gzip'
            if os.path.exists(dest):  # modo atualizar: o servidor responde 304 se nao mudou
                extra.update({k: info[c] for k, c in (('If-None-Match', 'etag'), ('If-Modified-Since', 'lm')) if info.get(c)})
            try:
                r = NAVEGADOR.open(urllib.request.Request(u, headers=cab(u, extra)), timeout=30)
                continua = r.status == 206
                total = ja_part if continua else 0
                if int(r.headers.get('Content-Length') or 0) + total > max_mb << 20:
                    log(f'pulei {u}: maior que {max_mb} MB')
                    return None, False
                final = dest if info.get('dest') else nome_real(u, dest, r)
                if extensao(final.replace(os.sep, '/')) in ext_excluidas:  # so o servidor revelou o tipo (download.php -> .zip)
                    log(f'pulei {u}: formato .{extensao(final.replace(os.sep, "/"))} desmarcado')
                    return None, False
                if continua:
                    log(f'continuando {u} de {ja_part >> 10} KB')
                dz = zlib.decompressobj(16 + zlib.MAX_WBITS) if (r.headers.get('Content-Encoding') or '').lower() == 'gzip' else None
                with open(part, 'ab' if continua else 'wb') as f:
                    while chunk := r.read(1 << 20):
                        chunk = dz.decompress(chunk) if dz else chunk
                        total += len(chunk)
                        if total > max_mb << 20:
                            log(f'cortei {u} em {max_mb} MB')
                            break
                        f.write(chunk)
                    if dz:
                        f.write(dz.flush())
                os.replace(part, final)
                with lock:
                    estado[u] = {'dest': os.path.relpath(final, raiz), 'etag': r.headers.get('ETag'), 'lm': r.headers.get('Last-Modified')}
                    frescos.add(final)
                return final, False
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    return dest, True
                if e.code == 416:  # o .part ja estava completo ou mudou: recomeca
                    os.remove(part)
                    continue
                if e.code in (429, 503) and tentativa < 2:  # o servidor pediu calma: espera o que ele mandou (ate 60 s)
                    ra = e.headers.get('Retry-After') or ''
                    time.sleep(min(60, int(ra) if ra.isdigit() else 5))
                    continue
                if e.code in (403, 404, 410) and u in palpites and u not in certos:
                    return None, False
                if tentativa == 2 or e.code in (403, 404, 410):
                    log(f'falhou {u}: {e}')
                    falhas[u] = e.code
                    return None, False
            except Exception as e:
                if tentativa == 2:
                    log(f'falhou {u}: {e}')
                    falhas[u] = str(e)
                    return None, False
            time.sleep(1 + tentativa)
        return None, False

    def enviar_formularios(u):
        """so no site do proprio usuario: abre a pagina de novo (token novo) e aperta os botoes de download"""
        try:
            texto = NAVEGADOR.open(urllib.request.Request(u, headers=cab(u)), timeout=30).read().decode('utf-8', 'replace')
        except Exception as e:
            log(f'falhou {u}: {e}')
            return
        for acao, dados in formularios_de_download(texto, u):
            if urllib.parse.urlparse(acao).netloc not in dominios or not permitido(acao):
                continue
            time.sleep(pausa)
            try:
                r = NAVEGADOR.open(urllib.request.Request(acao, data=urllib.parse.urlencode(dados).encode(),
                                                          headers=cab(acao, {'Referer': u})), timeout=30)
                nome = nome_do_cabecalho(r.headers)
                if not nome:
                    continue  # nao era download (pagina comum)
                dest = os.path.join(os.path.dirname(caminho_local(raiz, u)), nome)
                dados_arq = r.read((max_mb << 20) + 1)
                if len(dados_arq) > max_mb << 20:
                    log(f'pulei {acao}: maior que {max_mb} MB')
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                open(dest, 'wb').write(dados_arq)
                with lock:
                    baixados[0] += 1
                    n = baixados[0]
                log(f'ok ({n}) formulario {acao} -> {nome}')
            except Exception as e:
                log(f'falhou formulario {acao}: {e}')

    def tratar(item):
        u, prof = item
        dest, ja = pegar(u)
        if not dest:
            return []
        with lock:
            mapa[u] = dest
            baixados[0] += 1
            n = baixados[0]
        log(f'{"(ja tinha) " if ja else ""}ok ({n}) {u}')
        if extensao(dest.replace(os.sep, '/')) not in LER or os.path.getsize(dest) > 20 << 20:  # shortcut: nao procura links em texto > 20 MB
            return []
        try:  # pagina que ja tinha foi reescrita para offline: os links certos estao na copia original
            texto = open(original(dest) if ja and os.path.exists(original(dest)) else dest, encoding='utf-8', errors='replace').read()
        except OSError:
            return []
        html = dest.lower().endswith(('.html', '.htm'))
        if html and formularios:
            enviar_formularios(u)
        novos, pedidos_js = [], []
        if html and render and not ja and (feito := render(u)):  # grava o que o JavaScript montou (texto, listas, imagens)
            texto, pedidos_js = feito
            texto = re.sub(r'''(<meta\b[^>]*charset\s*=\s*["']?)[\w-]+''', r'\1utf-8', texto, count=1, flags=re.I)  # o navegador ja entrega em unicode
            grava_txt(dest, texto, 'utf-8')
        nofollow = html and robots and re.search(r'''<meta\b[^>]*\bname\s*=\s*["']?robots\b[^>]*\bnofollow''', texto, re.I)
        if html:
            base = base_de(texto, u)
        achados = links(texto, u, extras) + [normal(x.split('#')[0]) for x in pedidos_js if x.startswith('http')]
        if extensao(u) in ('js', 'mjs', 'cjs', 'json'):
            # endereco achado dentro de script e palpite (404/403 nao conta como falha); caminho relativo:
            # fetch('x') vale a partir da pagina e import 'x' a partir do proprio .js, entao tenta os dois
            achados = list(dict.fromkeys(achados + [v for b in sorted(pai.get(u, ())) for v in links(texto, b, extras)]))
            with lock:
                palpites.update(achados)
        else:
            with lock:
                certos.update(achados)
        for v in achados:
            if html:
                with lock:
                    pai.setdefault(v, set()).add(base)
                    origem_link.setdefault(v, u)
            eh_pagina = extensao(v) in GRUPOS['Páginas'] and not DIRETO.match(v)  # so pagina conta profundidade; arquivo de qualquer formato sempre vem
            if eh_pagina and prof >= profundidade:  # vale tambem para pagina citada dentro de .js/.json
                continue
            if eh_pagina and nofollow:  # a pagina pede para nao seguir os links dela; arquivos que ela usa vem
                continue
            if eh_pagina and urllib.parse.urlparse(v).netloc not in dominios:  # pagina de outro site: conta os saltos para fora
                s = saltos.get(u, 0) + 1
                if s > prof_fora:
                    continue
                with lock:
                    saltos[v] = min(s, saltos.get(v, s))
            novos.append((v, prof + 1 if eh_pagina else prof))
        return novos

    nivel = [(u, 0) for u in urls]
    for base in (set() if so_faltou else {f'{urllib.parse.urlparse(u).scheme}://{urllib.parse.urlparse(u).netloc}' for u in urls}):
        for meta in ('/robots.txt', '/sitemap.xml'):  # guarda os arquivos do proprio site (nao passam pelo robots)
            if base + meta not in feitos:
                feitos.add(base + meta)
                palpites.add(base + meta)  # robots/sitemap que nao existem: 404 silencioso, sem virar falha
                nivel.append((base + meta, 0))
    if sitemap:  # sitemap.xml lista paginas publicas que nenhum link mostra
        for v in ler_sitemaps({f'{urllib.parse.urlparse(u).scheme}://{urllib.parse.urlparse(u).netloc}' for u in urls}, log):
            if v not in feitos and permitido(v):
                feitos.add(v)
                nivel.append((v, 0))
    with ThreadPoolExecutor(conexoes) as pool:
        # fila continua: cada conexao pega o proximo assim que termina (um arquivo lento nao segura os outros)
        fila, pend = deque(nivel), set()
        while (fila or pend) and not parar.is_set():
            while fila and len(pend) < conexoes * 2 and baixados[0] + len(pend) < limite:
                pend.add(pool.submit(tratar, fila.popleft()))
            if not pend:
                break  # limite atingido
            prontos, pend = wait(pend, return_when=FIRST_COMPLETED)
            for f in prontos:
                for v, p in f.result():
                    with lock:
                        if v in feitos:
                            continue
                        feitos.add(v)
                    if permitido(v):
                        fila.append((v, p))
        repetir = [(u, profundidade) for u, c in falhas.items() if c not in (403, 404, 410)]  # erro de rede: tenta de novo uma vez
        if repetir and not parar.is_set():
            log(f'aviso: tentando de novo {len(repetir)} que falharam...')
            for u, _ in repetir:
                del falhas[u]
            list(pool.map(tratar, repetir))  # shortcut: nao segue links novos de quem so deu certo na repeticao
        # 403/429 em arquivo (nao pagina) = CDN estrangulou por excesso de pedidos; espera e tenta um de cada vez
        estrangulados = [(u, profundidade) for u, c in falhas.items() if c in (403, 429) and extensao(u) not in GRUPOS['Páginas']]
        if estrangulados and not parar.is_set():
            log(f'aviso: {len(estrangulados)} arquivos recusados por excesso de pedidos; esperando e tentando devagar...')
            time.sleep(10)
            for u, _ in estrangulados:
                del falhas[u]
            for item in estrangulados:
                if parar.is_set():
                    break
                tratar(item)
    if render:
        render.fechar()
    nao_copiados = {}  # links que a reescrita mandou para nao_baixado.html
    if reescrever:
        fora = os.path.join(raiz, 'nao_baixado.html')
        open(fora, 'w', encoding='utf-8').write(NAO_BAIXADO)
        reescritos = set()
        for u, dest in mapa.items():
            if not dest.lower().endswith(('.html', '.htm', '.xhtml', '.css')) or dest in reescritos:
                continue  # '/' e '/index.html' sao o mesmo arquivo: reescrever de novo estragaria os caminhos ja trocados
            reescritos.add(dest)
            if dest in frescos:  # guarda o original antes de reescrever (para atualizar depois)
                os.makedirs(os.path.dirname(original(dest)), exist_ok=True)
                texto, enc = ler_txt(dest)
                grava_txt(original(dest), texto, enc)
            elif os.path.exists(original(dest)):
                texto, enc = ler_txt(original(dest))
            else:
                continue  # ja reescrito por uma versao antiga do painel
            b = base_de(texto, u)
            pagina_html = dest.lower().endswith(('.html', '.htm', '.xhtml'))
            if leitura and pagina_html:
                def mostra_imagem(m):  # imagem preguicosa: poe o endereco real (data-src) no src, senao ela so aparece com JS
                    tag = m.group(0)
                    ds = re.search(r'\bdata-(?:src|original|lazy-src)\s*=\s*(["\'])(.*?)\1', tag, re.I)
                    if not ds:
                        return tag
                    if re.search(r'\bsrc\s*=', tag, re.I):
                        return re.sub(r'\bsrc\s*=\s*(["\']).*?\1', 'src=' + ds.group(1) + ds.group(2) + ds.group(1), tag, count=1, flags=re.I)
                    return tag[:-1] + ' src=' + ds.group(1) + ds.group(2) + ds.group(1) + '>'
                texto = re.sub(r'<img\b[^>]*>', mostra_imagem, texto, flags=re.I)
                texto = re.sub(r'</?noscript[^>]*>', '', texto, flags=re.I)  # mostra o conteudo que o site guardava para quem nao tem JS

            def local(v):
                """caminho local do link; o que nao foi baixado vai para nao_baixado.html (nunca abre a internet)"""
                alvo = urllib.parse.urljoin(b, htmllib.unescape(v.strip()))
                alvo, _, frag = alvo.partition('#')
                alvo = normal(alvo)
                if alvo in mapa:
                    return urllib.parse.quote(os.path.relpath(mapa[alvo], os.path.dirname(dest)).replace(os.sep, '/')) + ('#' + frag if frag else '')  # % e espaco no nome
                if alvo.startswith('http'):
                    cheio = re.match(r'(.*/revision/latest)(?:/.*)?$', alvo)  # Fandom: faltou o thumbnail? usa o full-size (mesma imagem) que ja esta na pasta
                    if cheio and cheio.group(1) != alvo and cheio.group(1) in mapa:
                        return urllib.parse.quote(os.path.relpath(mapa[cheio.group(1)], os.path.dirname(dest)).replace(os.sep, '/'))
                    nao_copiados[alvo] = None
                    return urllib.parse.quote(os.path.relpath(fora, os.path.dirname(dest)).replace(os.sep, '/')) + '#' + urllib.parse.quote(alvo, safe='')
                return v  # data:, mailto:, javascript:
            def troca(m):
                v = next(x for x in m.groups() if x)
                return m.group(0).replace(v, local(v))
            def troca_set(m):  # srcset="a.jpg 1x, b.jpg 2x"
                partes = []
                for c in m.group(1).split(','):
                    d = c.strip().split(None, 1)
                    d[0:1] = [local(d[0])] if d else []
                    partes.append(' '.join(d))
                return m.group(0).replace(m.group(1), ', '.join(partes))
            novo = re.sub(r'<base\b[^>]*>', '', SRCSET.sub(troca_set, ATTR.sub(troca, PRECONEXAO.sub('', texto))), flags=re.I)  # links ja viraram caminhos locais
            if leitura and pagina_html:  # tira os scripts (anuncio, anti-adblock, pop-ups): wiki e so texto e imagem
                novo = re.sub(r'<script\b[^>]*>.*?</script>', '', novo, flags=re.I | re.S)
                novo = re.sub(r'<script\b[^>]*>', '', novo, flags=re.I)
            if not dest.lower().endswith('.css'):
                novo = re.sub(r'''\s(?:integrity|nonce)\s*=\s*("[^"]*"|'[^']*')''', '', novo, flags=re.I)  # o arquivo local mudou: a assinatura original bloquearia ele
                novo, n = re.subn(r'<head\b[^>]*>', lambda h: h.group(0) + TRAVA, novo, count=1, flags=re.I)
                novo = novo if n else TRAVA + novo
            if novo != ler_txt(dest)[0]:
                grava_txt(dest, novo, enc)
    json.dump(estado, open(os.path.join(painel, 'estado.json'), 'w', encoding='utf-8'))
    open(os.path.join(painel, 'falhas.txt'), 'w', encoding='utf-8').write(
        ''.join(f'{u}  -> {motivo_falha(u, c)}' + (f'  [achado em: {origem_link[u]}]' if origem_link.get(u) else '') + '\n' for u, c in falhas.items()))
    if falhas:
        log(f'aviso: {len(falhas)} nao baixaram (lista em {os.path.join(painel, "falhas.txt")})')
    novos = [u for u in mapa if u not in tinha_antes]  # arquivos que entraram agora
    open(os.path.join(painel, 'novos.txt'), 'w', encoding='utf-8').write('\n'.join(sorted(novos)))
    log(f'{len(novos)} arquivos novos nesta rodada (lista em {os.path.join(painel, "novos.txt")})')
    entradas_bloqueadas = [u for u in urls if u in falhas and isinstance(falhas[u], int) and falhas[u] in (403, 401, 429)]
    if entradas_bloqueadas and baixados[0] > len(urls):  # a entrada caiu, mas o sitemap/links trouxeram o resto
        log(f'aviso: a pagina de entrada foi bloqueada ({entradas_bloqueadas[0]}), mas segui pelo sitemap e peguei {baixados[0]} arquivos -- isso e normal em alguns sites')
    elif entradas_bloqueadas:  # so a entrada, e nada mais veio
        log(f'aviso: a entrada foi bloqueada e nao achei o sitemap. Tente colar uma pagina interna (ex.: {urls[0].rstrip("/")}/wiki ou outra pagina do site)')
    motivos = {}
    for u in set(falhas) | set(nao_copiados):
        motivos[u] = (f'erro {falhas[u]}' if isinstance(falhas[u], int) else 'erro de rede') if u in falhas else \
            porque(u) or 'fora do limite (profundidade ou Arquivos máx.)'
    if auditoria:
        protegidos = [u for u, c in falhas.items() if isinstance(c, int) and c in (401, 403)]
        gerar_auditoria(raiz, set(mapa), protegidos, dominios, cab, log)
    gerar_indice(raiz, mapa.get(urls[0]) or caminho_local(raiz, urls[0]), {d: u for u, d in mapa.items()}, motivos, origem_link)
    if gerar_zip:
        with zipfile.ZipFile(raiz.rstrip('/\\') + '.zip', 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for d, ds, fs in os.walk(raiz):
                ds[:] = [x for x in ds if x != '.painel']
                for f in fs:
                    if f.endswith('.part'):  # download cortado: nao e arquivo de verdade
                        continue
                    z.write(os.path.join(d, f), os.path.relpath(os.path.join(d, f), raiz))
    log(f'PRONTO: {baixados[0]} arquivos em {raiz}' + (' + .zip' if gerar_zip else '') + (' (parado)' if parar.is_set() else ''))
    log_dns[0] = None  # nao usar este log depois que o espelhar acabou


# opcoes da janela; e o que vai num perfil (cookies nunca sao salvos)
PADRAO = dict(enderecos='', pasta='', prof=3, prof_fora=1, audit=False, lim=6000, mb=5000, con=2, pausa=1.0, mesmo=True, fora=True, lixo=True, robots=True, rew=True, zip=True,
              sitemap=True, form=False, render=False, atualizar=False, separados=False, so_coladas=False, leitura=False, so_faltou=False, desmarcados=[], filtros='', extras='')


def ler(arquivo):
    try:
        return open(arquivo, encoding='utf-8').read()
    except OSError:
        return ''


def separar(urls, pasta, separados):
    """[(enderecos, pasta do espelho)]: tudo num espelho so, ou um por site (pasta/site.com/espelho) para rodar ao mesmo tempo"""
    grupos = {}
    for u in urls:
        grupos.setdefault(urllib.parse.urlparse(u).netloc, []).append(u)
    if not separados or len(grupos) < 2:
        return [(urls, os.path.join(pasta, 'espelho'))]
    return [(us, os.path.join(pasta, re.sub(r'[<>:"|?*\\/]', '_', site), 'espelho')) for site, us in grupos.items()]


def argumentos(cfg):
    """opcoes (da janela ou de um perfil) -> ([(enderecos, pasta do espelho)], kwargs do espelhar)"""
    c = {**PADRAO, **cfg}
    urls = [u.strip() for u in c['enderecos'].splitlines() if u.strip().startswith('http')]
    sem_formato = ler(LISTA_FORMATOS)
    return separar(urls, c['pasta'], c['separados']), dict(
        limite=int(c['lim']), prof_fora=int(c['prof_fora']), mesmo_site=c['mesmo'], filtros=c['filtros'], max_mb=int(c['mb']),
        conexoes=int(c['con']), pausa=float(c['pausa']), robots=c['robots'], reescrever=c['rew'], gerar_zip=c['zip'],
        profundidade=0 if c['so_coladas'] else int(c['prof']), sitemap=c['sitemap'] and not c['so_coladas'],
        formularios=c['form'], renderizar=c['render'], auditoria=c['audit'], atualizar=c['atualizar'] or c['so_faltou'], so_faltou=c['so_faltou'], recursos_fora=c['fora'], leitura=c['leitura'], outros='Outros formatos' not in c['desmarcados'],
        ext_excluidas={e for n in c['desmarcados'] if n in GRUPOS for e in GRUPOS[n]}
        | {x.lower().lstrip('*.') for x in re.split(r'[\s,;]+', sem_formato) if x.strip('*.')},
        extras=[x for x in re.split(r'[\s,;]+', c['extras']) if x],
        bloquear=(BLOQUEADOS if c['lixo'] else set()) | {L.split('#')[0] for L in ler(LISTA_BLOQUEIO).splitlines()})


def avisar(texto):
    """balao de aviso do Windows (sem instalar nada); em outro sistema so escreve na tela"""
    print(texto)
    if os.name == 'nt':
        t = texto.replace("'", "''")
        subprocess.Popen(['powershell', '-NoProfile', '-WindowStyle', 'Hidden', '-Command',
                          "Add-Type -AssemblyName System.Windows.Forms; $n = New-Object System.Windows.Forms.NotifyIcon; "
                          "$n.Icon = [System.Drawing.SystemIcons]::Information; $n.Visible = $true; "
                          f"$n.ShowBalloonTip(10000, 'Painel de Download', '{t}', 'Info'); Start-Sleep 11; $n.Dispose()"],
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def rodar_perfis(nomes, atualizar=False):
    """sem janela, um perfil depois do outro (fila); e o que o agendamento do Windows chama"""
    for nome in nomes:
        cfg = json.loads(ler(os.path.join(PERFIS, nome + '.json')) or 'null')
        if not cfg:
            avisar(f'perfil nao encontrado: {nome}')
            continue
        alvos, kw = argumentos({**cfg, 'atualizar': atualizar or cfg.get('atualizar')})

        def um(urls, raiz):
            os.makedirs(os.path.join(raiz, '.painel'), exist_ok=True)
            ultimo, falhou = [''], [0]
            with open(os.path.join(raiz, '.painel', 'ultimo.log'), 'w', encoding='utf-8') as arq:
                def log(msg):
                    print(msg); arq.write(msg + '\n'); ultimo[0] = msg
                    falhou[0] += msg.startswith('falhou')
                espelhar(urls, raiz, log, threading.Event(), **kw)
            avisar(f'{nome}: ' + ultimo[0].replace('PRONTO: ', '') + (f' ({falhou[0]} falharam)' if falhou[0] else ''))
        sites = [threading.Thread(target=um, args=a) for a in alvos]  # sites separados rodam ao mesmo tempo
        for t in sites:
            t.start()
        for t in sites:
            t.join()


def agendar(nome, quando, dia, hora):
    """cria a tarefa no Agendador do Windows: roda o perfil sozinho, so baixando o que mudou"""
    pyw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    exe = pyw if os.path.exists(pyw) else sys.executable  # pythonw: sem janela preta
    tarefa = f'Painel de Download - {nome}'
    if os.name != 'nt':
        m, h = hora.split(':')[1], hora.split(':')[0]
        return f'Sem Agendador do Windows aqui. No crontab: {int(m)} {int(h)} * * {"*" if quando == "DAILY" else dia} {exe} {os.path.abspath(__file__)} --perfil "{nome}" --atualizar'
    cmd = ['schtasks', '/Create', '/F', '/TN', tarefa, '/SC', quando, '/ST', hora,
           '/TR', f'"{exe}" "{os.path.abspath(__file__)}" --perfil "{nome}" --atualizar'] + (['/D', dia] if quando == 'WEEKLY' else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    return f'Agendado: "{tarefa}"' if r.returncode == 0 else 'Nao consegui agendar: ' + (r.stderr or r.stdout).strip()


def atualizar_do_github():
    """baixa a versao nova do GitHub, se substitui e reabre; silencioso se nao houver novidade/internet"""
    if os.environ.get('PAINEL_SEM_UPDATE'):  # ja reaberto nesta cadeia: nao tenta de novo (evita loop)
        return
    txt = versao_nova()
    if not txt:
        return
    try:
        open(os.path.abspath(__file__), 'w', encoding='utf-8').write(txt)
        os.environ['PAINEL_SEM_UPDATE'] = '1'
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__), *sys.argv[1:]])  # reabre ja com o codigo novo
    except Exception:
        pass  # sem permissao de escrita etc.: segue com a versao atual


def main():
    atualizar_do_github()
    COR = {'fundo': '#f4f6fa', 'cartao': '#ffffff', 'borda': '#dfe3ea', 'texto': '#1f2937', 'suave': '#6b7280',
           'destaque': '#2563eb', 'destaque2': '#1d4ed8', 'topo': '#111827', 'log': '#0f172a'}
    w = tk.Tk()
    w.title(f'Painel de Download v{VERSAO_PAINEL}')
    w.configure(bg=COR['fundo'])
    w.minsize(860, 640)
    fonte = ('Segoe UI', 10)
    st = ttk.Style(w)
    st.theme_use('clam')
    st.configure('.', font=fonte, background=COR['fundo'], foreground=COR['texto'])
    st.configure('Cartao.TFrame', background=COR['cartao'])
    st.configure('Cartao.TLabel', background=COR['cartao'])
    st.configure('Dica.TLabel', background=COR['cartao'], foreground=COR['suave'], font=('Segoe UI', 9))
    plano = dict(bordercolor=COR['borda'], lightcolor=COR['cartao'], darkcolor=COR['cartao'])  # tira o relevo 3D do tema
    st.configure('Cartao.TCheckbutton', background=COR['cartao'], indicatorbackground='white', indicatorforeground='white', indicatormargin=(0, 0, 6, 0))
    st.map('Cartao.TCheckbutton', background=[('active', COR['cartao'])], indicatorbackground=[('selected', COR['destaque']), ('active', '#e8efff')])
    st.configure('TNotebook', background=COR['fundo'], borderwidth=0, tabmargins=(0, 0, 0, 0), **plano)
    st.configure('TNotebook.Tab', padding=(18, 8), background=COR['fundo'], foreground=COR['suave'], borderwidth=0, **plano)
    st.map('TNotebook.Tab', background=[('selected', COR['cartao'])], foreground=[('selected', COR['destaque'])],
           lightcolor=[('selected', COR['cartao'])], bordercolor=[('selected', COR['borda'])])
    st.configure('TEntry', fieldbackground='white', padding=4, **plano)
    st.configure('TSpinbox', fieldbackground='white', padding=3, arrowsize=12, background=COR['cartao'], **plano)
    st.map('TEntry', bordercolor=[('focus', COR['destaque'])])
    st.map('TSpinbox', bordercolor=[('focus', COR['destaque'])])
    st.configure('TCombobox', padding=4, arrowsize=14, background=COR['cartao'], **plano)
    st.map('TCombobox', fieldbackground=[('readonly', 'white')], bordercolor=[('focus', COR['destaque'])])
    st.configure('TButton', padding=(16, 7), background=COR['cartao'], **plano)
    st.map('TButton', background=[('active', '#eef2f7')])
    st.configure('Acao.TButton', font=('Segoe UI', 10, 'bold'), foreground='white', background=COR['destaque'], padding=(26, 8),
                 bordercolor=COR['destaque'], lightcolor=COR['destaque'], darkcolor=COR['destaque'])
    st.map('Acao.TButton', background=[('disabled', '#93b4f5'), ('active', COR['destaque2'])],
           lightcolor=[('active', COR['destaque2'])], darkcolor=[('active', COR['destaque2'])], bordercolor=[('active', COR['destaque2'])])
    st.configure('Horizontal.TProgressbar', background=COR['destaque'], troughcolor=COR['borda'], borderwidth=0,
                 lightcolor=COR['destaque'], darkcolor=COR['destaque'], bordercolor=COR['borda'])

    topo = tk.Frame(w, bg=COR['topo'], padx=20, pady=12)
    topo.pack(fill='x')
    tk.Label(topo, text='Painel de Download', bg=COR['topo'], fg='white', font=('Segoe UI', 15, 'bold')).pack(anchor='w')
    tk.Label(topo, text=f'Copia sites e arquivos para abrir 100% offline  ·  v{VERSAO_PAINEL}', bg=COR['topo'], fg='#9ca3af', font=fonte).pack(anchor='w')
    corpo = ttk.Frame(w, padding=(16, 12, 16, 0))
    corpo.pack(fill='both', expand=True)

    def texto(pai, altura):
        return scrolledtext.ScrolledText(pai, height=altura, font=('Consolas', 10), relief='flat', bd=0, wrap='none',
                                         highlightthickness=1, highlightbackground=COR['borda'], highlightcolor=COR['destaque'])

    def rotulo(pai, titulo, dica=''):
        ttk.Label(pai, text=titulo, style='Cartao.TLabel', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(8, 0))
        if dica:
            ttk.Label(pai, text=dica, style='Dica.TLabel').pack(anchor='w', pady=(0, 3))

    # enderecos + pasta
    cartao = ttk.Frame(corpo, style='Cartao.TFrame', padding=(14, 4, 14, 12))
    cartao.pack(fill='x')
    rotulo(cartao, 'Endereços', 'um por linha, começando com http:// ou https://')
    caixa = texto(cartao, 3)
    caixa.pack(fill='x')
    rotulo(cartao, 'Salvar em')
    linha_pasta = ttk.Frame(cartao, style='Cartao.TFrame')
    linha_pasta.pack(fill='x')
    pasta_var = tk.StringVar()
    ttk.Entry(linha_pasta, textvariable=pasta_var).pack(side='left', fill='x', expand=True, ipady=3)
    ttk.Button(linha_pasta, text='Escolher...', command=lambda: pasta_var.set(filedialog.askdirectory(title='Pasta onde salvar o espelho') or pasta_var.get())).pack(side='left', padx=(8, 0))
    rotulo(cartao, 'Perfil', 'guarde as opções de um site com um nome; agende para atualizar sozinho')
    linha_perfil = ttk.Frame(cartao, style='Cartao.TFrame')
    linha_perfil.pack(fill='x')
    perfil = ttk.Combobox(linha_perfil, state='readonly', width=30)
    perfil.pack(side='left', ipady=2)
    botoes_perfil = {t: ttk.Button(linha_perfil, text=t) for t in ('Salvar perfil', 'Excluir', 'Agendar...')}
    for b in botoes_perfil.values():
        b.pack(side='left', padx=(8, 0))

    abas = ttk.Notebook(corpo)
    abas.pack(fill='x', pady=(12, 0))
    def aba(nome):
        f = ttk.Frame(abas, style='Cartao.TFrame', padding=(14, 4, 14, 12))
        abas.add(f, text=nome)
        return f

    # aba Geral: limites e opcoes
    geral = aba('Geral')
    rotulo(geral, 'Limites')
    linha = ttk.Frame(geral, style='Cartao.TFrame')
    linha.pack(anchor='w')
    campos = {}
    for i, (nome, chave, padrao, passo) in enumerate((('Profundidade', 'prof', 3, 1), ('Níveis fora do site', 'prof_fora', 1, 1), ('Arquivos máx.', 'lim', 6000, 50), ('MB por arquivo', 'mb', 5000, 50),
                                                      ('Conexões', 'con', 2, 1), ('Pausa (s)', 'pausa', 1.0, 0.1))):
        ttk.Label(linha, text=nome, style='Dica.TLabel').grid(row=0, column=i, sticky='w', padx=(0, 16))
        campos[chave] = ttk.Spinbox(linha, from_=0, to=99999, increment=passo, width=9)
        campos[chave].set(padrao)
        campos[chave].grid(row=1, column=i, sticky='w', padx=(0, 16))
    rotulo(geral, 'Opções')
    opcoes = ttk.Frame(geral, style='Cartao.TFrame')
    opcoes.pack(anchor='w')
    var = {k: tk.BooleanVar(value=True) for k in ('mesmo', 'fora', 'lixo', 'robots', 'rew', 'zip', 'sitemap', 'form', 'render', 'audit', 'atualizar', 'separados', 'so_coladas', 'leitura', 'so_faltou')}
    var['form'].set(False)
    var['render'].set(False)
    var['audit'].set(False)
    var['atualizar'].set(False)
    var['separados'].set(False)
    var['so_coladas'].set(False)
    var['leitura'].set(False)
    var['so_faltou'].set(False)
    for i, (k, t) in enumerate((('mesmo', 'Só o mesmo site (desmarque p/ seguir links de outros sites)'), ('fora', 'Arquivos da página mesmo de outro site (ícones, fontes, CDN)'),
                                ('rew', 'Reescrever links (abrir offline)'),
                                ('robots', 'Respeitar robots.txt'), ('zip', 'Gerar .zip no fim'), ('sitemap', 'Ler sitemap.xml'),
                                ('atualizar', 'Atualizar: baixar de novo só o que mudou no site'),
                                ('separados', 'Cada site numa cópia separada (todos ao mesmo tempo)'),
                                ('so_coladas', 'Só as páginas coladas (não seguir links; p/ atualizar/achar um arquivo)'),
                                ('leitura', 'Modo leitura (remove anúncios e scripts; ideal p/ wikis)'),
                                ('so_faltou', 'Só o que faltou (tenta de novo só a lista de falhas; não revê o site)'))):
        ttk.Checkbutton(opcoes, text=t, variable=var[k], style='Cartao.TCheckbutton').grid(row=i // 2, column=i % 2, sticky='w', padx=(0, 24), pady=2)

    # aba Tipos de arquivo
    aba_tipos = aba('Tipos de arquivo')
    rotulo(aba_tipos, 'Baixar estes tipos', 'todos vêm marcados; desmarque o que NÃO quer')
    grade = ttk.Frame(aba_tipos, style='Cartao.TFrame')
    grade.pack(anchor='w')
    tipos = {}
    for i, nome in enumerate(list(GRUPOS) + ['Outros formatos']):
        tipos[nome] = tk.BooleanVar(value=True)
        r = nome if nome == 'Outros formatos' else f'{nome} (.{GRUPOS[nome][0] or GRUPOS[nome][1]}...)'
        ttk.Checkbutton(grade, text=r, variable=tipos[nome], style='Cartao.TCheckbutton').grid(row=i // 4, column=i % 4, sticky='w', padx=(0, 18), pady=2)

    def caixa_salva(pai, titulo, dica, arquivo):
        """caixa de texto que lembra o conteudo entre usos (salva no arquivo ao clicar Baixar)"""
        rotulo(pai, titulo, dica)
        c = texto(pai, 2)
        c.pack(fill='x')
        try:
            c.insert('1.0', open(arquivo, encoding='utf-8').read())
        except OSError:  # primeira vez: vazia
            pass
        return c
    form_caixa = caixa_salva(aba_tipos, 'Formatos que não quero', 'ex.: exe, iso, mp4 -- um por linha ou separados por virgula', LISTA_FORMATOS)

    # aba Filtros e bloqueios
    aba_filtros = aba('Filtros e bloqueios')
    ttk.Checkbutton(aba_filtros, text='Bloquear anúncios, rastreadores e redes sociais', variable=var['lixo'], style='Cartao.TCheckbutton').pack(anchor='w', pady=(10, 0))
    bloq_caixa = caixa_salva(aba_filtros, 'Outros sites que não quero que ele visite', 'um por linha; vale para os subdomínios', LISTA_BLOQUEIO)
    rotulo(aba_filtros, 'Filtros', '+*.pdf inclui (mesmo de outro site)   -*.gif exclui   -- um por linha')
    filtros = texto(aba_filtros, 2)
    filtros.pack(fill='x')

    # aba Avancado
    avancado = aba('Avançado')
    rotulo(avancado, 'Extensões extras para procurar dentro dos scripts', 'ex.: lua, cfg, dat')
    extras_caixa = ttk.Entry(avancado)
    extras_caixa.pack(fill='x', ipady=3)
    rotulo(avancado, 'Cookies para áreas com login', 'só sites seus; um por linha:  site.com: cookie')
    cookies_caixa = texto(avancado, 2)
    cookies_caixa.pack(fill='x')
    ttk.Checkbutton(avancado, text='Apertar botões de download (só no seu próprio site)', variable=var['form'], style='Cartao.TCheckbutton').pack(anchor='w', pady=(10, 0))
    ttk.Checkbutton(avancado, text='Auditar exposição (só sites seus): gera auditoria.html com o que ficou público e o que o robots.txt escondia',
                    variable=var['audit'], style='Cartao.TCheckbutton').pack(anchor='w', pady=(6, 0))
    ttk.Checkbutton(avancado, text='Renderizar JavaScript (sites React/Vue; acha arquivos montados por código; precisa do Playwright, mais lento)',
                    variable=var['render'], style='Cartao.TCheckbutton').pack(anchor='w', pady=(6, 0))

    # barra de acao
    acao = ttk.Frame(corpo, padding=(0, 12))
    acao.pack(fill='x')
    parar = threading.Event()
    trabalho = []  # uma linha de trabalho por site
    botao = ttk.Button(acao, text='Baixar', style='Acao.TButton')
    botao.pack(side='left')
    ttk.Button(acao, text='Parar', command=parar.set).pack(side='left', padx=8)
    status = tk.StringVar(value='Pronto para começar')
    ttk.Label(acao, textvariable=status, foreground=COR['suave']).pack(side='right')
    barra = ttk.Progressbar(acao, mode='indeterminate', length=180)  # so aparece enquanto baixa
    resultado = ttk.Frame(corpo)  # aparece quando termina
    raiz_atual, servidor = [''], {}

    def abrir(caminho):
        if os.name == 'nt':
            os.startfile(caminho)
        else:
            webbrowser.open('file://' + urllib.request.pathname2url(os.path.abspath(caminho)))

    def site_completo():
        """servidor local (sem internet) so enquanto o painel esta aberto: sites React/Vue funcionam"""
        r = raiz_atual[0]
        if r not in servidor:
            class Quieto(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *a):
                    pass
            servidor[r] = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quieto, directory=r))
            threading.Thread(target=servidor[r].serve_forever, daemon=True).start()
        webbrowser.open(f'http://127.0.0.1:{servidor[r].server_address[1]}/index.html')

    for t, f in (('Abrir site', lambda: abrir(os.path.join(raiz_atual[0], 'index.html'))), ('Site completo', site_completo),
                 ('Ver esqueleto', lambda: abrir(os.path.join(raiz_atual[0], 'mapa.html'))), ('Abrir pasta', lambda: abrir(pasta_var.get() or os.path.dirname(raiz_atual[0])))):
        ttk.Button(resultado, text=t, command=f).pack(side='left', padx=(0, 8))

    registro = scrolledtext.ScrolledText(corpo, height=8, font=('Consolas', 9), bg=COR['log'], fg='#cbd5e1', insertbackground='white',
                                         relief='flat', bd=0, padx=10, pady=8, state='disabled')
    registro.pack(fill='both', expand=True, pady=(0, 16))
    for tag, cor in (('ok', '#4ade80'), ('falhou', '#f87171'), ('aviso', '#fbbf24'), ('pronto', '#60a5fa')):
        registro.tag_configure(tag, foreground=cor)
    registro.config(state='normal'); registro.insert('end', 'O andamento do download aparece aqui.\n', 'dica'); registro.config(state='disabled')
    registro.tag_configure('dica', foreground='#64748b')

    contador = [0]

    def log(msg):
        m = re.sub(r'^\[[^\]]*\] ', '', msg)  # tira o [site.com] de quando varios sites rodam juntos
        tag = ('falhou' if m.startswith('falhou') else 'pronto' if m.startswith('PRONTO') else
               'aviso' if m.startswith(('pulei', 'cortei', 'cole', 'aviso', 'continuando', 'Agendado', 'Nao consegui', 'Sem Agendador')) else 'ok' if 'ok (' in m else '')
        def add():
            registro.config(state='normal'); registro.insert('end', msg + '\n', tag); registro.see('end'); registro.config(state='disabled')
            if tag == 'ok':
                contador[0] += 1
                status.set(f'{contador[0]} arquivos baixados')
        w.after(0, add)

    def vigiar():
        if any(t.is_alive() for t in trabalho):
            w.after(300, vigiar)
        else:
            status.set(f'Concluído: {contador[0]} arquivos' + (' (parado)' if parar.is_set() else ''))
            w.bell()
            if not w.focus_displayof():  # janela em segundo plano: avisa pelo Windows
                avisar(status.get())
            barra.stop()
            barra.pack_forget()
            botao.state(['!disabled'])
            if raiz_atual[0] and os.path.exists(os.path.join(raiz_atual[0], 'index.html')):
                resultado.pack(fill='x', pady=(0, 10), before=registro)

    def coleta():
        """opcoes da janela num dicionario (o mesmo formato de um perfil)"""
        return dict(enderecos=caixa.get('1.0', 'end').strip(), pasta=pasta_var.get(), filtros=filtros.get('1.0', 'end').strip(),
                    extras=extras_caixa.get(), desmarcados=[n for n, v in tipos.items() if not v.get()],
                    **{k: campos[k].get() for k in campos}, **{k: v.get() for k, v in var.items()})

    def aplica(cfg):
        c = {**PADRAO, **cfg}
        for widget, chave in ((caixa, 'enderecos'), (filtros, 'filtros')):
            widget.delete('1.0', 'end'); widget.insert('1.0', c[chave])
        extras_caixa.delete(0, 'end'); extras_caixa.insert(0, c['extras'])
        pasta_var.set(c['pasta'])
        for k in campos:
            campos[k].set(c[k])
        for k, v in var.items():
            v.set(c[k])
        for n, v in tipos.items():
            v.set(n not in c['desmarcados'])

    def salva_listas():
        for arquivo, c in ((LISTA_BLOQUEIO, bloq_caixa), (LISTA_FORMATOS, form_caixa)):
            open(arquivo, 'w', encoding='utf-8').write(c.get('1.0', 'end').strip() + '\n')

    def lista_perfis():
        perfil['values'] = sorted(f[:-5] for f in os.listdir(PERFIS) if f.endswith('.json')) if os.path.isdir(PERFIS) else []

    def carrega_perfil(_=None):
        aplica(json.loads(ler(os.path.join(PERFIS, perfil.get() + '.json')) or '{}'))
        log(f'perfil carregado: {perfil.get()}')

    def salva_perfil():
        nome = simpledialog.askstring('Salvar perfil', 'Nome do perfil (ex.: meu-site):', initialvalue=perfil.get(), parent=w)
        nome = re.sub(r'[<>:"/|?*\\]', '_', (nome or '').strip())
        if nome:
            os.makedirs(PERFIS, exist_ok=True)
            json.dump(coleta(), open(os.path.join(PERFIS, nome + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            salva_listas()
            lista_perfis()
            perfil.set(nome)
            log(f'perfil salvo: {nome} (cookies nao sao salvos)')

    def exclui_perfil():
        if perfil.get() and messagebox.askyesno('Excluir perfil', f'Excluir o perfil "{perfil.get()}"?', parent=w):
            os.remove(os.path.join(PERFIS, perfil.get() + '.json'))
            perfil.set('')
            lista_perfis()

    def janela_agendar():
        if not perfil.get():
            messagebox.showinfo('Agendar', 'Salve um perfil primeiro: o agendamento roda um perfil.', parent=w)
            return
        j = tk.Toplevel(w, bg=COR['cartao'], padx=18, pady=14)
        j.title('Agendar atualização')
        j.transient(w)
        ttk.Label(j, text=f'Atualizar "{perfil.get()}" sozinho, baixando só o que mudou', style='Cartao.TLabel').grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 10))
        quando, dia, hora = ttk.Combobox(j, values=['Todo dia', 'Toda semana'], state='readonly', width=12), ttk.Combobox(
            j, values=['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'DOM'], state='readonly', width=6), ttk.Entry(j, width=7)
        quando.set('Toda semana'); dia.set('SEG'); hora.insert(0, '03:00')
        for i, (t, wd) in enumerate((('Quando', quando), ('Dia', dia), ('Hora', hora))):
            ttk.Label(j, text=t, style='Dica.TLabel').grid(row=1, column=i, sticky='w', padx=(0, 10))
            wd.grid(row=2, column=i, sticky='w', padx=(0, 10))

        def ok():
            if not re.fullmatch(r'\d{1,2}:\d{2}', hora.get().strip()):
                messagebox.showerror('Agendar', 'Hora no formato 03:00', parent=j)
                return
            ingles = dict(zip(['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'DOM'], ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']))
            log(agendar(perfil.get(), 'DAILY' if quando.get() == 'Todo dia' else 'WEEKLY', ingles[dia.get()], hora.get().strip().zfill(5)))
            j.destroy()
        ttk.Button(j, text='Agendar', style='Acao.TButton', command=ok).grid(row=2, column=3, padx=(10, 0))

    perfil.bind('<<ComboboxSelected>>', carrega_perfil)
    for t, f in (('Salvar perfil', salva_perfil), ('Excluir', exclui_perfil), ('Agendar...', janela_agendar)):
        botoes_perfil[t].config(command=f)
    lista_perfis()
    aplica(json.loads(ler(CONFIG) or '{}'))  # volta como estava da ultima vez

    def iniciar():
        if not pasta_var.get():
            pasta_var.set(filedialog.askdirectory(title='Pasta onde salvar o espelho') or '')
        cfg = coleta()
        salva_listas()
        json.dump(cfg, open(CONFIG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        alvos, kw = argumentos(cfg)
        if not alvos[0][0] or not cfg['pasta']:
            log('cole um endereco http e escolha uma pasta')
            return
        parar.clear()
        resultado.pack_forget()
        raiz_atual[0] = alvos[0][1]  # botoes do fim abrem o primeiro site; 'Abrir pasta' mostra todos
        contador[0] = 0
        registro.config(state='normal'); registro.delete('1.0', 'end'); registro.config(state='disabled')
        kw['cookies'] = {L.split(':', 1)[0].strip().lower().replace('https://', '').replace('http://', '').split('/')[0]:
                         L.split(':', 1)[1].strip() for L in cookies_caixa.get('1.0', 'end').splitlines() if ':' in L and L.strip()}
        trabalho[:] = []
        for urls, raiz in alvos:
            site = urllib.parse.urlparse(urls[0]).netloc
            lg = (lambda pre: lambda m: log(pre + m))(f'[{site}] ' if len(alvos) > 1 else '')
            trabalho.append(threading.Thread(target=espelhar, daemon=True, args=(urls, raiz, lg, parar), kwargs=kw))
            trabalho[-1].start()
        botao.state(['disabled'])
        status.set('Baixando...')
        barra.pack(side='right', padx=12)
        barra.start(12)
        vigiar()

    botao.config(command=iniciar)
    w.mainloop()


if __name__ == '__main__':
    if '--perfil' in sys.argv:  # sem janela: python painel_download.py --perfil site1 [--perfil site2 ...] [--atualizar]
        rodar_perfis([sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == '--perfil'], '--atualizar' in sys.argv)
    else:
        main()
