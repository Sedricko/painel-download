"""Painel para espelhar paginas e arquivos publicos para leitura offline (alternativa leve ao HTTrack).

- espelho em pastas (dominio/caminho), com links reescritos para abrir offline; o que nao foi baixado vai para nao_baixado.html
  e uma trava (CSP) impede a pagina de acessar a internet; opcional: .zip no fim
- filtros no estilo HTTrack, um por linha: +*.pdf (inclui, mesmo de outro site)  -*.gif (exclui)
- profundidade (so conta paginas HTML), limite de paginas, MB por arquivo, varias conexoes, pausa entre pedidos
- retoma: arquivo ja baixado nao baixa de novo; respeita robots.txt (desligavel); ignora anuncios e redes sociais
Le sitemap.xml. Segue href/src/srcset/data-*/css url()/@import/meta refresh/sourcemap, playlists .m3u8 e, dentro de html/js/json/lua/etc.,
enderecos completos e caminhos entre aspas com extensao conhecida ("scripts/main.lua", JSON com \\/). Nao adivinha enderecos."""
import fnmatch, hashlib, html as htmllib, http.cookiejar, os, re, threading, time, tkinter as tk, urllib.parse, urllib.request, urllib.robotparser, zipfile
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, scrolledtext, ttk

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
    # redes sociais
    'facebook.com', 'fb.com', 'fb.me', 'fbcdn.net', 'instagram.com', 'cdninstagram.com', 'twitter.com', 'x.com', 't.co', 'twimg.com',
    'tiktok.com', 'tiktokcdn.com', 'linkedin.com', 'licdn.com', 'pinterest.com', 'pinimg.com', 'reddit.com', 'redd.it', 'redditmedia.com',
    'youtube.com', 'youtu.be', 'ytimg.com', 'googlevideo.com', 'whatsapp.com', 'wa.me', 'telegram.org', 't.me', 'discord.com', 'discord.gg',
    'snapchat.com', 'threads.net', 'tumblr.com', 'vk.com', 'kwai.com', 'twitch.tv', 'bsky.app', 'mastodon.social', 'quora.com',
}
ATTR = re.compile(r'''\b(?:href|src|xlink:href|poster|background|data|manifest|lowsrc|longdesc|data-[\w-]*(?:src|href|url|file|original|bg|background|download|lazy))\s*=\s*["']([^"'#]+)'''
                  r'''|\burl\(\s*["']?([^"')#]+)|@import\s+["']([^"']+)|\bcontent\s*=\s*["']\d+\s*;\s*url\s*=\s*([^"'#]+)|sourceMappingURL=([^\s"'*]+)''', re.I)
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
LISTA_BLOQUEIO, LISTA_FORMATOS = (os.path.join(os.path.dirname(os.path.abspath(__file__)), n) for n in ('sites_bloqueados.txt', 'formatos_bloqueados.txt'))
CONHECIDAS = {e for g in GRUPOS.values() for e in g}
DINAMICAS = {'php', 'asp', 'aspx', 'jsp', 'jspx', 'cfm', 'cgi', 'shtml', 'phtml', 'erb', 'cshtml'}  # pagina gerada no servidor: salva como .html para abrir offline
LER = {'html', 'htm', 'xhtml', 'css', 'js', 'mjs', 'cjs', 'json', 'xml', 'svg', 'txt', 'm3u8', 'm3u', 'webmanifest', 'rss', 'atom', 'jsonld',
       'vue', 'svelte', 'md', 'markdown', 'graphql', 'gql', 'prisma', *GRUPOS['Código'], *GRUPOS['Config'], *GRUPOS['Automação e DevOps']}  # arquivos de texto onde procurar links escondidos
# nomes que tambem sao palavras de codigo/dominio ("console.log", "site.com"): so contam com '/' no caminho
SEM_PONTO = {'Dockerfile', 'Makefile', 'Procfile', 'Jenkinsfile'}  # arquivos conhecidos sem extensao
DUVIDOSAS = {e for e in CONHECIDAS if len(e) < 3} | {'com', 'log', 'map', 'app', 'key', 'sys', 'lib', 'env', 'dat', 'img', 'bin',
                                                     'run', 'mod', 'obj', 'ct', 'esp', 'sig', 'assets', 'bundle', 'config', 'data', 'lock'}
