"""Painel para espelhar paginas e arquivos publicos para leitura offline (alternativa leve ao HTTrack).

- espelho em pastas (dominio/caminho), com links reescritos para abrir offline; opcional: .zip no fim
- filtros no estilo HTTrack, um por linha: +*.pdf (inclui, mesmo de outro site)  -*.gif (exclui)
- profundidade (so conta paginas HTML), limite de paginas, MB por arquivo, varias conexoes, pausa entre pedidos
- retoma: arquivo ja baixado nao baixa de novo; respeita robots.txt (desligavel); ignora dominios de anuncio
Le sitemap.xml. Segue href/src/srcset/data-*/css url()/@import/meta refresh/sourcemap, playlists .m3u8 e, dentro de html/js/json/lua/etc.,
enderecos completos e caminhos entre aspas com extensao conhecida ("scripts/main.lua", JSON com \\/). Nao adivinha enderecos."""
import fnmatch, hashlib, html as htmllib, http.cookiejar, os, re, threading, time, tkinter as tk, urllib.parse, urllib.request, urllib.robotparser, zipfile
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, scrolledtext

ANUNCIOS = ('doubleclick.net', 'googlesyndication.com', 'google-analytics.com', 'googletagmanager.com')
ATTR = re.compile(r'''\b(?:href|src|xlink:href|poster|background|data|manifest|lowsrc|longdesc|data-[\w-]*(?:src|href|url|file|original|bg|background|download|lazy))\s*=\s*["']([^"'#]+)'''
                  r'''|\burl\(\s*["']?([^"')#]+)|@import\s+["']([^"']+)|\bcontent\s*=\s*["']\d+\s*;\s*url\s*=\s*([^"'#]+)|sourceMappingURL=([^\s"'*]+)''', re.I)
BASE = re.compile(r'''<base\b[^>]*\bhref\s*=\s*["']([^"']+)''', re.I)
SRCSET = re.compile(r'''srcset\s*=\s*["']([^"']+)''', re.I)
ABS = re.compile(r'''https?://[^\s"'<>()\\/]+/[^\s"'<>()\\]*\.[a-z0-9]{1,8}(?:\?[^\s"'`<>()\\]*)?(?=[#"'`\s<>()\\,;]|$)''', re.I)  # endereco completo de arquivo, qualquer formato


