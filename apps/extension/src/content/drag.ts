import { useCallback, useEffect, useRef, useState, type MouseEvent, type PointerEvent } from 'react';

// 플로팅 카드를 사용자가 끌어서 옮길 수 있게 한다.
// - 5px 넘게 움직여야 끌기로 본다. 그보다 짧으면 평소처럼 클릭(사이드 패널 열기)이 된다.
// - 끌고 놓은 직후의 클릭은 막는다(옮기다가 패널이 열리지 않도록).
// - 옮긴 위치는 chrome.storage.local에 저장해 다른 페이지에서도 같은 자리에 띄운다.
// - 창 크기가 바뀌거나 저장된 위치가 화면 밖이면 화면 안으로 당긴다.

const KEY = 'kp.floating.position';
const MARGIN = 8;
const THRESHOLD = 5;

interface Pos {
  x: number;
  y: number;
}

/** 확장 밖(개발용 미리보기)에서는 저장하지 않는다 */
const store = () => (typeof chrome !== 'undefined' ? chrome.storage?.local : undefined);

function clamp(p: Pos, w: number, h: number): Pos {
  const maxX = Math.max(MARGIN, window.innerWidth - w - MARGIN);
  const maxY = Math.max(MARGIN, window.innerHeight - h - MARGIN);
  return { x: Math.min(Math.max(MARGIN, p.x), maxX), y: Math.min(Math.max(MARGIN, p.y), maxY) };
}

export function useDragPosition() {
  const [pos, setPos] = useState<Pos | null>(null);
  const el = useRef<HTMLElement | null>(null);
  const suppressClick = useRef(false);

  useEffect(() => {
    store()
      ?.get(KEY)
      .then((v) => {
        const p = v[KEY] as Pos | undefined;
        if (p && Number.isFinite(p.x) && Number.isFinite(p.y)) setPos((cur) => cur ?? p);
      })
      .catch(() => undefined);
  }, []);

  // 창 크기가 바뀌면 화면 안으로 다시 맞춘다.
  useEffect(() => {
    if (!pos) return;
    const fit = () => {
      const r = el.current?.getBoundingClientRect();
      if (!r) return;
      const next = clamp(pos, r.width, r.height);
      if (next.x !== pos.x || next.y !== pos.y) setPos(next);
    };
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, [pos]);

  const onPointerDown = useCallback((e: PointerEvent<HTMLElement>) => {
    if (e.button !== 0) return;
    // 직전 끌기 뒤에 클릭이 오지 않았더라도(바깥에서 놓음) 새로 누르면 다시 클릭할 수 있다.
    suppressClick.current = false;
    const target = e.currentTarget;
    el.current = target;
    const r = target.getBoundingClientRect();
    const start = { x: e.clientX, y: e.clientY };
    let moved = false;
    let last: Pos | null = null;
    const move = (ev: globalThis.PointerEvent) => {
      const dx = ev.clientX - start.x;
      const dy = ev.clientY - start.y;
      if (!moved && Math.hypot(dx, dy) < THRESHOLD) return;
      moved = true;
      ev.preventDefault();
      last = clamp({ x: r.left + dx, y: r.top + dy }, r.width, r.height);
      setPos(last);
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
      if (!moved) return;
      suppressClick.current = true;
      if (last) void store()?.set({ [KEY]: last }).catch(() => undefined);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
  }, []);

  const onClickCapture = useCallback((e: MouseEvent<HTMLElement>) => {
    if (!suppressClick.current) return;
    suppressClick.current = false;
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const ref = useCallback((node: HTMLElement | null) => {
    if (node) el.current = node;
  }, []);

  return {
    ref,
    style: pos ? { left: pos.x, top: pos.y, right: 'auto' } : undefined,
    onPointerDown,
    onClickCapture,
  };
}
