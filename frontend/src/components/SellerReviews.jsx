import React, { useEffect, useMemo, useState } from "react";
import { Star, MessageSquare, Check } from "lucide-react";
import { api } from "../lib/apiClient";
import { useAuth } from "../lib/auth";

/**
 * Stars (read-only) — renders 5 stars filling up to `value` (float, 0-5).
 */
export function StarRating({ value = 0, size = 16, className = "" }) {
  const v = Math.max(0, Math.min(5, Number(value) || 0));
  return (
    <div className={`inline-flex items-center gap-0.5 ${className}`} data-testid="star-rating">
      {[1, 2, 3, 4, 5].map((i) => {
        const fill = Math.max(0, Math.min(1, v - (i - 1)));
        return (
          <span key={i} className="relative inline-block" style={{ width: size, height: size }}>
            <Star size={size} className="text-[hsl(var(--line))]" strokeWidth={1.5} fill="currentColor" />
            {fill > 0 && (
              <span className="absolute inset-0 overflow-hidden" style={{ width: `${fill * 100}%` }}>
                <Star size={size} className="text-amber-500" strokeWidth={1.5} fill="currentColor" />
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}

/**
 * Interactive stars for the compose form.
 */
function StarInput({ value, onChange, size = 28 }) {
  const [hover, setHover] = useState(0);
  return (
    <div className="inline-flex items-center gap-1" data-testid="star-input">
      {[1, 2, 3, 4, 5].map((i) => (
        <button
          type="button"
          key={i}
          onMouseEnter={() => setHover(i)}
          onMouseLeave={() => setHover(0)}
          onClick={() => onChange(i)}
          className="p-0.5 transition-transform hover:scale-110"
          data-testid={`star-input-${i}`}
          aria-label={`${i} от 5`}
        >
          <Star
            size={size}
            strokeWidth={1.5}
            className={(hover || value) >= i ? "text-amber-500" : "text-[hsl(var(--line))]"}
            fill="currentColor"
          />
        </button>
      ))}
    </div>
  );
}

function ReviewForm({ sellerId, reviewable, onSubmitted }) {
  const [selected, setSelected] = useState(reviewable[0]?.auction_id || "");
  const [rating, setRating] = useState(5);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (!selected) { setErr("Изберете сделка."); return; }
    if (text.trim().length < 10) { setErr("Моля, напишете поне 10 символа."); return; }
    setSubmitting(true); setErr("");
    try {
      await api.post(`/users/${sellerId}/reviews`, {
        auction_id: selected, rating, text: text.trim(),
      });
      setText(""); setRating(5);
      onSubmitted?.();
    } catch (ex) {
      setErr(ex?.response?.data?.detail || "Грешка при изпращане.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-card border border-[hsl(var(--line))] bg-white p-6 mb-8"
      data-testid="review-form"
    >
      <div className="overline text-[hsl(var(--accent))] mb-2">Оставете отзив</div>
      <h3 className="font-serif text-2xl mb-5">Как беше сделката?</h3>

      {reviewable.length > 1 && (
        <label className="block mb-4">
          <span className="text-xs text-[hsl(var(--ink-muted))] uppercase tracking-wider">Сделка</span>
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="mt-1 w-full border border-[hsl(var(--line))] rounded-card px-3 py-2.5 bg-white"
            data-testid="review-auction-select"
          >
            {reviewable.map((r) => (
              <option key={r.auction_id} value={r.auction_id}>
                {r.auction_title}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="mb-4">
        <div className="text-xs text-[hsl(var(--ink-muted))] uppercase tracking-wider mb-2">Оценка</div>
        <StarInput value={rating} onChange={setRating} />
      </div>

      <label className="block mb-4">
        <span className="text-xs text-[hsl(var(--ink-muted))] uppercase tracking-wider">Коментар</span>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          maxLength={1200}
          placeholder="Как беше комуникацията, състоянието на автомобила, предаването?"
          className="mt-1 w-full border border-[hsl(var(--line))] rounded-card px-3 py-2.5 resize-y"
          data-testid="review-text"
        />
        <span className="block text-xs text-[hsl(var(--ink-muted))] mt-1">{text.length}/1200</span>
      </label>

      {err && <div className="text-sm text-[hsl(var(--danger))] mb-3" data-testid="review-error">{err}</div>}

      <button
        type="submit"
        disabled={submitting}
        className="inline-flex items-center gap-2 bg-[hsl(var(--ink))] text-white px-5 py-2.5 rounded-card text-sm font-medium hover:bg-[hsl(var(--accent))] transition-colors disabled:opacity-50"
        data-testid="review-submit"
      >
        <Check size={15} />
        {submitting ? "Изпращане…" : "Публикувай отзив"}
      </button>
    </form>
  );
}

export default function SellerReviews({ sellerId, rating }) {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [reviewable, setReviewable] = useState([]);
  const [loading, setLoading] = useState(true);

  const reload = async () => {
    setLoading(true);
    try {
      const [reviewsRes, reviewableRes] = await Promise.all([
        api.get(`/users/${sellerId}/reviews`),
        user && user.id !== sellerId ? api.get(`/me/reviewable`).catch(() => ({ data: { items: [] } })) : Promise.resolve({ data: { items: [] } }),
      ]);
      setItems(reviewsRes.data?.items || []);
      // Filter reviewable list to only this seller
      const filtered = (reviewableRes.data?.items || []).filter((r) => r.seller_id === sellerId);
      setReviewable(filtered);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [sellerId, user?.id]);

  const showForm = user && user.id !== sellerId && reviewable.length > 0;

  const avg = rating?.avg ?? 0;
  const count = rating?.count ?? 0;

  const dist = useMemo(() => {
    const d = { 5: 0, 4: 0, 3: 0, 2: 0, 1: 0 };
    items.forEach((r) => { d[r.rating] = (d[r.rating] || 0) + 1; });
    return d;
  }, [items]);

  return (
    <div data-testid="seller-reviews">
      {/* Header summary */}
      <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6 mb-8 flex items-start gap-8 flex-wrap">
        <div className="min-w-[180px]">
          <div className="font-serif text-5xl leading-none">{avg.toFixed(1)}</div>
          <div className="mt-2"><StarRating value={avg} size={18} /></div>
          <div className="mt-2 text-sm text-[hsl(var(--ink-muted))]" data-testid="review-count">
            {count === 0 ? "Все още няма отзиви" : `${count} ${count === 1 ? "отзив" : "отзива"}`}
          </div>
        </div>
        <div className="flex-1 min-w-[260px]">
          {[5, 4, 3, 2, 1].map((n) => {
            const c = dist[n] || 0;
            const pct = count ? (c / count) * 100 : 0;
            return (
              <div key={n} className="flex items-center gap-3 mb-1.5">
                <span className="text-xs text-[hsl(var(--ink-muted))] w-3">{n}</span>
                <Star size={12} className="text-amber-500" fill="currentColor" strokeWidth={1.5} />
                <div className="flex-1 h-1.5 rounded-full bg-[hsl(var(--line))] overflow-hidden">
                  <div className="h-full bg-amber-500" style={{ width: `${pct}%` }} />
                </div>
                <span className="text-xs text-[hsl(var(--ink-muted))] w-8 text-right">{c}</span>
              </div>
            );
          })}
        </div>
      </div>

      {showForm && (
        <ReviewForm sellerId={sellerId} reviewable={reviewable} onSubmitted={reload} />
      )}

      {/* List */}
      {loading ? (
        <div className="py-16 text-center text-sm text-[hsl(var(--ink-muted))]">Зареждане…</div>
      ) : items.length === 0 ? (
        <div className="py-16 text-center rounded-card border border-[hsl(var(--line))]" data-testid="reviews-empty">
          <MessageSquare size={28} className="mx-auto text-[hsl(var(--ink-muted))]" />
          <p className="font-serif text-xl mt-3">Все още няма оставени отзиви</p>
          <p className="mt-1 text-sm text-[hsl(var(--ink-muted))]">Купувачите могат да оценят продавача след приключила сделка.</p>
        </div>
      ) : (
        <ul className="space-y-4" data-testid="reviews-list">
          {items.map((r) => (
            <li key={r.id} className="rounded-card border border-[hsl(var(--line))] bg-white p-5" data-testid={`review-item-${r.id}`}>
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <div className="font-serif text-lg">{r.buyer_name}</div>
                  <div className="text-xs text-[hsl(var(--ink-muted))] mt-0.5">
                    за „{r.auction_title}" • {new Date(r.created_at).toLocaleDateString("bg-BG", { day: "numeric", month: "short", year: "numeric" })}
                  </div>
                </div>
                <StarRating value={r.rating} size={15} />
              </div>
              <p className="mt-3 text-sm text-[hsl(var(--ink))] whitespace-pre-line">{r.text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
