import React, { useEffect, useCallback, useRef } from "react";
import { X, ChevronLeft, ChevronRight } from "lucide-react";

/**
 * Fullscreen image lightbox with keyboard navigation + thumbnail strip.
 *
 * Zoom behaviour: pinch-to-zoom IS explicitly enabled inside the lightbox
 * (image container sets `touch-action: pinch-zoom`) — the global
 * double-tap/pinch block in `index.js` is bypassed via the container's
 * own gesture handler. Users can zoom photos freely but cannot zoom the
 * surrounding app UI.
 *
 * Navigation: arrow buttons, thumbnail clicks, keyboard arrow keys, AND
 * horizontal single-finger swipe on the image area. Swipe is suppressed
 * while a multi-touch pinch is in flight and when the visual viewport is
 * zoomed (so panning around a zoomed photo never accidentally advances
 * to the next image).
 *
 * Props:
 *  - images: string[] (full-resolution URLs — only the current one is ever loaded)
 *  - thumbnails?: string[] (optional 400 px tier used for the thumbnail strip)
 *  - index: number (current index)
 *  - onClose: () => void
 *  - onChange: (newIndex: number) => void
 */
export default function Lightbox({ images, thumbnails, index, onClose, onChange }) {
  const total = images?.length || 0;
  const stripRef = useRef(null);

  const prev = useCallback(() => {
    if (!total) return;
    onChange((index - 1 + total) % total);
  }, [index, total, onChange]);

  const next = useCallback(() => {
    if (!total) return;
    onChange((index + 1) % total);
  }, [index, total, onChange]);

  // ── Swipe tracking ────────────────────────────────────────────────
  // Single-finger horizontal swipe → prev/next. Auto-aborts if a second
  // finger touches down (= pinch in progress) or if the viewport is
  // currently zoomed (user is panning a zoomed image).
  const swipeRef = useRef({ startX: 0, startY: 0, active: false });
  const onTouchStart = useCallback((e) => {
    if (e.touches.length !== 1) { swipeRef.current.active = false; return; }
    // Suppress when the image is currently zoomed in.
    const scale = window.visualViewport?.scale ?? 1;
    if (scale > 1.05) { swipeRef.current.active = false; return; }
    swipeRef.current = {
      startX: e.touches[0].clientX,
      startY: e.touches[0].clientY,
      active: true,
    };
  }, []);
  const onTouchMove = useCallback((e) => {
    // Pinch detected mid-swipe → cancel.
    if (e.touches.length > 1) swipeRef.current.active = false;
  }, []);
  const onTouchEnd = useCallback((e) => {
    const s = swipeRef.current;
    if (!s.active) return;
    swipeRef.current.active = false;
    const t = e.changedTouches[0];
    if (!t) return;
    const dx = t.clientX - s.startX;
    const dy = t.clientY - s.startY;
    // Threshold: ≥40px horizontal AND clearly more horizontal than vertical.
    if (Math.abs(dx) < 40) return;
    if (Math.abs(dx) < Math.abs(dy) * 1.2) return;
    if (dx < 0) next(); else prev();
  }, [prev, next]);

  // ── Desktop mouse drag ────────────────────────────────────────────
  // Same gesture model as touch: press, drag horizontally, release.
  // Threshold matches touch (≥40 px). Cancelled on right-click or
  // when the cursor leaves the stage mid-drag.
  const dragRef = useRef({ startX: 0, startY: 0, active: false });
  const onMouseDown = useCallback((e) => {
    if (e.button !== 0) return; // only left button
    dragRef.current = { startX: e.clientX, startY: e.clientY, active: true };
  }, []);
  const onMouseUp = useCallback((e) => {
    const s = dragRef.current;
    if (!s.active) return;
    dragRef.current.active = false;
    const dx = e.clientX - s.startX;
    const dy = e.clientY - s.startY;
    if (Math.abs(dx) < 40) return;
    if (Math.abs(dx) < Math.abs(dy) * 1.2) return;
    if (dx < 0) next(); else prev();
  }, [prev, next]);
  const onMouseLeave = useCallback(() => { dragRef.current.active = false; }, []);

  // ── Desktop trackpad horizontal wheel ─────────────────────────────
  // Two-finger horizontal swipe on macOS / Precision trackpads emits
  // `wheel` events with `deltaX`. Accumulate until we cross a threshold,
  // then advance — with a cooldown so a single fling doesn't skip 5+
  // photos. Touchpad swipes typically deliver 100-300px of deltaX over
  // ~400ms; we trigger at 80 px accumulated.
  const wheelRef = useRef({ accum: 0, cooldownUntil: 0 });
  const onWheel = useCallback((e) => {
    // Vertical-dominant scroll (mouse wheel) → ignore. We only react
    // when the gesture is clearly horizontal.
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
    e.preventDefault();
    const now = performance.now();
    if (now < wheelRef.current.cooldownUntil) return;
    wheelRef.current.accum += e.deltaX;
    if (Math.abs(wheelRef.current.accum) >= 80) {
      if (wheelRef.current.accum < 0) prev(); else next();
      wheelRef.current.accum = 0;
      wheelRef.current.cooldownUntil = now + 400;
    }
  }, [prev, next]);
  // Reset accumulator when navigating via other means.
  useEffect(() => { wheelRef.current.accum = 0; }, [index]);

  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") prev();
      else if (e.key === "ArrowRight") next();
    };
    document.addEventListener("keydown", handler);
    // Lock scroll while lightbox is open
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // App-wide viewport meta is already zoom-friendly (`initial-scale=1`
    // without `maximum-scale` / `user-scalable=no`), so the OS pinch
    // gesture works inside the lightbox without any meta swap.

    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = prevOverflow;
    };
  }, [prev, next, onClose]);

  // Keep the active thumbnail in view as the user navigates.
  useEffect(() => {
    const strip = stripRef.current;
    if (!strip || index == null) return;
    const active = strip.querySelector(`[data-thumb-idx="${index}"]`);
    if (active && active.scrollIntoView) {
      active.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    }
  }, [index]);

  // Non-passive wheel listener on the stage — React's onWheel is passive
  // by default and preventDefault() is silently ignored. We need a manual
  // addEventListener with {passive:false} for trackpad horizontal swipes
  // to feel responsive (no rubber-band on the page).
  const stageRef = useRef(null);
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [onWheel]);

  if (!total || index == null) return null;

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/95 flex flex-col items-center justify-between select-none"
      onClick={onClose}
      data-testid="lightbox"
    >
      {/* Close */}
      <button
        onClick={(e) => { e.stopPropagation(); onClose(); }}
        className="absolute top-4 right-4 z-10 w-11 h-11 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition"
        aria-label="Затвори"
        data-testid="lightbox-close"
      >
        <X size={22} />
      </button>

      {/* Counter */}
      <div className="absolute top-5 left-1/2 -translate-x-1/2 text-white/80 text-sm font-mono z-10">
        {index + 1} / {total}
      </div>

      {/*
        Stage — image. `touch-action: pinch-zoom` re-enables the
        browser's native pinch gesture inside this container (the global
        gesture blocker in index.js skips elements with
        data-allow-pinch-zoom="1" — see the handler).
      */}
      <div
        ref={stageRef}
        className="flex-1 w-full flex items-center justify-center px-4 pt-14 pb-2 min-h-0 overflow-auto cursor-grab active:cursor-grabbing"
        data-allow-pinch-zoom="1"
        style={{ touchAction: "pinch-zoom" }}
        onClick={(e) => e.stopPropagation()}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onMouseDown={onMouseDown}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseLeave}
      >
        <img
          src={images[index]}
          alt=""
          className="max-w-full max-h-full object-contain"
          data-testid="lightbox-image"
          draggable={false}
          decoding="async"
          fetchpriority="high"
        />
      </div>

      {/* Prev / Next */}
      {total > 1 && (
        <>
          <button
            onClick={(e) => { e.stopPropagation(); prev(); }}
            className="absolute left-2 sm:left-4 top-1/2 -translate-y-1/2 w-11 h-11 sm:w-14 sm:h-14 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition z-10"
            aria-label="Предишна снимка"
            data-testid="lightbox-prev"
          >
            <ChevronLeft size={28} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); next(); }}
            className="absolute right-2 sm:right-4 top-1/2 -translate-y-1/2 w-11 h-11 sm:w-14 sm:h-14 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition z-10"
            aria-label="Следваща снимка"
            data-testid="lightbox-next"
          >
            <ChevronRight size={28} />
          </button>
        </>
      )}

      {/* Thumbnail strip — horizontally scrollable, click to jump */}
      {total > 1 && (
        <div
          ref={stripRef}
          onClick={(e) => e.stopPropagation()}
          className="w-full overflow-x-auto overflow-y-hidden bg-black/70 backdrop-blur-sm border-t border-white/10 px-3 py-2.5 flex gap-2 scroll-smooth"
          style={{ scrollbarWidth: "thin" }}
          data-testid="lightbox-strip"
        >
          {images.map((src, i) => (
            <button
              key={i}
              type="button"
              data-thumb-idx={i}
              onClick={(e) => { e.stopPropagation(); onChange(i); }}
              className={`relative shrink-0 w-20 h-14 sm:w-24 sm:h-16 rounded overflow-hidden border-2 transition ${
                i === index
                  ? "border-white"
                  : "border-transparent opacity-60 hover:opacity-100"
              }`}
              aria-label={`Снимка ${i + 1}`}
              data-testid={`lightbox-thumb-${i}`}
            >
              <img
                src={(thumbnails && thumbnails[i]) || src}
                alt=""
                loading="lazy"
                decoding="async"
                className="w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
