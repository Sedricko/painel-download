// Salva o JSON que o content_manager manda (Export JSON).
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.cmd !== 'save' || sender.id !== chrome.runtime.id) return;
  let host = 'pagina';
  try { host = new URL(msg.data.url).hostname || host; } catch {}
  const filename = `master-spa/${host}-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
  // shortcut: data: URL (service worker nao tem createObjectURL); se arquivos muito grandes falharem, trocar por offscreen document + blob.
  const url = 'data:application/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(msg.data, null, 2));
  chrome.downloads.download({ url, filename, saveAs: false }, id =>
    reply(chrome.runtime.lastError ? { error: chrome.runtime.lastError.message } : { ok: true, id, filename }));
  return true;
});
