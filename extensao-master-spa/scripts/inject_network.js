// Main World, document_start: monkey patch de fetch e XHR. Guarda as ultimas chamadas em window.__MSPA_NET.
(() => {
  if (window.__MSPA_NET) return;
  const MAX = 500, BODY = 2000;
  const log = window.__MSPA_NET = [];
  const push = e => { log.push(e); if (log.length > MAX) log.shift(); };
  const cut = t => (t.length > BODY ? t.slice(0, BODY) + '…' : t);
  // shortcut: mascara so senha/token em JSON e form-urlencoded; corpo em outro formato sai como esta.
  const mask = t => cut(t).replace(/("?(?:password|passwd|senha|token|secret|authorization)"?\s*[:=]\s*)("[^"]*"|[^&,}\s]*)/gi, '$1"***"');
  const textual = ct => /json|text\/|xml|javascript|graphql/i.test(ct || '');
  const abs = u => { try { return new URL(u, location.href).href; } catch { return String(u); } };

  const origFetch = window.fetch;
  window.fetch = async function (input, init) {
    const isReq = input instanceof Request;
    const e = {
      type: 'fetch',
      method: ((init && init.method) || (isReq && input.method) || 'GET').toUpperCase(),
      url: abs(isReq ? input.url : input),
      t: Date.now(),
    };
    if (init && typeof init.body === 'string') e.reqBody = mask(init.body);
    try {
      const res = await origFetch.apply(this, arguments);
      e.status = res.status;
      e.ms = Date.now() - e.t;
      e.contentType = res.headers.get('content-type');
      if (textual(e.contentType)) res.clone().text().then(b => { e.resBody = mask(b); }, () => {});
      push(e);
      return res;
    } catch (err) {
      e.error = String(err);
      push(e);
      throw err;
    }
  };

  const X = XMLHttpRequest.prototype, open = X.open, send = X.send;
  X.open = function (method, url) {
    this.__mspa = { type: 'xhr', method: String(method).toUpperCase(), url: abs(url) };
    return open.apply(this, arguments);
  };
  X.send = function (body) {
    const e = this.__mspa;
    if (e) {
      e.t = Date.now();
      if (typeof body === 'string') e.reqBody = mask(body);
      this.addEventListener('loadend', () => {
        e.status = this.status;
        e.ms = Date.now() - e.t;
        e.contentType = this.getResponseHeader('content-type');
        if ((this.responseType === '' || this.responseType === 'text') && textual(e.contentType)) e.resBody = mask(this.responseText);
        push(e);
      });
    }
    return send.apply(this, arguments);
  };
})();
