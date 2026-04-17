import React, { useRef, useState } from "react";
import { Upload, X, Image as ImageIcon, AlertCircle, Check, Move, GripVertical, ArrowRightLeft } from "lucide-react";

const MAX_SIZE = 2 * 1024 * 1024; // 2MB per image

export default function ImageUploader({
  images = [],
  onChange,
  max = 8,
  min = 0,
  label,
  helper,
  testId = "image-uploader",
  category,           // unique ID of this category (used for drag-drop)
  onMoveBetween,      // (fromCategory, fromIdx, toCategory) => void
  availableCategories = [], // [{ id, label }] for "Move to" dropdown
}) {
  const ref = useRef(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const [dragOverGrid, setDragOverGrid] = useState(false);
  const [menuOpen, setMenuOpen] = useState(null); // idx of image with open menu

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
      try {
        const dataUrl = await compress(f);
        compressed.push(dataUrl);
      } catch (e) { /* skip */ }
    }
    onChange([...images, ...compressed]);
  };

  const remove = (idx) => onChange(images.filter((_, i) => i !== idx));

  const reorder = (fromIdx, toIdx) => {
    if (fromIdx === toIdx) return;
    const next = [...images];
    const [item] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, item);
    onChange(next);
  };

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
    setDragOverIdx(null);
    setDragOverGrid(false);
    const d = parseDrag(e);
    if (!d) return;
    if (d.category === category) {
      reorder(d.idx, toIdx);
    } else if (onMoveBetween) {
      // Cross-category drop: move to this category at toIdx
      onMoveBetween(d.category, d.idx, category, toIdx);
    }
  };

  const onGridDragOver = (e) => {
    // Dragging over empty area
    const d = e.dataTransfer.types.includes("application/x-image-move") || e.dataTransfer.types.includes("text/plain");
    if (d) {
      e.preventDefault();
      setDragOverGrid(true);
    }
  };

  const onGridDrop = (e) => {
    e.preventDefault();
    setDragOverGrid(false);
    const d = parseDrag(e);
    if (!d) return;
    if (d.category !== category && onMoveBetween) {
      onMoveBetween(d.category, d.idx, category, null);
    }
  };

  const moveToOther = (idx, targetCatId) => {
    setMenuOpen(null);
    if (onMoveBetween) onMoveBetween(category, idx, targetCatId, null);
  };

  const meetsMin = images.length >= min;

  return (
    <div data-testid={testId} className={`rounded-card border bg-white p-4 transition ${dragOverGrid ? "border-[hsl(var(--accent))] ring-2 ring-[hsl(var(--accent))]/20" : "border-[hsl(var(--line))]"}`}>
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
            className={`relative aspect-[4/3] rounded-md border overflow-hidden bg-[hsl(var(--surface))] cursor-move transition ${dragOverIdx === i ? "border-[hsl(var(--accent))] ring-2 ring-[hsl(var(--accent))]/30" : "border-[hsl(var(--line))]"}`}
            data-testid={`${testId}-slot-${i}`}
          >
            <img src={src} alt="" className="w-full h-full object-cover pointer-events-none" />
            <div className="absolute top-1 left-1 bg-black/60 text-white rounded px-1.5 py-0.5 flex items-center gap-1 text-[10px] font-mono">
              <GripVertical size={10} /> {i + 1}
            </div>
            <div className="absolute top-1 right-1 flex flex-col gap-1">
              <button
                type="button"
                onClick={() => remove(i)}
                className="bg-white/90 rounded-full p-1 border border-[hsl(var(--line))] hover:bg-[hsl(var(--danger))] hover:text-white transition"
                data-testid={`${testId}-remove-${i}`}
                title="Премахни"
              ><X size={12} /></button>
              {availableCategories.length > 0 && (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setMenuOpen(menuOpen === i ? null : i)}
                    className="bg-white/90 rounded-full p-1 border border-[hsl(var(--line))] hover:bg-[hsl(var(--ink))] hover:text-white transition"
                    data-testid={`${testId}-move-${i}`}
                    title="Премести в друга категория"
                  ><ArrowRightLeft size={12} /></button>
                </div>
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
      {!label && (
        <p className="mt-2 text-xs text-[hsl(var(--ink-muted))] flex items-center gap-1.5">
          <ImageIcon size={11} /> JPEG/PNG · автоматично се оптимизират до 1600px
        </p>
      )}
      {images.length > 0 && (
        <p className="mt-2 text-[10px] text-[hsl(var(--ink-muted))] flex items-center gap-1">
          <Move size={9} /> Влачете снимка за промяна на реда или към друга категория
        </p>
      )}
    </div>
  );
}
