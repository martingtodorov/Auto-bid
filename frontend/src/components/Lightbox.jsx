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
 * Navigation: ONLY explicit actions change the image — arrow buttons,
 * thumbnail clicks, keyboard arrow keys. Swipe-to-advance is intentionally
 * removed so pinch + pan gestures inside a zoomed image aren't hijacked
 * as accidental "next photo" swipes.
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

    // Re-enable pinch zoom for the duration the lightbox is open.
    // The app-wide viewport meta locks scale to 1 (see public/index.html)
    // and CSS `touch-action` alone cannot override it on mobile browsers.
    // We swap the meta's content attribute while the viewer is mounted,
    // then restore the locked value on close.
    const metaEl = document.querySelector('meta[name="viewport"]');
    const prevViewport = metaEl ? metaEl.getAttribute("content") : null;
    if (metaEl) {
      metaEl.setAttribute(
        "content",
        "width=device-width, initial-scale=1, maximum-scale=5, user-scalable=yes, viewport-fit=cover"
      );
    }

    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = prevOverflow;
      if (metaEl && prevViewport != null) metaEl.setAttribute("content", prevViewport);
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
        className="flex-1 w-full flex items-center justify-center px-4 pt-14 pb-2 min-h-0 overflow-auto"
        data-allow-pinch-zoom="1"
        style={{ touchAction: "pinch-zoom" }}
        onClick={(e) => e.stopPropagation()}
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
