import React, { useRef, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Upload, X, Image as ImageIcon, AlertCircle, Check, Move, GripVertical, ArrowRightLeft } from "lucide-react";
import { toast } from "sonner";

// Per-image hard cap (raw bytes the user picks from disk). Mirrors the
// backend `IMAGE_MAX_RAW_BYTES` so feedback is immediate and consistent.
const MAX_IMG_BYTES = 10 * 1024 * 1024;        // 10 MB per file
const MAX_LISTING_BYTES = 120 * 1024 * 1024;   // 120 MB total per listing
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
  // Optional callback used by parent (e.g. SellPage) to report cumulative
  // bytes across ALL uploaders for a single listing — needed to enforce the
  // 120 MB total-listing budget across categorised buckets.
  totalBudgetBytes = MAX_LISTING_BYTES,
  currentTotalBytes = 0,
}) {
  const { t } = useTranslation();
  const ref = useRef(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const [dragOverGrid, setDragOverGrid] = useState(false);
  const [menuOpen, setMenuOpen] = useState(null);
  const [touchDragging, setTouchDragging] = useState(false);

  // Cleanup on unmount
  useEffect(() => () => { clearGhost(); clearTargetHighlight(); }, []);

  // Re-encode the image client-side so we don't ship multi-MB camera
  // originals over the wire. The server still re-optimizes everything for
  // a single source of truth, but trimming here cuts upload time on slow
  // connections (notably mobile uploads).
  //
  // We aim for ≤ 600 KB per photo at JPEG q=0.82, max 1600 px on the
  // long edge — this is plenty for a 4:3 gallery card up to 2× retina,
  // and lets users submit 24 photos in well under 20 MB total.
  // If the encoded result is still > 1.5 MB (e.g. very high-detail
  // shot), we recompress at q=0.7 and 1280 px as a safety net.
  const TARGET_BYTES = 1.5 * 1024 * 1024; // 1.5 MB upper bound per photo

  // Feature-detect canvas AVIF encoding (Chrome 105+, Edge, Brave, modern
  // Android). Safari and Firefox still return null/throw — they fall
  // back to JPEG. AVIF cuts payloads ~40% vs JPEG at equivalent
  // perceptual quality, so a typical 25-photo sell submission goes
  // from ~37 MB → ~22 MB on supported browsers without any quality
  // loss visible to humans.
  const _supportsAvifEncode = (() => {
    try {
      const c = document.createElement("canvas");
      c.width = c.height = 4;
      const d = c.toDataURL("image/avif");
      return typeof d === "string" && d.startsWith("data:image/avif");
    } catch {
      return false;
    }
  })();

  const encodeAtQuality = (img, longEdge, quality) => {
    const canvas = document.createElement("canvas");
    let w = img.width, h = img.height;
    if (w > longEdge || h > longEdge) {
      if (w > h) { h = Math.round((h / w) * longEdge); w = longEdge; }
      else { w = Math.round((w / h) * longEdge); h = longEdge; }
    }
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext("2d");
    // White background so transparent PNGs don't show black after JPEG/AVIF
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(img, 0, 0, w, h);
    // AVIF when the browser supports encoding it natively — quality
    // 0.55 ≈ JPEG 0.82 perceptually but ~40% smaller. Fall back to
    // JPEG when the encode unexpectedly fails (returns a tiny stub).
    if (_supportsAvifEncode) {
      const avifQ = Math.max(0.4, Math.min(0.7, quality - 0.25));
      try {
        const avif = canvas.toDataURL("image/avif", avifQ);
        if (avif && avif.startsWith("data:image/avif") && avif.length > 1024) {
          return avif;
        }
      } catch {
        /* fall through to JPEG */
      }
    }
    return canvas.toDataURL("image/jpeg", quality);
  };

  const dataUrlBytes = (url) => {
    if (!url || typeof url !== "string") return 0;
    const i = url.indexOf(",");
    if (i < 0) return 0;
    return Math.floor((url.length - i - 1) * 0.75);
  };

  const compress = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          let dataUrl = encodeAtQuality(img, 1600, 0.82);
          // Hot pictures (lots of foliage / texture) can still come out
          // > 1.5 MB after the first pass — recompress more aggressively.
          if (dataUrlBytes(dataUrl) > TARGET_BYTES) {
            dataUrl = encodeAtQuality(img, 1280, 0.7);
          }
          resolve(dataUrl);
        };
        img.onerror = () =>
          reject(new Error("decode-failed"));
        img.src = e.target.result;
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  // Detect HEIC/HEIF — iPhones save in this format by default and only
  // Safari can decode it natively. Identification is via either the
  // file's MIME (most browsers fill it correctly when picking via the
  // OS file dialog) or the `.heic`/`.heif` extension as a fallback.
  const isHeicFile = (file) => {
    const t = (file.type || "").toLowerCase();
    if (t.includes("heic") || t.includes("heif")) return true;
    const n = (file.name || "").toLowerCase();
    return /\.heic$|\.heif$/.test(n);
  };

  // Convert HEIC → JPEG Blob using the libheif WASM bundle. The library
  // (~1 MB) is lazily imported so it only ships to users who actually
  // need it — desktop Chrome / Firefox visitors never download it.
  const convertHeicToJpegFile = async (file) => {
    const { default: heic2any } = await import("heic2any");
    const out = await heic2any({ blob: file, toType: "image/jpeg", quality: 0.9 });
    // heic2any returns a Blob (single image) or Blob[] (multi-frame).
    const blob = Array.isArray(out) ? out[0] : out;
    // Re-wrap as a File so downstream filename/size logging stays sane.
    const newName = (file.name || "image").replace(/\.(heic|heif)$/i, ".jpg");
    return new File([blob], newName, { type: "image/jpeg" });
  };

  const handleFiles = async (files) => {
    const fmt = (n) => `${(n / 1024 / 1024).toFixed(1)} MB`;
    const arr = Array.from(files);
    const slotsLeft = Math.max(0, max - images.length);
    if (arr.length > slotsLeft) {
      toast.warning(t("uploader.too_many", { max }));
    }
    const accepted = [];
    let runningTotal = currentTotalBytes;

    for (const f of arr.slice(0, slotsLeft)) {
      // 1) raw per-file size (fast path before any decoding)
      if (f.size > MAX_IMG_BYTES) {
        toast.error(t("uploader.image_too_large", { name: f.name, size: fmt(f.size), max: "10 MB" }));
        continue;
      }
      // 2) Heuristic budget check — would adding this file blow the listing cap?
      //    We use the raw file size as the upper bound (compression usually
      //    halves it, so this is intentionally conservative).
      if (runningTotal + f.size > totalBudgetBytes) {
        toast.error(t("uploader.total_too_large", {
          current: fmt(runningTotal),
          incoming: fmt(f.size),
          max: "120 MB",
        }));
        break;
      }
      try {
        // HEIC files (iPhone default) cannot be decoded by canvas in
        // Chrome/Firefox. Convert to JPEG first via lazy-loaded WASM
        // before running the standard compression pipeline. Conversion
        // is slow (~1-3s per photo), so we surface a toast for context.
        let inputFile = f;
        if (isHeicFile(f)) {
          const tid = toast.loading(
            t("uploader.heic_converting", "Конвертирам {{name}} от HEIC към JPEG…", { name: f.name })
          );
          try {
            inputFile = await convertHeicToJpegFile(f);
          } finally {
            toast.dismiss(tid);
          }
        }
        const dataUrl = await compress(inputFile);
        const compressedBytes = dataUrlBytes(dataUrl);
        // Recheck against the cap with the actual encoded size.
        if (runningTotal + compressedBytes > totalBudgetBytes) {
          toast.error(t("uploader.total_too_large", {
            current: fmt(runningTotal),
            incoming: fmt(compressedBytes),
            max: "120 MB",
          }));
          break;
        }
        runningTotal += compressedBytes;
        accepted.push(dataUrl);
      } catch (e) {
        // HEIC conversion or canvas decode failed. The HEIC branch above
        // already wraps its own try/finally so a thrown error here for a
        // .heic input means libheif could not parse the file — likely a
        // 16-bit / multi-track variant. Fall back to a clear hint.
        const isHeic = isHeicFile(f);
        toast.error(
          isHeic
            ? t(
                "uploader.heic_unsupported",
                "{{name}} е HEIC формат, който браузърът ви не може да обработи. На iPhone превключете Settings → Camera → Formats → Most Compatible или конвертирайте към JPG.",
                { name: f.name }
              )
            : t("uploader.decode_failed", { name: f.name })
        );
      }
    }
    if (accepted.length) onChange([...images, ...accepted]);
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
    // Scroll-lock the page during desktop drag to avoid the surrounding
    // form scrolling under the cursor when the browser's edge-scroll
    // engages — that fights the user's reorder intent and feels janky.
    // Restored unconditionally on dragend (fires for both drop & cancel).
    document.body.style.overflow = "hidden";
  };
  const onDragEndAny = () => {
    document.body.style.overflow = "";
    setDragOverIdx(null);
    setDragOverGrid(false);
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
            {images.length}/{max} {min > 0 && <span>· {t("common.min_short")} {min}</span>}
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
            onDragEnd={onDragEndAny}
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
            <span className="text-[11px]">{t("forms.add", "Добави")}</span>
          </button>
        )}
      </div>
      <input ref={ref} type="file" accept="image/*,.heic,.heif" multiple className="hidden" onChange={(e) => handleFiles(e.target.files)} data-testid={`${testId}-input`} />

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
