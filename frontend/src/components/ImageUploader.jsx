import React, { useRef, useState, useEffect } from "react";
import { Upload, X, Image as ImageIcon, AlertCircle, Check, Move, GripVertical, ArrowRightLeft } from "lucide-react";

const MAX_SIZE = 2 * 1024 * 1024;
const LONG_PRESS_MS = 220;

// Shared pointer-drag state across all uploader instances (cross-category drag)
const pointerState = {
  active: false,
  startX: 0, startY: 0,
  category: null, idx: null,
  ghost: null,
  longPressTimer: null,
  lastTargetSlot: null,       // [category, idx] of currently-highlighted slot
  onDropResolver: null,
};

function clearGhost() {
  if (pointerState.ghost) {
    pointerState.ghost.remove();
    pointerState.ghost = null;
  }
}

function clearTargetHighlight() {
  document.querySelectorAll('[data-drag-target="true"]').forEach((el) => {
    el.removeAttribute("data-drag-target");
  });
}

export default function ImageUploader({
  images = [],
  onChange,
  max = 8,
  min = 0,
  label,
  helper,
  testId = "image-uploader",
  category,
  onMoveBetween,
  availableCategories = [],
}) {
  const ref = useRef(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const [dragOverGrid, setDragOverGrid] = useState(false);
  const [menuOpen, setMenuOpen] = useState(null);
  const [touchDragging, setTouchDragging] = useState(false);

  // Cleanup on unmount
  useEffect(() => () => { clearGhost(); clearTargetHighlight(); }, []);

  const compress = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement("canvas");
          const maxDim = 1600;
          let w = img.width, h = img.height;
          if (w > maxDim || h > maxDim) {
            if (w > h) { h = (h / w) * maxDim; w = maxDim; }
            else { w = (w / h) * maxDim; h = maxDim; }
          }
          canvas.width = w; canvas.height = h;
          const ctx = canvas.getContext("2d");
          ctx.drawImage(img, 0, 0, w, h);
          resolve(canvas.toDataURL("image/jpeg", 0.82));
        };
        img.onerror = reject;
        img.src = e.target.result;
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  const handleFiles = async (files) => {
    const arr = Array.from(files).slice(0, max - images.length);
    const compressed = [];
    for (const f of arr) {
      if (f.size > MAX_SIZE * 3) continue;
      try { compressed.push(await compress(f)); } catch {}
    }
    onChange([...images, ...compressed]);
  };

  const remove = (idx) => onChange(images.filter((_, i) => i !== idx));

  const reorder = (fromIdx, toIdx) => {
    if (fromIdx === toIdx || toIdx == null) return;
    const next = [...images];
    const [item] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, item);
    onChange(next);
  };

  // ===== HTML5 drag (desktop) =====
  const onDragStart = (e, idx) => {
    e.dataTransfer.effectAllowed = "move";
    const payload = JSON.stringify({ category, idx });
    e.dataTransfer.setData("application/x-image-move", payload);
    e.dataTransfer.setData("text/plain", payload);
  };
  const parseDrag = (e) => {
    try {
      const raw = e.dataTransfer.getData("application/x-image-move") || e.dataTransfer.getData("text/plain");
      if (!raw) return null;
      const d = JSON.parse(raw);
      if (typeof d !== "object" || !d.category) return null;
      return d;
    } catch { return null; }
  };
  const onSlotDragOver = (e, idx) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOverIdx(idx);
  };
  const onSlotDrop = (e, toIdx) => {
    e.preventDefault();
    setDragOverIdx(null); setDragOverGrid(false);
    const d = parseDrag(e); if (!d) return;
    if (d.category === category) reorder(d.idx, toIdx);
    else if (onMoveBetween) onMoveBetween(d.category, d.idx, category, toIdx);
  };
  const onGridDragOver = (e) => {
    if (e.dataTransfer.types.includes("application/x-image-move") || e.dataTransfer.types.includes("text/plain")) {
      e.preventDefault();
      setDragOverGrid(true);
    }
  };
  const onGridDrop = (e) => {
    e.preventDefault();
    setDragOverGrid(false);
    const d = parseDrag(e); if (!d) return;
    if (d.category !== category && onMoveBetween) onMoveBetween(d.category, d.idx, category, null);
  };

  // ===== Touch drag (mobile) =====
  const onTouchStart = (e, idx, src) => {
    if (e.touches.length !== 1) return;
    const t = e.touches[0];
    pointerState.startX = t.clientX;
    pointerState.startY = t.clientY;
    pointerState.category = category;
    pointerState.idx = idx;
    pointerState.active = false;

    if (pointerState.longPressTimer) clearTimeout(pointerState.longPressTimer);
    pointerState.longPressTimer = setTimeout(() => {
      // Enter drag mode — create floating ghost
      pointerState.active = true;
      setTouchDragging(true);
      // Haptic (Android/iOS best-effort)
      try { if (navigator.vibrate) navigator.vibrate(12); } catch {}

      const ghost = document.createElement("div");
      ghost.style.cssText = `position:fixed;left:0;top:0;width:120px;height:90px;background-image:url("${src.replace(/"/g, '\\"')}");background-size:cover;background-position:center;border-radius:8px;box-shadow:0 12px 32px rgba(0,0,0,.35);pointer-events:none;z-index:9999;transform:translate(${pointerState.startX - 60}px, ${pointerState.startY - 45}px) scale(1.05);transition:transform .05s linear;border:2px solid hsl(158 60% 30%);`;
      document.body.appendChild(ghost);
      pointerState.ghost = ghost;
      // Prevent page scroll while dragging
      document.body.style.overflow = "hidden";
      document.body.style.touchAction = "none";
    }, LONG_PRESS_MS);
  };

  const onTouchMove = (e) => {
    if (!pointerState.longPressTimer && !pointerState.active) return;
    const t = e.touches[0];
    const dx = t.clientX - pointerState.startX;
    const dy = t.clientY - pointerState.startY;

    // If user moves before long-press timer fires → cancel (treat as scroll)
    if (!pointerState.active) {
      if (Math.abs(dx) > 8 || Math.abs(dy) > 8) {
        clearTimeout(pointerState.longPressTimer);
        pointerState.longPressTimer = null;
      }
      return;
    }

    // Active drag
    e.preventDefault();
    if (pointerState.ghost) {
      pointerState.ghost.style.transform = `translate(${t.clientX - 60}px, ${t.clientY - 45}px) scale(1.05)`;
    }
    // Find target slot under finger
    const el = document.elementFromPoint(t.clientX, t.clientY);
    clearTargetHighlight();
    pointerState.lastTargetSlot = null;
    if (el) {
      const slot = el.closest("[data-uploader-slot]");
      if (slot) {
        slot.setAttribute("data-drag-target", "true");
        pointerState.lastTargetSlot = {
          cat: slot.getAttribute("data-uploader-category"),
          idx: parseInt(slot.getAttribute("data-uploader-idx"), 10),
        };
      } else {
        const grid = el.closest("[data-uploader-grid]");
        if (grid) {
          grid.setAttribute("data-drag-target", "true");
          pointerState.lastTargetSlot = {
            cat: grid.getAttribute("data-uploader-category"),
            idx: null,
          };
        }
      }
    }

    // Auto-scroll near viewport edges
    const margin = 60;
    if (t.clientY < margin) window.scrollBy(0, -8);
    else if (t.clientY > window.innerHeight - margin) window.scrollBy(0, 8);
  };

  const onTouchEnd = () => {
    if (pointerState.longPressTimer) clearTimeout(pointerState.longPressTimer);
    pointerState.longPressTimer = null;
    if (!pointerState.active) return;

    const target = pointerState.lastTargetSlot;
    const src = pointerState.category;
    const fromIdx = pointerState.idx;
    clearGhost();
    clearTargetHighlight();
    document.body.style.overflow = "";
    document.body.style.touchAction = "";
    pointerState.active = false;
    setTouchDragging(false);

    if (target && src) {
      if (target.cat === src) {
        if (target.idx != null && target.idx !== fromIdx) reorder(fromIdx, target.idx);
      } else if (onMoveBetween) {
        onMoveBetween(src, fromIdx, target.cat, target.idx);
      }
    }
  };

  const onTouchCancel = () => onTouchEnd();

  const moveToOther = (idx, targetCatId) => {
    setMenuOpen(null);
    if (onMoveBetween) onMoveBetween(category, idx, targetCatId, null);
  };

  const meetsMin = images.length >= min;

  return (
    <div
      data-testid={testId}
      className={`rounded-card border bg-white p-4 transition ${dragOverGrid ? "border-[hsl(var(--accent))] ring-2 ring-[hsl(var(--accent))]/20" : "border-[hsl(var(--line))]"}`}
    >
      {label && (
        <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
          <div>
            <div className="text-sm font-semibold">{label}</div>
            {helper && <div className="text-xs text-[hsl(var(--ink-muted))] mt-0.5">{helper}</div>}
          </div>
          <div className={`flex items-center gap-1.5 text-xs font-mono ${meetsMin ? "text-[hsl(var(--accent))]" : "text-[hsl(var(--ink-muted))]"}`}>
            {meetsMin ? <Check size={12} /> : <AlertCircle size={12} />}
            {images.length}/{max} {min > 0 && <span>· мин. {min}</span>}
          </div>
        </div>
      )}

      <div
        className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5"
        data-uploader-grid="true"
        data-uploader-category={category}
        onDragOver={onGridDragOver}
        onDrop={onGridDrop}
        onDragLeave={() => setDragOverGrid(false)}
      >
        {images.map((src, i) => (
          <div
            key={i}
            draggable
            onDragStart={(e) => onDragStart(e, i)}
            onDragOver={(e) => onSlotDragOver(e, i)}
            onDragLeave={() => setDragOverIdx(null)}
            onDrop={(e) => onSlotDrop(e, i)}
            onTouchStart={(e) => onTouchStart(e, i, src)}
            onTouchMove={onTouchMove}
            onTouchEnd={onTouchEnd}
            onTouchCancel={onTouchCancel}
            data-uploader-slot="true"
            data-uploader-category={category}
            data-uploader-idx={i}
            className={`relative aspect-[4/3] rounded-md border overflow-hidden bg-[hsl(var(--surface))] cursor-move select-none transition ${dragOverIdx === i ? "border-[hsl(var(--accent))] ring-2 ring-[hsl(var(--accent))]/30" : "border-[hsl(var(--line))]"} data-[drag-target=true]:border-[hsl(var(--accent))] data-[drag-target=true]:ring-2 data-[drag-target=true]:ring-[hsl(var(--accent))]/40`}
            data-testid={`${testId}-slot-${i}`}
            style={{ touchAction: "pan-y" }}
          >
            <img src={src} alt="" className="w-full h-full object-cover pointer-events-none" draggable="false" />
            <div className="absolute top-1 left-1 bg-black/60 text-white rounded px-1.5 py-0.5 flex items-center gap-1 text-[10px] font-mono pointer-events-none">
              <GripVertical size={10} /> {i + 1}
            </div>
            <div className="absolute top-1 right-1 flex flex-col gap-1">
              <button
                type="button"
                onClick={() => remove(i)}
                className="bg-white/90 rounded-full p-1 border border-[hsl(var(--line))] hover:bg-[hsl(var(--danger))] hover:text-white transition"
                data-testid={`${testId}-remove-${i}`}
              ><X size={12} /></button>
              {availableCategories.length > 0 && (
                <button
                  type="button"
                  onClick={() => setMenuOpen(menuOpen === i ? null : i)}
                  className="bg-white/90 rounded-full p-1 border border-[hsl(var(--line))] hover:bg-[hsl(var(--ink))] hover:text-white transition"
                  data-testid={`${testId}-move-${i}`}
                  title="Премести в друга категория"
                ><ArrowRightLeft size={12} /></button>
              )}
            </div>
          </div>
        ))}
        {images.length < max && (
          <button
            type="button"
            onClick={() => ref.current?.click()}
            className="aspect-[4/3] rounded-md border-2 border-dashed border-[hsl(var(--line))] hover:border-[hsl(var(--ink))] transition flex flex-col items-center justify-center gap-1.5 text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]"
            data-testid={`${testId}-add`}
          >
            <Upload size={18} />
            <span className="text-[11px]">Добави</span>
          </button>
        )}
      </div>
      <input ref={ref} type="file" accept="image/*" multiple className="hidden" onChange={(e) => handleFiles(e.target.files)} data-testid={`${testId}-input`} />

      {menuOpen != null && (
        <>
          <div className="fixed inset-0 z-40 bg-black/40" onClick={() => setMenuOpen(null)} data-testid={`${testId}-menu-overlay`} />
          <div className="fixed left-0 right-0 bottom-0 sm:left-auto sm:right-6 sm:bottom-6 sm:w-72 z-50 bg-white rounded-t-xl sm:rounded-xl shadow-2xl border border-[hsl(var(--line))] overflow-hidden" data-testid={`${testId}-menu`}>
            <div className="px-5 py-3 border-b border-[hsl(var(--line))] bg-[hsl(var(--surface))]">
              <div className="text-xs text-[hsl(var(--ink-muted))]">Премести снимка #{menuOpen + 1} в:</div>
            </div>
            {availableCategories.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => moveToOther(menuOpen, c.id)}
                className="w-full text-left px-5 py-4 sm:py-3 text-sm hover:bg-[hsl(var(--surface))] border-b border-[hsl(var(--line))] last:border-b-0 flex items-center gap-2"
                data-testid={`${testId}-moveto-${c.id}-${menuOpen}`}
              >
                <ArrowRightLeft size={14} className="text-[hsl(var(--accent))]" /> {c.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setMenuOpen(null)}
              className="w-full text-center px-5 py-4 sm:py-3 text-sm text-[hsl(var(--ink-muted))] bg-[hsl(var(--surface))]"
              data-testid={`${testId}-menu-cancel`}
            >Отказ</button>
          </div>
        </>
      )}

      {images.length > 0 && (
        <p className="mt-2 text-[10px] text-[hsl(var(--ink-muted))] flex items-center gap-1">
          <Move size={9} /> Натиснете и задръжте, за да преместите снимка
        </p>
      )}
      {touchDragging && <p className="sr-only" data-testid={`${testId}-touch-dragging`}>dragging</p>}
    </div>
  );
}
