const out = document.getElementById('out');
const activeTab = async () => (await chrome.tabs.query({ active: true, currentWindow: true }))[0];
const send = async cmd => {
  try { return await chrome.tabs.sendMessage((await activeTab()).id, { cmd }); }
  catch { return { error: 'Sem acesso a esta aba. Recarregue a pagina (F5) e tente de novo.' }; }
};
const show = text => { out.textContent = text; };

document.getElementById('scan').onclick = async () => {
  const r = await send('scan');
  show(r.error || `${r.count} elementos (${r.react} com React). Rede: ${r.network} chamadas.`);
};
document.getElementById('hl').onclick = async () => {
  const r = await send('highlight');
  show(r.error || (r.on ? 'Destaque ligado.' : 'Destaque desligado.'));
};
document.getElementById('export').onclick = async () => {
  const r = await send('export');
  show(r.error || `Salvo em Downloads/${r.filename}`);
};
document.getElementById('panel').onclick = async () => {
  try {
    await chrome.scripting.executeScript({ target: { tabId: (await activeTab()).id }, world: 'MAIN', files: ['scripts/inject_panel.js'] });
    window.close();
  } catch (e) { show(String(e.message || e)); }
};