QUOTADO = re.compile(r'''["'`]([^"'`\s<>(){}\\|^]+(?:\.(?:%s)|/(?:%s))(?:[?#][^"'`\s]*)?)["'`]''' % ('|'.join(
    sorted((re.escape(e) for e in CONHECIDAS if e), key=len, reverse=True)), '|'.join(SEM_PONTO)), re.I)  # "dir/arquivo.lua" escondido em qualquer texto
JAR = http.cookiejar.CookieJar()  # guarda o cookie da sessao durante o download, como o navegador
NAVEGADOR = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR))
# regra do navegador: scripts da pagina nao acessam a internet (so arquivos locais); formularios nao enviam nada
TRAVA = ('''<meta http-equiv="Content-Security-Policy" content="default-src 'self' file: data: blob: 'unsafe-inline' 'unsafe-eval'; '''
         '''form-action 'none'">''')
NAO_BAIXADO = ('''<!doctype html><meta charset="utf-8"><title>Nao baixado</title><body style="font-family:sans-serif;padding:24px">'''
               '''<h2>Este link nao foi baixado</h2><p>Endereco original (copie se quiser abrir na internet):</p>'''
               '''<p><code id="u"></code></p><p><a href="javascript:history.back()">Voltar</a></p>'''
               '''<script>document.getElementById('u').textContent = decodeURIComponent(location.hash.slice(1))</script>''')
FORM = re.compile(r'<form\b([^>]*)>(.*?)</form>', re.I | re.S)


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
        out.append((urllib.parse.urljoin(base, atributo(attrs, 'action') or base), dados))
    return out


def extensao(url):
    """'lua' de x/main.lua; tambem 'htaccess' de /.htaccess e 'dockerfile' de /Dockerfile"""
    n = os.path.basename(urllib.parse.urlparse(url).path)
    return n.lower() if n in SEM_PONTO else n.rsplit('.', 1)[1].lower() if '.' in n else ''


def caminho_local(raiz, url):
    p = urllib.parse.urlparse(url)
    c = p.path
    if c.endswith('/') or not c:
        c += 'index.html'
    nome = re.sub(r'[<>:"|?*\\]', '_', c.strip('/'))
    if p.query:
        base, ext = os.path.splitext(nome)
        nome = base + '_' + hashlib.md5(p.query.encode()).hexdigest()[:8] + (ext or '.html')
    elif '.' not in os.path.basename(nome) and os.path.basename(nome) not in SEM_PONTO:
        nome += '.html'
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
    texto = re.sub(r'\\u002[fF]', '/', texto.replace('\\/', '/'))  # JSON escapa a barra: "https:\/\/site\/x.lua"
    achados = [next(x for x in m if x) for m in ATTR.findall(texto)]
    achados += [a for a in QUOTADO.findall(texto) if '/' in a or extensao(a.split('#')[0]) not in DUVIDOSAS]
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
        if '${' in a or '{{' in a or a.startswith('%23'):  # modelo de JavaScript ("${base}.lua") ou ancora, nao e endereco
            continue
        u = urllib.parse.urljoin(base, htmllib.unescape(a.strip())).split('#')[0]  # &amp; do html vira &
        if u.startswith('http'):
            out.append(u)
    return out


def ler_sitemaps(sites, log):
    """enderecos <loc> do /sitemap.xml e dos 'Sitemap:' do robots.txt (segue indices de sitemap)"""
    def baixar(u):
        try:
            return urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'leitura-pessoal'}), timeout=30).read().decode('utf-8', 'replace')
        except Exception:
            return ''
    fila = [s + '/sitemap.xml' for s in sites] + [m for s in sites for m in re.findall(r'(?im)^\s*sitemap:\s*(\S+)', baixar(s + '/robots.txt'))]
    vistos, achados = set(), []
    while fila and len(vistos) < 100:  # shortcut: le no maximo 100 sitemaps e ignora .xml.gz; aumentar se algum site precisar
        s = fila.pop()
        if s in vistos:
            continue
        vistos.add(s)
        for loc in re.findall(r'<loc>\s*([^<\s]+)', baixar(s)):
            loc = loc.replace('&amp;', '&')
            (fila if '<sitemapindex' in loc or re.search(r'\.xml(\?|$)', loc, re.I) else achados).append(loc)
    if achados:
        log(f'sitemap: {len(achados)} enderecos')
    return achados


