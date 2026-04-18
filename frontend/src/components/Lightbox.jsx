import React, { useEffect, useCallback } from "react";
import { X, ChevronLeft, ChevronRight } from "lucide-react";

/**
 * Fullscreen image lightbox with keyboard & touch navigation.
 * Props:
 *  - images: string[] (URLs)
 *  - index: number (current index)
 *  - onClose: () => void
 *  - onChange: (newIndex: number) => void
 */
export default function Lightbox({ images, index, onClose, onChange }) {
  const total = images?.length || 0;

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
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = prevOverflow;
    };
  }, [prev, next, onClose]);

  // Swipe support (mobile)
  const touchStartX = React.useRef(0);
  const onTouchStart = (e) => { touchStartX.current = e.touches[0].clientX; };
  const onTouchEnd = (e) => {
    const dx = e.changedTouches[0].clientX - touchStartX.current;
    if (Math.abs(dx) > 50) (dx > 0 ? prev : next)();
  };

  if (!total || index == null) return null;

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/95 flex items-center justify-center select-none"
      onClick={onClose}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
      data-testid="lightbox"
    >
      {/* Close */}
      <button
        onClick={(e) => { e.stopPropagation(); onClose(); }}
        className="absolute top-4 right-4 w-11 h-11 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition"
        aria-label="Затвори"
        data-testid="lightbox-close"
      >
        <X size={22} />
      </button>

      {/* Counter */}
      <div className="absolute top-5 left-1/2 -translate-x-1/2 text-white/80 text-sm font-mono">
        {index + 1} / {total}
      </div>

      {/* Image */}
      <img
        src={images[index]}
        alt=""
        onClick={(e) => e.stopPropagation()}
        className="max-w-[95vw] max-h-[90vh] object-contain"
        data-testid="lightbox-image"
      />

      {/* Prev / Next */}
      {total > 1 && (
        <>
          <button
            onClick={(e) => { e.stopPropagation(); prev(); }}
            className="absolute left-2 sm:left-4 top-1/2 -translate-y-1/2 w-11 h-11 sm:w-14 sm:h-14 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition"
            aria-label="Предишна снимка"
            data-testid="lightbox-prev"
          >
            <ChevronLeft size={28} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); next(); }}
            className="absolute right-2 sm:right-4 top-1/2 -translate-y-1/2 w-11 h-11 sm:w-14 sm:h-14 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition"
            aria-label="Следваща снимка"
            data-testid="lightbox-next"
          >
            <ChevronRight size={28} />
          </button>
        </>
      )}
    </div>
  );
}
