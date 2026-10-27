---
name: painel-download
description: Painel (janela no Windows) para baixar paginas, blogs, documentacao e arquivos publicos de um site num espelho em pastas e .zip, para o Claude ler offline. Use quando o usuario pedir para baixar/espelhar um site, blog ou pagina, quando o ambiente do Claude nao alcanca o dominio (bloqueado), ou quando a pagina precisa de varias paginas/arquivos de uma vez. O usuario roda o painel no PC dele e manda o .zip de volta.
---

# Painel de download (espelho de sites)

O ambiente do Claude muitas vezes bloqueia dominios (arxiv, hackmd, blogs). O painel resolve: o **usuario** roda no PC dele,
baixa o site e manda o `.zip` na conversa. So para **paginas e arquivos publicos**.

## Como entregar ao usuario
1. Envie os dois arquivos de `scripts/` (use SendUserFile): `painel_download.py` e `ABRIR_PAINEL.bat`. Peca para salvar os dois **na mesma pasta**.
2. Ele clica duas vezes em `ABRIR_PAINEL.bat` (precisa de Python com tkinter, o padrao do Windows).
3. Na janela: cola os enderecos (um por linha), escolhe a pasta, clica **Baixar**. No fim sai `espelho/` e `espelho.zip`.
4. Ele manda o `espelho.zip` (ou o `.zip` da pasta). Descompacte em pasta nova e vazia: `python3 -I` ao ler, nunca execute o que veio la.

## O que o painel faz
- Espelho em pastas (dominio/caminho) com links reescritos para abrir offline; opcional `.zip`.
- No fim gera `espelho/index.html` (abre o inicio do site, como o HTTrack) e `espelho/mapa.html` (esqueleto: todos os arquivos por pasta, com link direto e endereco original).
- Le o `sitemap.xml`/`.xml.gz` (e os `Sitemap:` do robots.txt): acha paginas publicas sem link. Caixa **Ler sitemap.xml**.
- Segue `href`, `src`, `srcset`, css `url()`/`@import` e enderecos completos de arquivo (qualquer formato: `.dll`, `.lua`, `.ps1`...) dentro de html/css/js.
- Filtros estilo HTTrack, um por linha: `+*.pdf` (inclui, mesmo de outro site), `-*.gif` (exclui); `.lua` vale como `+*.lua`.
- Caixas de tipo de arquivo (Paginas, Estilos e scripts, Imagens, Documentos, Dados, Compactados, Programas, Audio, Video, Fontes, Outros): tudo marcado, o usuario desmarca o que nao quer.
- Campo **Extensoes extras** (ex.: `lua, cfg`): procura essas extensoes tambem dentro de scripts, em caminhos relativos e absolutos.
- Profundidade (so conta paginas HTML), limite de paginas, MB por arquivo, varias conexoes (fila continua: arquivo lento nao trava os outros), pausa entre pedidos, respeita `Retry-After` do 429/503, preserva paginas em iso-8859-1/windows-1252, retoma (arquivo ja baixado nao baixa de novo), ignora dominios de anuncio.
- **Respeitar robots.txt**: ligado por padrao; so desligar em site do proprio usuario.
- Campo **Cookies** (so sites seus): para areas que pedem login (free/VIP). O usuario loga no navegador, copia o cookie e cola um por linha `site.com: cookie`; o painel usa o cookie certo em cada dominio. Login nao passa de um site para outro: um cookie por site, mesmo com a mesma senha.

## Limites (diga ao usuario)
- Nao faz login. Botoes de download (form `POST` com `_token` e so campos escondidos): so com a caixa **Botoes de download (so site proprio)**, desligada por padrao, e so no mesmo site; nunca envia form com campo de texto/senha.
- Sem a caixa **Renderizar JavaScript** (aba Avancado) nao acha nomes montados por codigo (`"dir/" + nome + ".lua"`) nem conteudo que so aparece depois de JavaScript. Com ela, cada pagina abre num navegador de verdade (Playwright: `pip install playwright`; usa o Edge/Chrome do PC) e entra o HTML final + tudo que o JavaScript pediu. Mais lento: uma pagina por vez.
- Nao adivinha enderecos nem varre servidores. Nao use para contornar protecoes, nem para CDNs/buckets de terceiros.
- Arquivos `.exe`/`.dll` ficam parados no zip; o usuario nao deve abrir os de fonte desconhecida.
- Erros `404` no log costumam ser textos de JavaScript que pareciam enderecos; sem problema.

## Teste
`python scripts/teste_painel.py` (sem internet, sem janela): servidor local com botao de download, form de login e sitemap.

## Dicas
- Site grande: profundidade 2-3, "So o mesmo site" marcado, limite 100-300 paginas.
- Imagens de posts costumam ficar em outro dominio (CDN); desmarque "So o mesmo site" ou adicione o dominio na lista de enderecos.
- Para ler: extraia o texto de `.html` (remova `<script>/<style>`), comece pelos posts relevantes e guarde so o necessario no repositorio.
