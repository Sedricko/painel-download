"""Painel para espelhar paginas e arquivos publicos para leitura offline (alternativa leve ao HTTrack).

- espelho em pastas (dominio/caminho), com links reescritos para abrir offline; opcional: .zip no fim
- filtros no estilo HTTrack, um por linha: +*.pdf (inclui, mesmo de outro site)  -*.gif (exclui)
- profundidade (so conta paginas HTML), limite de paginas, MB por arquivo, varias conexoes, pausa entre pedidos
- retoma: arquivo ja baixado nao baixa de novo; respeita robots.txt (desligavel); ignora dominios de anuncio
Le sitemap.xml. Segue href/src/srcset/css url()/@import e enderecos completos dentro de html/css/js. Nao adivinha enderecos."""
import fnmatch, hashlib, os, re, threading, time, tkinter as tk, urllib.parse, urllib.request, urllib.robotparser, zipfile
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, scrolledtext

ANUNCIOS = ('doubleclick.net', 'googlesyndication.com', 'google-analytics.com', 'googletagmanager.com')
ATTR = re.compile(r'''(?:href|src|data-src|data-original|poster)\s*=\s*["']([^"'#]+)|url\(\s*["']?([^"')#]+)|@import\s+["']([^"']+)''', re.I)
SRCSET = re.compile(r'''srcset\s*=\s*["']([^"']+)''', re.I)
ABS = re.compile(r'''https?://[^\s"'<>()\\]+\.(?:css|js|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|pdf|zip|rar|gz|tgz|tar|exe|dll|mp3|mp4|avi|mov|wav|json|xml)\b''', re.I)


