import type { Message } from '../shared/messages';

// Track the actual panel document, scoped to its browser window (not every window).
const visible = new Map<number, boolean>();
const panels = new Map<chrome.runtime.Port, { windowId: number; visible: boolean }>();
function publish(windowId: number, open: boolean) {
  visible.set(windowId, open);
  void chrome.tabs.query({ windowId }).then(tabs => {
    for (const tab of tabs) if (tab.id !== undefined)
      void chrome.tabs.sendMessage(tab.id, { type: 'panelVisibility', open } satisfies Message).catch(() => undefined);
  }).catch(() => undefined);
}
export function panelIsOpen(windowId: number) { return visible.get(windowId) ?? false; }
export function panelOpened(windowId: number) { publish(windowId, true); }

chrome.runtime.onConnect.addListener(port => {
  if (port.name !== 'kkulpick-sidepanel' || port.sender?.url !== chrome.runtime.getURL('sidepanel.html')) return;
  port.onMessage.addListener((msg: { windowId?: number; visible?: boolean }) => {
    if (!Number.isInteger(msg.windowId) || typeof msg.visible !== 'boolean') return;
    const windowId = msg.windowId!;
    panels.set(port, { windowId, visible: msg.visible });
    publish(windowId, [...panels.values()].some(p => p.windowId === windowId && p.visible));
  });
  port.onDisconnect.addListener(() => {
    const panel = panels.get(port);
    panels.delete(port);
    if (panel) publish(panel.windowId, [...panels.values()].some(p => p.windowId === panel.windowId && p.visible));
  });
});

// Newer Chrome also reports switching away from a still-mounted panel.
type PanelEvent = { addListener: (callback: (info: { windowId: number }) => void) => void };
const events = chrome.sidePanel as typeof chrome.sidePanel & { onOpened?: PanelEvent; onClosed?: PanelEvent };
events.onOpened?.addListener(info => publish(info.windowId, true));
events.onClosed?.addListener(info => publish(info.windowId, false));
chrome.windows.onRemoved.addListener(windowId => visible.delete(windowId));
