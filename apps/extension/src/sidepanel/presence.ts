// Reconnect after a background worker restart; closing the panel disconnects the port.
export function trackPanelPresence() {
  let stopped = false;
  let port: chrome.runtime.Port | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const report = () => {
    void chrome.windows.getCurrent().then(win => {
      if (!stopped && win.id !== undefined) {
        try { port?.postMessage({ windowId: win.id, visible: document.visibilityState === 'visible' }); } catch { /* reconnect handles worker shutdown */ }
      }
    });
  };
  const connect = () => {
    if (stopped) return;
    port = chrome.runtime.connect({ name: 'kkulpick-sidepanel' });
    port.onDisconnect.addListener(() => {
      if (!stopped) timer = setTimeout(connect, 500);
    });
    report();
  };
  connect();
  document.addEventListener('visibilitychange', report);
  window.addEventListener('pagehide', () => {
    stopped = true;
    clearTimeout(timer);
    document.removeEventListener('visibilitychange', report);
    port?.disconnect();
  }, { once: true });
}
