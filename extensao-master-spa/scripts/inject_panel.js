// Fase 2, Main World: painel em Shadow DOM fechado. Lista o scan e executa acoes (ver, clicar, digitar).
(() => {
  const S = window.__MSPA;
  if (!S) return alert('Master SPA: recarregue a pagina (F5) e tente de novo.');
  const old = document.getElementById('mspa-panel');
  if (old) return old.remove(); // clicar de novo fecha

  const host = document.createElement('div');
  host.id = 'mspa-panel';
  const root = host.attachShadow({ mode: 'closed' });
  root.innerHTML = `
    <style>
      .box { position: fixed; top: 12px; right: 12px; width: 360px; max-height: 75vh; display: flex; flex-direction: column;
             font: 12px system-ui, sans-serif; color: #111; background: #fff; border: 1px solid #999; border-radius: 8px;
             box-shadow: 0 6px 24px #0004; z-index: 2147483647; }
      header { display: flex; gap: 6px; align-items: center; padding: 8px; border-bottom: 1px solid #ddd; font-weight: 600; }
      header span { flex: 1; }
      .tools { display: flex; gap: 6px; padding: 8px; }
      input { flex: 1; min-width: 0; padding: 4px 6px; font: inherit; }
      ul { list-style: none; margin: 0; padding: 0 8px 8px; overflow: auto; }
      li { display: flex; gap: 4px; align-items: center; padding: 4px 0; border-top: 1px solid #eee; }
      li .t { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      li .r { color: #e11d48; }
      button { font: inherit; padding: 2px 6px; cursor: pointer; }
      .msg { padding: 0 8px 6px; color: #b45309; min-height: 1em; }
    </style>
    <div class="box" role="dialog" aria-label="Master SPA">
      <header><span>Master SPA</span><button class="re">Re-scan</button><button class="x" aria-label="Fechar">×</button></header>
      <div class="tools"><input class="f" placeholder="Filtrar (texto, tag, componente)"><input class="v" placeholder="Texto para Digitar"></div>
      <div class="msg" role="status"></div>
      <ul></ul>
    </div>`;
  const $ = s => root.querySelector(s);
  const ul = $('ul'), filter = $('.f'), value = $('.v'), msg = $('.msg');
  const typable = it => /^(input|textarea|select)$/.test(it.tag) || it.attrs.contenteditable !== undefined;
  const btn = (text, fn) => { const b = document.createElement('button'); b.textContent = text; b.onclick = fn; return b; };
  const run = (i, action) => { const r = S.act(i, action, value.value); msg.textContent = r.error || ''; };

  const render = () => {
    const q = filter.value.toLowerCase();
    const items = S.lastScan.items.filter(it => !q ||
      [it.text, it.tag, it.selector, ...(it.react ? it.react.components : [])].join(' ').toLowerCase().includes(q));
    ul.replaceChildren(...items.slice(0, 300).map(it => {
      const li = document.createElement('li');
      const t = document.createElement('span');
      t.className = 't';
      t.textContent = `#${it.i} <${it.tag}> ${it.text}`;
      t.title = it.selector;
      li.append(t);
      if (it.react && it.react.components[0]) {
        const r = document.createElement('span');
        r.className = 'r';
        r.textContent = it.react.components[0];
        li.append(r);
      }
      li.append(btn('Ver', () => run(it.i, 'show')), btn('Clicar', () => run(it.i, 'click')));
      if (typable(it)) li.append(btn('Digitar', () => run(it.i, 'type')));
      return li;
    }));
    msg.textContent = items.length > 300 ? `Mostrando 300 de ${items.length}. Use o filtro.` : '';
  };

  if (!S.lastScan) S.scan();
  filter.oninput = render;
  $('.re').onclick = () => { S.scan(); render(); };
  $('.x').onclick = () => host.remove();
  document.documentElement.append(host);
  render();
})();