GRUPOS = {
    'Paginas': ('html', 'htm', 'php', 'asp', 'aspx', 'jsp', 'jspx', 'cfm', 'cgi', 'xhtml', 'shtml', 'phtml', 'erb', 'cshtml', ''),
    'Estilos e scripts': ('css', 'scss', 'less', 'js', 'mjs', 'cjs', 'jsx', 'ts', 'tsx', 'vue', 'svelte', 'map', 'wasm', 'webmanifest'),
    'Codigo': ('lua', 'luac', 'py', 'pyc', 'pyd', 'pyw', 'rb', 'pl', 'tcl', 'r', 'vbs', 'vba', 'ahk', 'au3', 'c', 'h', 'cpp', 'hpp',
               'cs', 'java', 'kt', 'kts', 'scala', 'go', 'rs', 'swift', 'dart', 'el', 'ex', 'exs', 'erl', 'gd', 'nut', 'sqf', 'ipynb'),
    'Config': ('ini', 'cfg', 'config', 'toml', 'properties', 'inf', 'reg', 'plist', 'env', 'lst'),
    'Automacao e DevOps': ('sh', 'bash', 'ps1', 'psm1', 'psd1', 'bat', 'cmd', 'conf', 'lock', 'htaccess', 'dockerignore', 'gitignore',
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
    'Audio': ('mp3', 'mp2', 'wav', 'wma', 'ogg', 'oga', 'opus', 'flac', 'aac', 'm4a', 'aiff', 'mid', 'midi', 'amr'),
    'Video': ('mp4', 'm4v', 'mov', 'mpg', 'mpeg', 'avi', 'asf', 'wmv', 'rm', 'vob', 'qt', 'vid', 'ac3', 'mkv', 'webm', 'flv', 'ogv',
              '3gp', 'm3u8', 'm3u', 'mpd', 'srt', 'vtt'),
    'Fontes': ('woff', 'woff2', 'ttf', 'otf', 'eot'),
    'Outros conhecidos': ('torrent', 'crt', 'cer', 'pem', 'gpg', 'sig', 'sha256', 'md5', 'iss', 'nsi'),
}
CONHECIDAS = {e for g in GRUPOS.values() for e in g}
DINAMICAS = {'php', 'asp', 'aspx', 'jsp', 'jspx', 'cfm', 'cgi', 'shtml', 'phtml', 'erb', 'cshtml'}  # pagina gerada no servidor: salva como .html para abrir offline
LER = {'html', 'htm', 'xhtml', 'css', 'js', 'mjs', 'cjs', 'json', 'xml', 'svg', 'txt', 'm3u8', 'm3u', 'webmanifest', 'rss', 'atom', 'jsonld',
       'vue', 'svelte', 'md', 'markdown', 'graphql', 'gql', 'prisma', *GRUPOS['Codigo'], *GRUPOS['Config'], *GRUPOS['Automacao e DevOps']}  # arquivos de texto onde procurar links escondidos
# nomes que tambem sao palavras de codigo/dominio ("console.log", "site.com"): so contam com '/' no caminho
SEM_PONTO = {'Dockerfile', 'Makefile', 'Procfile', 'Jenkinsfile'}  # arquivos conhecidos sem extensao
DUVIDOSAS = {e for e in CONHECIDAS if len(e) < 3} | {'com', 'log', 'map', 'app', 'key', 'sys', 'lib', 'env', 'dat', 'img', 'bin',
                                                     'run', 'mod', 'obj', 'ct', 'esp', 'sig', 'assets', 'bundle', 'config', 'data', 'lock'}
QUOTADO = re.compile(r'''["'`]([^"'`\s<>(){}\\|^]+(?:\.(?:%s)|/(?:%s))(?:[?#][^"'`\s]*)?)["'`]''' % ('|'.join(
    sorted((re.escape(e) for e in CONHECIDAS if e), key=len, reverse=True)), '|'.join(SEM_PONTO)), re.I)  # "dir/arquivo.lua" escondido em qualquer texto
JAR = http.cookiejar.CookieJar()  # guarda o cookie da sessao durante o download, como o navegador
NAVEGADOR = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR))
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
            if not (d == raiz and f in ('index.html', 'mapa.html')) and not f.endswith('.part'):
                pastas.setdefault(os.path.relpath(d, raiz).replace(os.sep, '/'), []).append(os.path.join(d, f))
    rel = lambda c: urllib.parse.quote(os.path.relpath(c, raiz).replace(os.sep, '/'))
    corpo = []
    for pasta in sorted(pastas):
        corpo.append(f'<h2>{esc(pasta)}/</h2><ul>')
        for c in pastas[pasta]:
            u = origem.get(c)
            corpo.append(f'<li><a href="{rel(c)}">{esc(os.path.basename(c))}</a> <small>{os.path.getsize(c) // 1024} KB'
                         + (f' &middot; <a href="{esc(u)}">{esc(u)}</a>' if u else '') + '</small></li>')
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
             sitemap=True, formularios=False, cookies=None):
    os.makedirs(raiz, exist_ok=True)
    cookies = cookies or {}
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
        if any(a in u for a in ANUNCIOS) or any(fnmatch.fnmatch(u, m) or fnmatch.fnmatch(u.split('//', 1)[-1], m) for m in menos):
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
            eh_pagina = extensao(v) in GRUPOS['Paginas']  # so pagina conta profundidade; arquivo de qualquer formato sempre vem
            if eh_pagina and html and prof >= profundidade:
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
        for u, dest in mapa.items():
            if not dest.lower().endswith(('.html', '.htm', '.css')):
                continue
            texto = open(dest, encoding='utf-8', errors='replace').read()
            b = base_de(texto, u)

            def troca(m):
                alvo = urllib.parse.urljoin(b, htmllib.unescape(next(x for x in m.groups() if x))).split('#')[0]
                if alvo in mapa:
                    return m.group(0).replace(next(x for x in m.groups() if x), os.path.relpath(mapa[alvo], os.path.dirname(dest)).replace(os.sep, '/'))
                return m.group(0)
            def troca_set(m):  # srcset="a.jpg 1x, b.jpg 2x"
                partes = []
                for c in m.group(1).split(','):
                    d = c.strip().split(None, 1)
                    alvo = urllib.parse.urljoin(b, htmllib.unescape(d[0])).split('#')[0] if d else ''
                    d[0:1] = [os.path.relpath(mapa[alvo], os.path.dirname(dest)).replace(os.sep, '/') if alvo in mapa else d[0]] if d else []
                    partes.append(' '.join(d))
                return m.group(0).replace(m.group(1), ', '.join(partes))
            novo = re.sub(r'<base\b[^>]*>', '', SRCSET.sub(troca_set, ATTR.sub(troca, texto)), flags=re.I)  # links ja viraram caminhos locais
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
    w = tk.Tk()
    w.title('Espelhar paginas para o Claude')
    tk.Label(w, text='Enderecos (um por linha):').pack(anchor='w', padx=8, pady=(8, 0))
    caixa = scrolledtext.ScrolledText(w, width=96, height=4)
    caixa.pack(padx=8)
    caixa.insert('1.0', 'https://engineering.nordeus.com/\n')
    tk.Label(w, text='Filtros (+*.pdf inclui, mesmo de outro site; -*.gif exclui):').pack(anchor='w', padx=8)
    filtros = scrolledtext.ScrolledText(w, width=96, height=3)
    filtros.pack(padx=8)
    tk.Label(w, text='Extensoes extras para procurar tambem dentro dos scripts (ex.: lua, cfg, dat):').pack(anchor='w', padx=8)
    extras_caixa = tk.Entry(w, width=60)
    extras_caixa.pack(anchor='w', padx=8)
    tk.Label(w, text='Cookies para areas que pedem login (so sites seus; um por linha: site.com: cookie):').pack(anchor='w', padx=8)
    cookies_caixa = scrolledtext.ScrolledText(w, width=96, height=2)
    cookies_caixa.pack(padx=8)
    campos = {}
    linha = tk.Frame(w)
    linha.pack(anchor='w', padx=8, pady=4)
    for rotulo, chave, padrao in (('Profundidade', 'prof', 3), ('Paginas max', 'lim', 200), ('MB/arquivo', 'mb', 500),
                                  ('Conexoes', 'con', 4), ('Pausa (s)', 'pausa', 0.3)):
        tk.Label(linha, text=rotulo + ':').pack(side='left')
        campos[chave] = tk.Spinbox(linha, from_=0, to=99999, increment=1, width=7)
        campos[chave].delete(0, 'end'); campos[chave].insert(0, str(padrao))
        campos[chave].pack(side='left', padx=(2, 10))
    tk.Label(w, text='Tipos de arquivo (desmarque o que NAO quer):').pack(anchor='w', padx=8)
    grade = tk.Frame(w)
    grade.pack(anchor='w', padx=8)
    tipos = {}
    for i, nome in enumerate(list(GRUPOS) + ['Outros']):
        tipos[nome] = tk.BooleanVar(value=True)
        rotulo = nome if nome == 'Outros' else f'{nome} (.{GRUPOS[nome][0] or GRUPOS[nome][1]}...)'
        tk.Checkbutton(grade, text=rotulo, variable=tipos[nome]).grid(row=i // 4, column=i % 4, sticky='w')
    opcoes = tk.Frame(w)
    opcoes.pack(anchor='w', padx=8)
    var = {k: tk.BooleanVar(value=True) for k in ('mesmo', 'robots', 'rew', 'zip', 'sitemap', 'form')}
    for k, t in (('mesmo', 'So o mesmo site (desmarque p/ seguir links de outros sites)'), ('robots', 'Respeitar robots.txt'), ('rew', 'Reescrever links (abrir offline)'), ('zip', 'Gerar .zip'),
                 ('sitemap', 'Ler sitemap.xml'), ('form', 'Botoes de download (so site proprio)')):
        tk.Checkbutton(opcoes, text=t, variable=var[k]).pack(side='left')
    var['form'].set(False)
    parar = threading.Event()
    registro = scrolledtext.ScrolledText(w, width=96, height=14, state='disabled')

    def log(msg):
        def add():
            registro.config(state='normal'); registro.insert('end', msg + '\n'); registro.see('end'); registro.config(state='disabled')
        w.after(0, add)

    def iniciar():
        urls = [u.strip() for u in caixa.get('1.0', 'end').splitlines() if u.strip().startswith('http')]
        pasta = filedialog.askdirectory(title='Pasta onde salvar o espelho') if urls else None
        if not urls or not pasta:
            log('cole um endereco http e escolha uma pasta')
            return
        parar.clear()
        threading.Thread(target=espelhar, daemon=True, args=(urls, os.path.join(pasta, 'espelho'), log, parar), kwargs=dict(
            profundidade=int(campos['prof'].get()), limite=int(campos['lim'].get()), mesmo_site=var['mesmo'].get(),
            filtros=filtros.get('1.0', 'end'), max_mb=int(campos['mb'].get()), conexoes=int(campos['con'].get()),
            pausa=float(campos['pausa'].get()), robots=var['robots'].get(), reescrever=var['rew'].get(), gerar_zip=var['zip'].get(), sitemap=var['sitemap'].get(), formularios=var['form'].get(),
            ext_excluidas={e for n, v in tipos.items() if not v.get() and n in GRUPOS for e in GRUPOS[n]}, outros=tipos['Outros'].get(),
            extras=[x for x in re.split(r'[\s,;]+', extras_caixa.get()) if x],
            cookies={L.split(':', 1)[0].strip().lower().replace('https://', '').replace('http://', '').split('/')[0]:
                     L.split(':', 1)[1].strip() for L in cookies_caixa.get('1.0', 'end').splitlines() if ':' in L and L.strip()})).start()

    botoes = tk.Frame(w)
    botoes.pack(anchor='w', padx=8, pady=4)
    tk.Button(botoes, text='Baixar', command=iniciar).pack(side='left')
    tk.Button(botoes, text='Parar', command=parar.set).pack(side='left', padx=8)
    registro.pack(padx=8, pady=8)
    w.mainloop()


if __name__ == '__main__':
    main()