def gerar_indice(raiz, inicio, origem):
    """espelho/index.html (abre o inicio do site) e espelho/mapa.html (esqueleto: todos os arquivos com link direto)"""
    esc, pastas = htmllib.escape, {}
    for d, _, fs in os.walk(raiz):
        for f in sorted(fs):
            if not (d == raiz and f in ('index.html', 'mapa.html', 'nao_baixado.html')) and not f.endswith('.part'):
                pastas.setdefault(os.path.relpath(d, raiz).replace(os.sep, '/'), []).append(os.path.join(d, f))
    rel = lambda c: urllib.parse.quote(os.path.relpath(c, raiz).replace(os.sep, '/'))
    corpo = []
    for pasta in sorted(pastas):
        corpo.append(f'<h2>{esc(pasta)}/</h2><ul>')
        for c in pastas[pasta]:
            u = origem.get(c)
            corpo.append(f'<li><a href="{rel(c)}">{esc(os.path.basename(c))}</a> <small>{os.path.getsize(c) // 1024} KB'
                         + (f' &middot; {esc(u)}' if u else '') + '</small></li>')
        corpo.append('</ul>')
    estilo = '<meta charset="utf-8"><style>body{font-family:sans-serif;margin:0}nav{background:#222;padding:8px}nav a{color:#fff;margin-right:16px}main{padding:0 16px}small{color:#777}</style>'
    nav = '<nav><a href="index.html">Inicio do site</a><a href="mapa.html">Mapa dos arquivos</a></nav>'
    total = sum(len(v) for v in pastas.values())
    open(os.path.join(raiz, 'mapa.html'), 'w', encoding='utf-8').write(
        f'<!doctype html><title>Mapa do espelho</title>{estilo}{nav}<main><h1>{total} arquivos</h1>{"".join(corpo)}</main>')
    open(os.path.join(raiz, 'index.html'), 'w', encoding='utf-8').write(
        f'<!doctype html><title>Espelho offline</title>{estilo}<style>iframe{{border:0;width:100%;height:calc(100vh - 40px)}}</style>{nav}'
        + (f'<iframe src="{rel(inicio)}"></iframe>' if inicio and os.path.exists(inicio) else '<main><p>Inicio nao baixado; veja o mapa.</p></main>'))


