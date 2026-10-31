// Main World: acha elementos interativos (HTML + handlers React via Fiber), destaca na tela e executa acoes.
(() => {
  if (window.__MSPA) return;
  const INTERACTIVE = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=tab],[role=menuitem],[role=checkbox],[onclick],[contenteditable=""],[contenteditable=true],[tabindex]:not([tabindex="-1"])';
  const ATTRS = ['id', 'name', 'type', 'role', 'aria-label', 'title', 'placeholder', 'href', 'data-testid', 'data-test', 'data-cy', 'contenteditable'];
  let elements = [];
  let overlay = null;

  const fiberOf = el => {
    const k = Object.keys(el).find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
    return k && el[k];
  };
  const typeName = t => t && (t.displayName || t.name || (t.render && (t.render.displayName || t.render.name)) || (t.type && (t.type.displayName || t.type.name)));
  const reactInfo = el => {
    const f = fiberOf(el);
    if (!f) return null;
    const props = f.memoizedProps || {};
    const components = [];
    for (let n = f.return; n && components.length < 6; n = n.return) {
      const name = typeof n.type !== 'string' && typeName(n.type);
      if (name && !components.includes(name)) components.push(name);
    }
    return {
      components,
      props: Object.keys(props).filter(k => k !== 'children'),
      handlers: Object.keys(props).filter(k => /^on[A-Z]/.test(k) && typeof props[k] === 'function'),
    };
  };

  const uniqueId = n => n.id && document.querySelectorAll('#' + CSS.escape(n.id)).length === 1;
  const cssPath = el => {
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== document.documentElement; n = n.parentElement) {
      if (uniqueId(n)) { parts.unshift('#' + CSS.escape(n.id)); break; }
      let s = n.localName;
      const same = n.parentElement ? [...n.parentElement.children].filter(c => c.localName === n.localName) : [];
      if (same.length > 1) s += `:nth-of-type(${same.indexOf(n) + 1})`;
      parts.unshift(s);
    }
    return parts.join(' > ');
  };
  const label = el => (el.innerText || el.value || el.getAttribute('aria-label') || el.placeholder || el.title || '').trim().replace(/\s+/g, ' ').slice(0, 100);

  // shortcut: nao entra em shadow roots nem iframes; se a SPA usar web components, varrer el.shadowRoot recursivamente.
  const scan = () => {
    elements = [];
    const items = [];
    for (const el of document.body.querySelectorAll('*')) {
      if (el.closest('#mspa-overlay,#mspa-panel')) continue;
      const react = reactInfo(el);
      const clickable = react && react.handlers.some(h => /^on(Click|MouseDown|PointerDown|KeyDown|Change|Submit)$/.test(h));
      if (!el.matches(INTERACTIVE) && !clickable) continue;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      const attrs = {};
      for (const a of ATTRS) if (el.hasAttribute(a)) attrs[a] = el.getAttribute(a);
      if (el.className && typeof el.className === 'string') attrs.class = el.className;
      items.push({
        i: elements.length,
        tag: el.localName,
        text: label(el),
        selector: cssPath(el),
        attrs,
        rect: { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) },
        react,
      });
      elements.push(el);
    }
    api.lastScan = { when: new Date().toISOString(), items };
    if (overlay) { highlight(false); highlight(true); }
    return api.lastScan;
  };

  const highlight = on => {
    if (on === undefined) on = !overlay;
    if (overlay) { overlay.remove(); overlay = null; }
    if (!on) return false;
    if (!api.lastScan) scan();
    overlay = document.createElement('div');
    overlay.id = 'mspa-overlay';
    overlay.style.cssText = 'position:absolute;left:0;top:0;width:0;height:0;z-index:2147483646;pointer-events:none';
    for (const it of api.lastScan.items) {
      const b = document.createElement('div');
      const color = it.react ? '#e11d48' : '#2563eb';
      b.style.cssText = `position:absolute;left:${it.rect.x}px;top:${it.rect.y}px;width:${it.rect.w}px;height:${it.rect.h}px;outline:2px solid ${color};background:${color}14;box-sizing:border-box`;
      const tag = document.createElement('span');
      tag.textContent = it.i;
      tag.style.cssText = `position:absolute;left:0;top:-14px;font:10px/14px monospace;color:#fff;background:${color};padding:0 3px`;
      b.append(tag);
      overlay.append(b);
    }
    document.documentElement.append(overlay);
    return true;
  };

  const el = i => {
    const e = elements[i];
    if (e && e.isConnected) return e;
    const it = api.lastScan && api.lastScan.items[i];
    return it && document.querySelector(it.selector); // SPA re-renderizou: tenta pelo seletor
  };

  // Valor por setter nativo + evento input: sem isso o React ignora (estado controlado).
  const typeInto = (e, value) => {
    e.focus();
    if (e.isContentEditable) { document.execCommand('selectAll'); document.execCommand('insertText', false, value); return; }
    const proto = e instanceof HTMLTextAreaElement ? HTMLTextAreaElement : e instanceof HTMLSelectElement ? HTMLSelectElement : HTMLInputElement;
    Object.getOwnPropertyDescriptor(proto.prototype, 'value').set.call(e, value);
    e.dispatchEvent(new Event('input', { bubbles: true }));
    e.dispatchEvent(new Event('change', { bubbles: true }));
  };

  const act = (i, action, value) => {
    const e = el(i);
    if (!e) return { error: `Elemento ${i} nao existe mais. Faca um novo scan.` };
    if (action === 'show') {
      e.scrollIntoView({ block: 'center', behavior: 'smooth' });
      const old = e.style.outline;
      e.style.outline = '3px solid #f59e0b';
      setTimeout(() => { e.style.outline = old; }, 1500);
    } else if (action === 'click') e.click();
    else if (action === 'type') typeInto(e, String(value == null ? '' : value));
    else return { error: 'Acao desconhecida: ' + action };
    return { ok: true };
  };

  const api = window.__MSPA = { lastScan: null, scan, highlight, el, act };

  const handlers = {
    scan: () => {
      const s = scan();
      return { count: s.items.length, react: s.items.filter(i => i.react).length, network: (window.__MSPA_NET || []).length };
    },
    highlight: on => ({ on: highlight(on) }),
    act: a => act(a.i, a.action, a.value),
    export: () => ({
      url: location.href,
      title: document.title,
      when: new Date().toISOString(),
      dom: api.lastScan || scan(),
      network: window.__MSPA_NET || [],
    }),
  };

  window.addEventListener('message', ev => {
    const d = ev.data;
    if (ev.source !== window || !d || d.mspa !== 'req' || !handlers[d.cmd]) return;
    let res;
    try { res = handlers[d.cmd](d.arg); } catch (e) { res = { error: String(e) }; }
    window.postMessage({ mspa: 'res', id: d.id, res: JSON.parse(JSON.stringify(res)) }, '*');
  });
})();
