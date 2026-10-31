// Isolated world: ponte entre o popup (chrome.runtime) e os scripts do Main World (window.postMessage).
const pending = new Map();
let seq = 0;

window.addEventListener('message', ev => {
  const d = ev.data;
  if (ev.source !== window || !d || d.mspa !== 'res' || !pending.has(d.id)) return;
  pending.get(d.id)(d.res);
  pending.delete(d.id);
});

const ask = (cmd, arg) => new Promise(ok => {
  const id = `m${++seq}-${Math.random()}`;
  pending.set(id, ok);
  window.postMessage({ mspa: 'req', id, cmd, arg }, '*');
  setTimeout(() => pending.delete(id) && ok({ error: 'Scanner nao respondeu. Recarregue a pagina (F5).' }), 5000);
});

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  const p = msg.cmd === 'export'
    ? ask('export').then(data => data.error ? data : chrome.runtime.sendMessage({ cmd: 'save', data }))
    : ask(msg.cmd, msg.arg);
  p.then(reply, e => reply({ error: String(e.message || e) }));
  return true;
});
