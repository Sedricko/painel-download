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
- Le o `sitemap.xml` (e os `Sitemap:` do robots.txt): acha paginas publicas sem link. Caixa **Ler sitemap.xml**.
- Segue `href`, `src`, `srcset`, css `url()`/`@import` e enderecos completos dentro de html/css/js.
- Filtros estilo HTTrack, um por linha: `+*.pdf` (inclui, mesmo de outro site), `-*.gif` (exclui); `.lua` vale como `+*.lua`.
- Caixas de tipo de arquivo (Paginas, Estilos e scripts, Imagens, Documentos, Dados, Compactados, Programas, Audio, Video, Fontes, Outros): tudo marcado, o usuario desmarca o que nao quer.
- Campo **Extensoes extras** (ex.: `lua, cfg`): procura essas extensoes tambem dentro de scripts, em caminhos relativos e absolutos.
- Profundidade (so conta paginas HTML), limite de paginas, MB por arquivo, varias conexoes, pausa entre pedidos, retoma (arquivo ja baixado nao baixa de novo), ignora dominios de anuncio.
- **Respeitar robots.txt**: ligado por padrao; so desligar em site do proprio usuario.

## Limites (diga ao usuario)
- Nao faz login, nao envia formularios (`POST` com token): downloads por botao de formulario o usuario baixa no navegador.
- Nao acha nomes montados por codigo (`"dir/" + nome + ".lua"`), nem conteudo que so aparece depois de JavaScript.
- Nao adivinha enderecos nem varre servidores. Nao use para contornar protecoes, nem para CDNs/buckets de terceiros.
- Arquivos `.exe`/`.dll` ficam parados no zip; o usuario nao deve abrir os de fonte desconhecida.
- Erros `404` no log costumam ser textos de JavaScript que pareciam enderecos; sem problema.

## Dicas
- Site grande: profundidade 2-3, "So o mesmo site" marcado, limite 100-300 paginas.
- Imagens de posts costumam ficar em outro dominio (CDN); desmarque "So o mesmo site" ou adicione o dominio na lista de enderecos.
- Para ler: extraia o texto de `.html` (remova `<script>/<style>`), comece pelos posts relevantes e guarde so o necessario no repositorio.