def espelhar(urls, raiz, log, parar, profundidade=3, limite=200, mesmo_site=True, filtros='', max_mb=500,
             conexoes=4, pausa=0.3, robots=True, reescrever=True, gerar_zip=True, ext_excluidas=(), outros=True, extras=(),
             sitemap=True, formularios=False, cookies=None, bloquear=BLOQUEADOS):
    os.makedirs(raiz, exist_ok=True)
    cookies = cookies or {}
    bloquear = {re.sub(r'^(https?://)?(www\.)?', '', b.strip().lower()).split('/')[0] for b in bloquear if b.strip()}
    dominios = {urllib.parse.urlparse(u).netloc for u in urls}

    def cab(u, extra=None):
        """cabecalhos; junta o cookie da sessao (JAR) com o cookie do login do dominio (areas que pedem login)"""
        h = {'User-Agent': 'leitura-pessoal'}
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
    rp, lock, ultimo = {}, threading.Lock(), [0.0]
    feitos, mapa, baixados = set(urls), {}, [0]

    def permitido(u):
        e = extensao(u)
        if e in ext_excluidas or (e not in CONHECIDAS and not outros):
            return False
        h = urllib.parse.urlparse(u).netloc.lower().split(':')[0]
        if urllib.parse.urlparse(u).netloc not in dominios and any(h == d or h.endswith('.' + d) for d in bloquear):
            return False
        if any(fnmatch.fnmatch(u, m) or fnmatch.fnmatch(u.split('//', 1)[-1], m) for m in menos):
            return False
        if any(fnmatch.fnmatch(u, m) or fnmatch.fnmatch(u.split('//', 1)[-1], m) for m in mais):
            return True
        if mesmo_site and urllib.parse.urlparse(u).netloc not in dominios:
            return False
        if robots:
            h = urllib.parse.urlparse(u)
            with lock:
                if h.netloc not in rp:
                    r = urllib.robotparser.RobotFileParser(f'{h.scheme}://{h.netloc}/robots.txt')
                    try:
                        r.read()
                    except Exception:
                        r = None
                    rp[h.netloc] = r
            r = rp[h.netloc]
            if r and not r.can_fetch('leitura-pessoal', u):
                return False
        return True

    def pegar(u):
        """(texto ou None, caminho) -- baixa em pedacos, retoma se o arquivo ja existe"""
        dest = caminho_local(raiz, u)
        if os.path.exists(dest):
            return dest, True
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        for tentativa in range(3):
            if parar.is_set():
                return None, False
            with lock:
                espera = ultimo[0] + pausa - time.time()
                ultimo[0] = max(time.time(), ultimo[0]) + (pausa if espera > 0 else 0)
            if espera > 0:
                time.sleep(espera)
            try:
                r = NAVEGADOR.open(urllib.request.Request(u, headers=cab(u)), timeout=30)
                if int(r.headers.get('Content-Length') or 0) > max_mb << 20:
                    log(f'pulei {u}: maior que {max_mb} MB')
                    return None, False
                total = 0
                with open(dest + '.part', 'wb') as f:
                    while chunk := r.read(1 << 20):
                        total += len(chunk)
                        if total > max_mb << 20:
                            log(f'cortei {u} em {max_mb} MB')
                            break
                        f.write(chunk)
                os.replace(dest + '.part', dest)
                return dest, False
            except Exception as e:
                if tentativa == 2 or '404' in str(e) or '403' in str(e):
                    log(f'falhou {u}: {e}')
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
                nome = re.search(r'''filename\*?=(?:UTF-8'')?["']?([^"';]+)''', r.headers.get('Content-Disposition') or '', re.I)
                if not nome:
                    continue  # nao era download (pagina comum)
                nome = re.sub(r'[<>:"/|?*\\]', '_', os.path.basename(urllib.parse.unquote(nome.group(1)).strip()))
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
        try:
            texto = open(dest, encoding='utf-8', errors='replace').read()
        except OSError:
            return []
        html = dest.lower().endswith(('.html', '.htm'))
        if html and formularios:
            enviar_formularios(u)
        novos = []
        for v in links(texto, u, extras):
            eh_pagina = extensao(v) in GRUPOS['Páginas']  # so pagina conta profundidade; arquivo de qualquer formato sempre vem
            if eh_pagina and prof >= profundidade:  # vale tambem para pagina citada dentro de .js/.json
                continue
            novos.append((v, prof + 1 if eh_pagina else prof))
        return novos

    nivel = [(u, 0) for u in urls]
    if sitemap:  # sitemap.xml lista paginas publicas que nenhum link mostra
        for v in ler_sitemaps({f'{urllib.parse.urlparse(u).scheme}://{urllib.parse.urlparse(u).netloc}' for u in urls}, log):
            if v not in feitos and permitido(v):
                feitos.add(v)
                nivel.append((v, 0))
    with ThreadPoolExecutor(conexoes) as pool:
        while nivel and baixados[0] < limite and not parar.is_set():
            prox = []
            for novos in pool.map(tratar, nivel[:max(0, limite - baixados[0])]):
                for v, p in novos:
                    with lock:
                        if v in feitos:
                            continue
                        feitos.add(v)
                    if permitido(v):
                        prox.append((v, p))
            nivel = prox
    if reescrever:
        fora = os.path.join(raiz, 'nao_baixado.html')
        open(fora, 'w', encoding='utf-8').write(NAO_BAIXADO)
        for u, dest in mapa.items():
            if not dest.lower().endswith(('.html', '.htm', '.xhtml', '.css')):
                continue
            texto = open(dest, encoding='utf-8', errors='replace').read()
            b = base_de(texto, u)

            def local(v):
                """caminho local do link; o que nao foi baixado vai para nao_baixado.html (nunca abre a internet)"""
                alvo = urllib.parse.urljoin(b, htmllib.unescape(v.strip()))
                alvo, _, frag = alvo.partition('#')
                if alvo in mapa:
                    return os.path.relpath(mapa[alvo], os.path.dirname(dest)).replace(os.sep, '/') + ('#' + frag if frag else '')
                if alvo.startswith('http'):
                    return os.path.relpath(fora, os.path.dirname(dest)).replace(os.sep, '/') + '#' + urllib.parse.quote(alvo, safe='')
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
            novo = re.sub(r'<base\b[^>]*>', '', SRCSET.sub(troca_set, ATTR.sub(troca, texto)), flags=re.I)  # links ja viraram caminhos locais
            if not dest.lower().endswith('.css'):
                novo = re.sub(r'''\s(?:integrity|nonce)\s*=\s*("[^"]*"|'[^']*')''', '', novo, flags=re.I)  # o arquivo local mudou: a assinatura original bloquearia ele
                novo, n = re.subn(r'<head\b[^>]*>', lambda h: h.group(0) + TRAVA, novo, count=1, flags=re.I)
                novo = novo if n else TRAVA + novo
            if novo != texto:
                open(dest, 'w', encoding='utf-8').write(novo)
    gerar_indice(raiz, mapa.get(urls[0]) or caminho_local(raiz, urls[0]), {d: u for u, d in mapa.items()})
    if gerar_zip:
        with zipfile.ZipFile(raiz.rstrip('/\\') + '.zip', 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for d, _, fs in os.walk(raiz):
                for f in fs:
                    z.write(os.path.join(d, f), os.path.relpath(os.path.join(d, f), raiz))
    log(f'PRONTO: {baixados[0]} arquivos em {raiz}' + (' + .zip' if gerar_zip else '') + (' (parado)' if parar.is_set() else ''))


def main():
    COR = {'fundo': '#f4f6fa', 'cartao': '#ffffff', 'borda': '#dfe3ea', 'texto': '#1f2937', 'suave': '#6b7280',
           'destaque': '#2563eb', 'destaque2': '#1d4ed8', 'topo': '#111827', 'log': '#0f172a'}
    w = tk.Tk()
    w.title('Painel de Download')
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
    tk.Label(topo, text='Copia sites e arquivos para abrir 100% offline', bg=COR['topo'], fg='#9ca3af', font=fonte).pack(anchor='w')
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
    for i, (nome, chave, padrao, passo) in enumerate((('Profundidade', 'prof', 3, 1), ('Páginas máx.', 'lim', 200, 50), ('MB por arquivo', 'mb', 500, 50),
                                                      ('Conexões', 'con', 4, 1), ('Pausa (s)', 'pausa', 0.3, 0.1))):
        ttk.Label(linha, text=nome, style='Dica.TLabel').grid(row=0, column=i, sticky='w', padx=(0, 16))
        campos[chave] = ttk.Spinbox(linha, from_=0, to=99999, increment=passo, width=9)
        campos[chave].set(padrao)
        campos[chave].grid(row=1, column=i, sticky='w', padx=(0, 16))
    rotulo(geral, 'Opções')
    opcoes = ttk.Frame(geral, style='Cartao.TFrame')
    opcoes.pack(anchor='w')
    var = {k: tk.BooleanVar(value=True) for k in ('mesmo', 'lixo', 'robots', 'rew', 'zip', 'sitemap', 'form')}
    var['form'].set(False)
    for i, (k, t) in enumerate((('mesmo', 'Só o mesmo site (desmarque p/ seguir links de outros sites)'), ('rew', 'Reescrever links (abrir offline)'),
                                ('robots', 'Respeitar robots.txt'), ('zip', 'Gerar .zip no fim'), ('sitemap', 'Ler sitemap.xml'))):
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

    # barra de acao
    acao = ttk.Frame(corpo, padding=(0, 12))
    acao.pack(fill='x')
    parar = threading.Event()
    trabalho = [None]
    botao = ttk.Button(acao, text='Baixar', style='Acao.TButton')
    botao.pack(side='left')
    ttk.Button(acao, text='Parar', command=parar.set).pack(side='left', padx=8)
    status = tk.StringVar(value='Pronto para começar')
    ttk.Label(acao, textvariable=status, foreground=COR['suave']).pack(side='right')
    barra = ttk.Progressbar(acao, mode='indeterminate', length=180)  # so aparece enquanto baixa

    registro = scrolledtext.ScrolledText(corpo, height=12, font=('Consolas', 9), bg=COR['log'], fg='#cbd5e1', insertbackground='white',
                                         relief='flat', bd=0, padx=10, pady=8, state='disabled')
    registro.pack(fill='both', expand=True, pady=(0, 16))
    for tag, cor in (('ok', '#4ade80'), ('falhou', '#f87171'), ('aviso', '#fbbf24'), ('pronto', '#60a5fa')):
        registro.tag_configure(tag, foreground=cor)
    registro.config(state='normal'); registro.insert('end', 'O andamento do download aparece aqui.\n', 'dica'); registro.config(state='disabled')
    registro.tag_configure('dica', foreground='#64748b')

    def log(msg):
        tag = ('falhou' if msg.startswith('falhou') else 'pronto' if msg.startswith('PRONTO') else
               'aviso' if msg.startswith(('pulei', 'cortei', 'cole')) else 'ok' if 'ok (' in msg else '')
        def add():
            registro.config(state='normal'); registro.insert('end', msg + '\n', tag); registro.see('end'); registro.config(state='disabled')
            n = re.search(r'ok \((\d+)\)', msg)
            if n:
                status.set(f'{n.group(1)} arquivos baixados')
            elif tag == 'pronto':
                status.set(f"Concluído: {re.search(r'\d+', msg).group()} arquivos" + (' (parado)' if 'parado' in msg else ''))
        w.after(0, add)

    def vigiar():
        if trabalho[0] and trabalho[0].is_alive():
            w.after(300, vigiar)
        else:
            barra.stop()
            barra.pack_forget()
            botao.state(['!disabled'])

    def iniciar():
        urls = [u.strip() for u in caixa.get('1.0', 'end').splitlines() if u.strip().startswith('http')]
        if not urls:
            log('cole um endereco http')
            return
        if not pasta_var.get():
            pasta_var.set(filedialog.askdirectory(title='Pasta onde salvar o espelho') or '')
        pasta = pasta_var.get()
        if not pasta:
            log('cole um endereco http e escolha uma pasta')
            return
        parar.clear()
        registro.config(state='normal'); registro.delete('1.0', 'end'); registro.config(state='disabled')
        bloq, sem_formato = (c.get('1.0', 'end').strip() for c in (bloq_caixa, form_caixa))
        for arquivo, conteudo in ((LISTA_BLOQUEIO, bloq), (LISTA_FORMATOS, sem_formato)):
            open(arquivo, 'w', encoding='utf-8').write(conteudo + '\n')
        trabalho[0] = threading.Thread(target=espelhar, daemon=True, args=(urls, os.path.join(pasta, 'espelho'), log, parar), kwargs=dict(
            profundidade=int(campos['prof'].get()), limite=int(campos['lim'].get()), mesmo_site=var['mesmo'].get(),
            filtros=filtros.get('1.0', 'end'), max_mb=int(campos['mb'].get()), conexoes=int(campos['con'].get()),
            pausa=float(campos['pausa'].get()), robots=var['robots'].get(), reescrever=var['rew'].get(), gerar_zip=var['zip'].get(), sitemap=var['sitemap'].get(), formularios=var['form'].get(),
            ext_excluidas={e for n, v in tipos.items() if not v.get() and n in GRUPOS for e in GRUPOS[n]}
            | {x.lower().lstrip('*.') for x in re.split(r'[\s,;]+', sem_formato) if x.strip('*.')}, outros=tipos['Outros formatos'].get(),
            extras=[x for x in re.split(r'[\s,;]+', extras_caixa.get()) if x],
            bloquear=(BLOQUEADOS if var['lixo'].get() else set()) | {L.split('#')[0] for L in bloq.splitlines()},
            cookies={L.split(':', 1)[0].strip().lower().replace('https://', '').replace('http://', '').split('/')[0]:
                     L.split(':', 1)[1].strip() for L in cookies_caixa.get('1.0', 'end').splitlines() if ':' in L and L.strip()}))
        trabalho[0].start()
        botao.state(['disabled'])
        status.set('Baixando...')
        barra.pack(side='right', padx=12)
        barra.start(12)
        vigiar()

    botao.config(command=iniciar)
    w.mainloop()

if __name__ == '__main__':
    main()