GRUPOS = {
    'Paginas': ('html', 'htm', 'php', 'asp', 'aspx', 'jsp', 'xhtml', 'shtml', ''),
    'Estilos e scripts': ('css', 'js', 'mjs', 'map'),
    'Imagens': ('jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'ico', 'bmp', 'tif', 'tiff', 'avif'),
    'Documentos': ('pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'rtf', 'odt', 'md', 'epub'),
    'Dados': ('json', 'xml', 'rss', 'atom', 'yaml', 'yml', 'sql'),
    'Compactados': ('zip', 'rar', '7z', 'tar', 'tgz', 'gz', 'bz2', 'xz', 'z'),
    'Programas': ('exe', 'dll', 'msi', 'apk', 'bat', 'sh', 'so', 'bin', 'jar', 'iso', 'dmg'),
    'Audio': ('mp3', 'mp2', 'wav', 'wma', 'ogg', 'flac', 'aac', 'm4a'),
    'Video': ('mp4', 'mov', 'mpg', 'mpeg', 'avi', 'asf', 'wmv', 'rm', 'vob', 'qt', 'vid', 'ac3', 'mkv', 'webm', 'flv'),
    'Fontes': ('woff', 'woff2', 'ttf', 'otf', 'eot'),
}
CONHECIDAS = {e for g in GRUPOS.values() for e in g}


def extensao(url):
    return os.path.splitext(urllib.parse.urlparse(url).path)[1].lstrip('.').lower()


def caminho_local(raiz, url):
    p = urllib.parse.urlparse(url)
    c = p.path
    if c.endswith('/') or not c:
        c += 'index.html'
    nome = re.sub(r'[<>:"|?*\\]', '_', c.strip('/'))
    if p.query:
        base, ext = os.path.splitext(nome)
        nome = base + '_' + hashlib.md5(p.query.encode()).hexdigest()[:8] + (ext or '.html')
    elif '.' not in os.path.basename(nome):
        nome += '.html'
    return os.path.join(raiz, re.sub(r'[<>:"|?*]', '_', p.netloc), nome)


def links(texto, base, extras=()):
    achados = [next(x for x in m if x) for m in ATTR.findall(texto)]
    if extras:  # extensions the user asked for: also look for them inside scripts ("dir/file.lua", 'https://x/y.lua')
        e = '|'.join(re.escape(x.lstrip('.*')) for x in extras)
        achados += re.findall(r'''["'`]([^"'`\s<>()]+\.(?:%s))(?:\?[^"'`\s]*)?["'`]''' % e, texto, re.I)
        achados += re.findall(r'''(https?://[^\s"'`<>()\\]+\.(?:%s))\b''' % e, texto, re.I)
    for ss in SRCSET.findall(texto):
        achados += [c.strip().split()[0] for c in ss.split(',') if c.strip()]
    achados += ABS.findall(texto)
    out = []
    for a in achados:
        u = urllib.parse.urljoin(base, a.strip()).split('#')[0]
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


def espelhar(urls, raiz, log, parar, profundidade=3, limite=200, mesmo_site=True, filtros='', max_mb=500,
             conexoes=4, pausa=0.3, robots=True, reescrever=True, gerar_zip=True, ext_excluidas=(), outros=True, extras=(),
             sitemap=True):
    os.makedirs(raiz, exist_ok=True)
    dominios = {urllib.parse.urlparse(u).netloc for u in urls}
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
                r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'leitura-pessoal'}), timeout=30)
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
        if not dest.lower().endswith(('.html', '.htm', '.css', '.js')):
            return []
        try:
            texto = open(dest, encoding='utf-8', errors='replace').read()
        except OSError:
            return []
        html = dest.lower().endswith(('.html', '.htm'))
        novos = []
        for v in links(texto, u, extras):
            eh_pagina = not (re.search(r'\.(css|js|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|pdf|zip|rar|gz|tgz|tar|exe|dll|mp3|mp4|avi|mov|wav|json|xml)(\?|$)', v, re.I) or extensao(v) in {x.lstrip('.*').lower() for x in extras})
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

            def troca(m):
                alvo = urllib.parse.urljoin(u, next(x for x in m.groups() if x)).split('#')[0]
                if alvo in mapa:
                    return m.group(0).replace(next(x for x in m.groups() if x), os.path.relpath(mapa[alvo], os.path.dirname(dest)).replace(os.sep, '/'))
                return m.group(0)
            def troca_set(m):  # srcset="a.jpg 1x, b.jpg 2x"
                partes = []
                for c in m.group(1).split(','):
                    d = c.strip().split(None, 1)
                    alvo = urllib.parse.urljoin(u, d[0]).split('#')[0] if d else ''
                    d[0:1] = [os.path.relpath(mapa[alvo], os.path.dirname(dest)).replace(os.sep, '/') if alvo in mapa else d[0]] if d else []
                    partes.append(' '.join(d))
                return m.group(0).replace(m.group(1), ', '.join(partes))
            novo = SRCSET.sub(troca_set, ATTR.sub(troca, texto))
            if novo != texto:
                open(dest, 'w', encoding='utf-8').write(novo)
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
    var = {k: tk.BooleanVar(value=True) for k in ('mesmo', 'robots', 'rew', 'zip', 'sitemap')}
    for k, t in (('mesmo', 'So o mesmo site'), ('robots', 'Respeitar robots.txt'), ('rew', 'Reescrever links (abrir offline)'), ('zip', 'Gerar .zip'),
                 ('sitemap', 'Ler sitemap.xml')):
        tk.Checkbutton(opcoes, text=t, variable=var[k]).pack(side='left')
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
            pausa=float(campos['pausa'].get()), robots=var['robots'].get(), reescrever=var['rew'].get(), gerar_zip=var['zip'].get(), sitemap=var['sitemap'].get(),
            ext_excluidas={e for n, v in tipos.items() if not v.get() and n in GRUPOS for e in GRUPOS[n]}, outros=tipos['Outros'].get(),
            extras=[x for x in re.split(r'[\s,;]+', extras_caixa.get()) if x])).start()

    botoes = tk.Frame(w)
    botoes.pack(anchor='w', padx=8, pady=4)
    tk.Button(botoes, text='Baixar', command=iniciar).pack(side='left')
    tk.Button(botoes, text='Parar', command=parar.set).pack(side='left', padx=8)
    registro.pack(padx=8, pady=8)
    w.mainloop()


if __name__ == '__main__':
    main()
