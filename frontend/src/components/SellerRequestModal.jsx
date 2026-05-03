import React, { useEffect, useRef, useState } from "react";
import { X, FileEdit, Images, ArrowUp, ArrowDown, Trash2, GripVertical } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { useTranslation } from "react-i18next";

const LONG_PRESS_MS = 220;

/**
 * Seller self-service requests for a single auction.
 * Modes: "promote" | "text" | "reorder"
 *
 * Props:
 *  - auction: the auction dict (needs id, title, description, images)
 *  - mode: one of "promote" | "text" | "reorder"
 *  - onClose()
 *  - onDone()   — called after successful submission (parent refreshes list)
 */
export default function SellerRequestModal({ auction, mode, onClose, onDone }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // Text change state
  const [newTitle, setNewTitle] = useState(auction?.title || "");
  const [newDesc, setNewDesc] = useState(auction?.description || "");
  const [note, setNote] = useState("");

  // Reorder state
  const [images, setImages] = useState(() => Array.from(auction?.images || []));
  const dragItem = useRef(null);
  const touchState = useRef({ active: false, startX: 0, startY: 0, fromIdx: null, ghost: null, longPressTimer: null, lastTargetIdx: null });

  // Modal close on Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async () => {
    setErr(""); setBusy(true);
    try {
      if (mode === "text") {
        if (!newTitle && !newDesc) {
          setErr(t("forms.required"));
          setBusy(false);
          return;
        }
        const payload = { note: note || null };
        if (newTitle && newTitle !== auction.title) payload.title = newTitle;
        if (newDesc && newDesc !== auction.description) payload.description = newDesc;
        if (!payload.title && !payload.description) {
          setErr("Няма промяна спрямо текущия текст.");
          setBusy(false);
          return;
        }
        await api.post(`/auctions/${auction.id}/request-text-change`, payload);
      } else if (mode === "reorder") {
        await api.patch(`/auctions/${auction.id}/reorder-images`, { images });
      }
      onDone?.();
      onClose();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(false); }
  };

  // Drag handlers for photos
  const onDragStart = (i) => { dragItem.current = i; };
  const onDragOver = (e, i) => {
    e.preventDefault();
    if (dragItem.current === null || dragItem.current === i) return;
    setImages((list) => {
      const next = [...list];
      const [moved] = next.splice(dragItem.current, 1);
      next.splice(i, 0, moved);
      dragItem.current = i;
      return next;
    });
  };
  const onDragEnd = () => { dragItem.current = null; };

  // Touch (mobile) drag — long-press creates a floating ghost that follows the finger.
  const clearGhost = () => {
    if (touchState.current.ghost) {
      touchState.current.ghost.remove();
      touchState.current.ghost = null;
    }
  };
  const clearTargetHighlight = () => {
    document.querySelectorAll('[data-reorder-drop-target="true"]').forEach((el) => el.removeAttribute("data-reorder-drop-target"));
  };
  useEffect(() => () => { clearGhost(); clearTargetHighlight(); }, []);

  const onTouchStart = (e, idx, src) => {
    if (e.touches.length !== 1) return;
    const tch = e.touches[0];
    touchState.current.startX = tch.clientX;
    touchState.current.startY = tch.clientY;
    touchState.current.fromIdx = idx;
    touchState.current.active = false;
    if (touchState.current.longPressTimer) clearTimeout(touchState.current.longPressTimer);
    touchState.current.longPressTimer = setTimeout(() => {
      touchState.current.active = true;
      try { if (navigator.vibrate) navigator.vibrate(12); } catch {}
      const ghost = document.createElement("div");
      ghost.style.cssText = `position:fixed;left:0;top:0;width:120px;height:90px;background-image:url("${src.replace(/"/g, '\\"')}");background-size:cover;background-position:center;border-radius:8px;box-shadow:0 12px 32px rgba(0,0,0,.35);pointer-events:none;z-index:9999;transform:translate(${tch.clientX - 60}px, ${tch.clientY - 45}px) scale(1.05);border:2px solid hsl(158 60% 30%);`;
      document.body.appendChild(ghost);
      touchState.current.ghost = ghost;
      document.body.style.overflow = "hidden";
    }, LONG_PRESS_MS);
  };
  const onTouchMove = (e) => {
    if (!touchState.current.longPressTimer && !touchState.current.active) return;
    const tch = e.touches[0];
    const dx = tch.clientX - touchState.current.startX;
    const dy = tch.clientY - touchState.current.startY;
    if (!touchState.current.active) {
      if (Math.abs(dx) > 8 || Math.abs(dy) > 8) {
        clearTimeout(touchState.current.longPressTimer);
        touchState.current.longPressTimer = null;
      }
      return;
    }
    e.preventDefault();
    if (touchState.current.ghost) {
      touchState.current.ghost.style.transform = `translate(${tch.clientX - 60}px, ${tch.clientY - 45}px) scale(1.05)`;
    }
    const el = document.elementFromPoint(tch.clientX, tch.clientY);
    clearTargetHighlight();
    touchState.current.lastTargetIdx = null;
    if (el) {
      const slot = el.closest("[data-reorder-slot]");
      if (slot) {
        slot.setAttribute("data-reorder-drop-target", "true");
        touchState.current.lastTargetIdx = parseInt(slot.getAttribute("data-reorder-idx"), 10);
      }
    }
    const margin = 60;
    if (tch.clientY < margin) window.scrollBy(0, -8);
    else if (tch.clientY > window.innerHeight - margin) window.scrollBy(0, 8);
  };
  const onTouchEnd = () => {
    if (touchState.current.longPressTimer) clearTimeout(touchState.current.longPressTimer);
    touchState.current.longPressTimer = null;
    const wasActive = touchState.current.active;
    const fromIdx = touchState.current.fromIdx;
    const targetIdx = touchState.current.lastTargetIdx;
    clearGhost();
    clearTargetHighlight();
    document.body.style.overflow = "";
    touchState.current.active = false;
    if (wasActive && fromIdx != null && targetIdx != null && targetIdx !== fromIdx) {
      setImages((list) => {
        const n = [...list];
        const [moved] = n.splice(fromIdx, 1);
        n.splice(targetIdx, 0, moved);
        return n;
      });
    }
  };

  const moveUp = (i) => {
    if (i <= 0) return;
    setImages((list) => { const n = [...list]; [n[i-1], n[i]] = [n[i], n[i-1]]; return n; });
  };
  const moveDown = (i) => {
    if (i >= images.length - 1) return;
    setImages((list) => { const n = [...list]; [n[i+1], n[i]] = [n[i], n[i+1]]; return n; });
  };

  const titleMap = {
    text: { icon: FileEdit, title: t("seller.request_text_change") },
    reorder: { icon: Images, title: t("seller.reorder_photos") },
  };
  const Meta = titleMap[mode] || titleMap.text;
  const Icon = Meta.icon;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose} data-testid="seller-request-modal">
      <div className="bg-white rounded-card max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-5 rule-b">
          <div className="flex items-center gap-2">
            <Icon size={18} className="text-[hsl(var(--accent))]" />
            <h2 className="font-serif text-xl">{Meta.title}</h2>
          </div>
          <button onClick={onClose} className="text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]" data-testid="seller-request-close">
            <X size={20} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div className="text-xs text-[hsl(var(--ink-muted))]">
            <span className="overline">Обява</span>
            <div className="text-sm text-[hsl(var(--ink))] mt-0.5">{auction.title}</div>
          </div>

          {/* Promotion is now self-serve via Stripe Checkout — no modal mode. */}

          {mode === "text" && (
            <>
              <p className="text-sm text-[hsl(var(--ink-muted))]">{t("seller.text_change_description")}</p>
              <div>
                <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">{t("seller.new_title")}</label>
                <input
                  type="text"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  maxLength={200}
                  className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm"
                  data-testid="text-change-title-input"
                />
              </div>
              <div>
                <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">{t("seller.new_description")}</label>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  rows={8}
                  maxLength={8000}
                  className="w-full border border-[hsl(var(--line))] p-3 text-sm"
                  data-testid="text-change-desc-input"
                />
              </div>
              <div>
                <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">{t("seller.note_for_mod")}</label>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                  maxLength={600}
                  className="w-full border border-[hsl(var(--line))] p-3 text-sm"
                  data-testid="text-change-note-input"
                />
              </div>
            </>
          )}

          {mode === "reorder" && (
            <>
              <p className="text-sm text-[hsl(var(--ink-muted))]">{t("seller.reorder_description")}</p>
              {images.length === 0 ? (
                <div className="text-sm text-[hsl(var(--ink-muted))]">Няма снимки.</div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3" data-testid="reorder-grid">
                  {images.map((src, i) => (
                    <div
                      key={`${src}-${i}`}
                      draggable
                      onDragStart={() => onDragStart(i)}
                      onDragOver={(e) => onDragOver(e, i)}
                      onDragEnd={onDragEnd}
                      onTouchStart={(e) => onTouchStart(e, i, src)}
                      onTouchMove={onTouchMove}
                      onTouchEnd={onTouchEnd}
                      onTouchCancel={onTouchEnd}
                      data-reorder-slot="true"
                      data-reorder-idx={i}
                      className="relative rounded-card border border-[hsl(var(--line))] overflow-hidden bg-[hsl(var(--surface))] cursor-move group select-none transition data-[reorder-drop-target=true]:border-[hsl(var(--accent))] data-[reorder-drop-target=true]:ring-2 data-[reorder-drop-target=true]:ring-[hsl(var(--accent))]/40"
                      data-testid={`reorder-item-${i}`}
                      style={{ touchAction: "pan-y" }}
                    >
                      <div className="aspect-[4/3]">
                        <img src={src} alt={`#${i+1}`} className="w-full h-full object-cover pointer-events-none" draggable="false" />
                      </div>
                      <div className="absolute top-1 left-1 bg-black/70 text-white text-xs font-mono px-1.5 py-0.5 rounded flex items-center gap-1 pointer-events-none">
                        <GripVertical size={10} /> #{i + 1}{i === 0 ? " • корица" : ""}
                      </div>
                      <div className="absolute bottom-1 right-1 flex gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                        <button
                          type="button"
                          onClick={() => moveUp(i)}
                          className="p-1 bg-black/70 text-white rounded hover:bg-black"
                          data-testid={`reorder-up-${i}`}
                          title="Нагоре"
                        >
                          <ArrowUp size={12} />
                        </button>
                        <button
                          type="button"
                          onClick={() => moveDown(i)}
                          className="p-1 bg-black/70 text-white rounded hover:bg-black"
                          data-testid={`reorder-down-${i}`}
                          title="Надолу"
                        >
                          <ArrowDown size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {images.length > 0 && (
                <p className="text-[11px] text-[hsl(var(--ink-muted))] mt-2">
                  Плъзнете снимките с мишка (десктоп) или натиснете и задръжте, за да ги преместите (мобилни). Първата снимка е корица.
                </p>
              )}
            </>
          )}

          {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="seller-request-error">{err}</p>}
        </div>

        <div className="flex justify-end gap-2 p-5 rule-t">
          <button onClick={onClose} className="btn btn-secondary !py-2 !px-5" data-testid="seller-request-cancel">
            {t("forms.cancel")}
          </button>
          <button
            onClick={submit}
            disabled={busy}
            className="btn btn-accent !py-2 !px-5"
            data-testid="seller-request-submit"
          >
            {busy ? t("forms.sending") : (mode === "reorder" ? t("seller.save_order") : t("forms.submit"))}
          </button>
        </div>
      </div>
    </div>
  );
}
