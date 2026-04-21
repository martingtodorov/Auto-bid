import React, { useEffect, useRef, useState } from "react";
import { X, Star, FileEdit, Images, ArrowUp, ArrowDown, Trash2 } from "lucide-react";
import { api } from "../lib/apiClient";
import { formatError } from "../lib/auth";
import { useTranslation } from "react-i18next";

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

  // Promote state
  const [promoteNote, setPromoteNote] = useState("");

  // Text change state
  const [newTitle, setNewTitle] = useState(auction?.title || "");
  const [newDesc, setNewDesc] = useState(auction?.description || "");
  const [note, setNote] = useState("");

  // Reorder state
  const [images, setImages] = useState(() => Array.from(auction?.images || []));
  const dragItem = useRef(null);

  // Modal close on Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async () => {
    setErr(""); setBusy(true);
    try {
      if (mode === "promote") {
        await api.post(`/auctions/${auction.id}/request-promotion`, { note: promoteNote || null });
      } else if (mode === "text") {
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

  const moveUp = (i) => {
    if (i <= 0) return;
    setImages((list) => { const n = [...list]; [n[i-1], n[i]] = [n[i], n[i-1]]; return n; });
  };
  const moveDown = (i) => {
    if (i >= images.length - 1) return;
    setImages((list) => { const n = [...list]; [n[i+1], n[i]] = [n[i], n[i+1]]; return n; });
  };

  const titleMap = {
    promote: { icon: Star, title: t("seller.promote_request") },
    text: { icon: FileEdit, title: t("seller.request_text_change") },
    reorder: { icon: Images, title: t("seller.reorder_photos") },
  };
  const Meta = titleMap[mode] || titleMap.promote;
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

          {mode === "promote" && (
            <>
              <p className="text-sm text-[hsl(var(--ink-muted))]" data-testid="promote-description">{t("seller.promote_description")}</p>
              <div>
                <label className="overline text-[hsl(var(--ink-muted))] block mb-1.5">{t("seller.note_for_mod")}</label>
                <textarea
                  value={promoteNote}
                  onChange={(e) => setPromoteNote(e.target.value)}
                  rows={4}
                  maxLength={600}
                  className="w-full border border-[hsl(var(--line))] p-3 text-sm"
                  data-testid="promote-note-input"
                />
              </div>
            </>
          )}

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
                      className="relative rounded-card border border-[hsl(var(--line))] overflow-hidden bg-[hsl(var(--surface))] cursor-move group"
                      data-testid={`reorder-item-${i}`}
                    >
                      <div className="aspect-[4/3]">
                        <img src={src} alt={`#${i+1}`} className="w-full h-full object-cover pointer-events-none" />
                      </div>
                      <div className="absolute top-1 left-1 bg-black/70 text-white text-xs font-mono px-1.5 py-0.5 rounded">
                        #{i + 1}{i === 0 ? " • корица" : ""}
                      </div>
                      <div className="absolute bottom-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
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
