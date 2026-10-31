// Teste sem internet: carrega a extensao no Chromium, abre pagina local "SPA" e confere scan, rede, export e painel.
// Rodar: node teste_extensao.js
const assert = require('assert');
const http = require('http');
const os = require('os'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright');

const PAGE = `<!doctype html><title>SPA teste</title><body>
<button id="b1">Salvar</button><input id="nome" placeholder="Nome"><div id="fake" style="width:50px;height:20px">React</div>
<a href="#x">Link</a><div style="display:none"><button>escondido</button></div>
<script>
  function MeuBotao() {}
  const el = document.getElementById('fake');
  el.__reactFiber$abc = { memoizedProps: { onClick() { window.clicou = 1; }, children: 'x' }, return: { type: 'div', return: { type: MeuBotao, return: null } } };
  el.onclick = () => { window.clicou = 1; };
  let digitado = ''; document.getElementById('nome').addEventListener('input', e => { digitado = e.target.value; window.digitado = digitado; });
  fetch('/api/dados', { method: 'POST', body: JSON.stringify({ usuario: 'a', senha: 'segredo' }) });
  const x = new XMLHttpRequest(); x.open('GET', '/api/xhr'); x.send();
</script></body>`;

(async () => {
  const server = http.createServer((req, res) => {
    if (req.url.startsWith('/api')) { res.setHeader('content-type', 'application/json'); return res.end('{"ok":true}'); }
    res.setHeader('content-type', 'text/html'); res.end(PAGE);
  }).listen(0);
  const base = `http://127.0.0.1:${server.address().port}/`;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mspa-'));
  const ctx = await chromium.launchPersistentContext(dir, {
    headless: true, channel: 'chromium', acceptDownloads: true,
    args: [`--disable-extensions-except=${__dirname}`, `--load-extension=${__dirname}`],
  });
  try {
    const sw = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
    const page = await ctx.newPage();
    await page.goto(base);
    await page.waitForFunction(() => window.__MSPA && window.__MSPA_NET.length >= 2);

    // popup -> content_manager -> main world (mesmo caminho do botao)
    const send = cmd => sw.evaluate(async cmd => {
      const [tab] = await chrome.tabs.query({ active: true });
      return chrome.tabs.sendMessage(tab.id, { cmd });
    }, cmd);

    const scan = await send('scan');
    assert.strictEqual(scan.count, 4, JSON.stringify(scan)); // b1, nome, fake (React), link; escondido fica fora
    assert.strictEqual(scan.react, 1);
    assert.strictEqual(scan.network, 2);

    assert.deepStrictEqual(await send('highlight'), { on: true });
    assert.strictEqual(await page.locator('#mspa-overlay > div').count(), 4);

    const dom = await page.evaluate(() => window.__MSPA.lastScan.items);
    const fake = dom.find(i => i.attrs.id === 'fake');
    assert.deepStrictEqual(fake.react.components, ['MeuBotao']);
    assert.deepStrictEqual(fake.react.handlers, ['onClick']);
    assert.strictEqual(dom.find(i => i.attrs.id === 'nome').selector, '#nome');

    const net = await page.evaluate(() => window.__MSPA_NET);
    const post = net.find(n => n.method === 'POST');
    assert.ok(post.reqBody.includes('"senha":"***"') && !post.reqBody.includes('segredo'), post.reqBody);
    assert.ok(net.find(n => n.type === 'xhr').resBody.includes('ok'));

    const exp = await send('export');
    assert.ok(exp.ok && /^master-spa\/127\.0\.0\.1-.*\.json$/.test(exp.filename), JSON.stringify(exp));

    // Fase 2: no uso real o popup injeta via executeScript (activeTab do clique); o teste nao tem esse clique.
    await page.evaluate(() => { const a = Element.prototype.attachShadow; Element.prototype.attachShadow = function () { return a.call(this, { mode: 'open' }); }; }); // so no teste: closed nao deixa o Playwright ver
    await page.addScriptTag({ path: path.join(__dirname, 'scripts/inject_panel.js') });
    const panel = page.locator('#mspa-panel');
    await panel.locator('input.v').fill('Maria');
    await panel.locator('li', { hasText: 'Nome' }).getByText('Digitar').click();
    await panel.locator('li', { hasText: 'React' }).getByText('Clicar').click();
    assert.strictEqual(await page.evaluate(() => window.digitado), 'Maria');
    assert.strictEqual(await page.evaluate(() => window.clicou), 1);
    await panel.locator('input.f').fill('meubotao');
    assert.strictEqual(await panel.locator('li').count(), 1);
    console.log('OK: scan, React Fiber, rede (senha mascarada), export, painel');
  } finally {
    await ctx.close(); server.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
