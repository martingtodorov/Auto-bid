import React, { useEffect, useRef, useState } from "react";
import { Clock, Send, CheckCircle2, XCircle } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { useAuth, formatError } from "../lib/auth";

const STATUS_LABEL = {
  awaiting_seller_opening: "Изчаква оферта от продавача",
  awaiting_buyer_response: "Изчаква отговор от купувача",
  awaiting_seller_final: "Изчаква финално решение от продавача",
  accepted: "Сделката е сключена",
  declined: "Преговорите са прекратени",
  expired: "Срокът изтече",
};

function fmtCountdown(seconds) {
  if (!seconds || seconds <= 0) return "изтекъл";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}ч ${m}мин`;
}

export default function NegotiationPortal({ auctionId, auction }) {
  const { user } = useAuth();
  const [neg, setNeg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [priceInput, setPriceInput] = useState("");
  const [msgInput, setMsgInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const scrollerRef = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/auctions/${auctionId}/negotiation`);
      setNeg(data);
    } catch (e) {
      // 404 => not applicable / not a party
      setNeg(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [auctionId]);

  useEffect(() => {
    if (!neg) return;
    // Soft refresh every 30s to update deadlines
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [neg?.id]);

  useEffect(() => {
    if (scrollerRef.current) scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [neg?.messages?.length]);

  if (loading || !user || !neg) return null;

  const isSeller = user.id === neg.seller_id;
  const isBuyer = user.id === neg.buyer_id;
  const isAdmin = user.role === "admin";
  if (!isSeller && !isBuyer && !isAdmin) return null;

  const submitOpening = async (decline) => {
    setError(""); setSubmitting(true);
    try {
      const payload = decline ? { decline: true } : { price_eur: Number(priceInput) };
      const { data } = await api.post(`/auctions/${auctionId}/negotiation/opening`, payload);
      setNeg(data); setPriceInput("");
    } catch (e) { setError(formatError(e)); }
    finally { setSubmitting(false); }
  };

  const submitResponse = async (action) => {
    setError(""); setSubmitting(true);
    try {
      const payload = { action };
      if (action === "counter") payload.price_eur = Number(priceInput);
      const { data } = await api.post(`/auctions/${auctionId}/negotiation/response`, payload);
      setNeg(data); setPriceInput("");
    } catch (e) { setError(formatError(e)); }
    finally { setSubmitting(false); }
  };

  const submitFinal = async (action) => {
    setError(""); setSubmitting(true);
    try {
      const { data } = await api.post(`/auctions/${auctionId}/negotiation/final`, { action });
      setNeg(data);
    } catch (e) { setError(formatError(e)); }
    finally { setSubmitting(false); }
  };

  const sendMessage = async () => {
    if (!msgInput.trim()) return;
    try {
      const { data } = await api.post(`/auctions/${auctionId}/negotiation/messages`, { text: msgInput.trim() });
      setNeg((prev) => ({ ...prev, messages: [...(prev.messages || []), data.message] }));
      setMsgInput("");
    } catch (e) { setError(formatError(e)); }
  };

  const status = neg.status;
  const open = ["awaiting_seller_opening", "awaiting_buyer_response", "awaiting_seller_final"].includes(status);
  const deadlineLabel = open ? fmtCountdown(neg.seconds_left) : null;

  return (
    <section className="rounded-card border border-[hsl(var(--line))] bg-white p-6 mt-8" data-testid="negotiation-portal">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="overline text-[hsl(var(--accent))]">След-аукционни преговори</div>
          <h3 className="font-serif text-2xl mt-2">Резервът не беше достигнат</h3>
          <p className="mt-2 text-sm text-[hsl(var(--ink-muted))] max-w-xl">
            Имате 72 часа в общ прозорец (3 × 24 ч), за да договорите директна сделка. AutoBid.bg остава във фонов режим — таксата на купувача се прилага, ако сделката приключи успешно.
          </p>
        </div>
        <div className="text-right">
          <div className="overline text-[hsl(var(--ink-muted))]">Статус</div>
          <div className="text-sm font-semibold mt-1">{STATUS_LABEL[status] || status}</div>
          {deadlineLabel && (
            <div className="mt-1 inline-flex items-center gap-1.5 text-xs text-[hsl(var(--ink-muted))]"><Clock size={12} /> {deadlineLabel}</div>
          )}
        </div>
      </div>

      {/* Offer summary */}
      <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-card border border-[hsl(var(--line))] p-3">
          <div className="overline text-[hsl(var(--ink-muted))]">Водеща наддавка</div>
          <div className="font-serif text-xl mt-1">{formatEUR(auction?.current_bid_eur || 0)}</div>
        </div>
        <div className="rounded-card border border-[hsl(var(--line))] p-3">
          <div className="overline text-[hsl(var(--ink-muted))]">Оферта на продавача</div>
          <div className="font-serif text-xl mt-1">{neg.seller_offer_eur ? formatEUR(neg.seller_offer_eur) : "—"}</div>
        </div>
        <div className="rounded-card border border-[hsl(var(--line))] p-3">
          <div className="overline text-[hsl(var(--ink-muted))]">Контра на купувача</div>
          <div className="font-serif text-xl mt-1">{neg.buyer_counter_eur ? formatEUR(neg.buyer_counter_eur) : "—"}</div>
        </div>
      </div>

      {status === "accepted" && (
        <div className="mt-5 p-3 rounded-card bg-[hsl(var(--accent-soft))] border border-[hsl(var(--accent))]/30 flex items-center gap-2" data-testid="negotiation-accepted">
          <CheckCircle2 size={16} className="text-[hsl(var(--accent))]" />
          <div className="text-sm">Сделката е сключена за <strong>{formatEUR(neg.final_price_eur)}</strong>. Такса купувач: <strong>{formatEUR(neg.buyer_fee_eur)}</strong>.</div>
        </div>
      )}
      {(status === "declined" || status === "expired") && (
        <div className="mt-5 p-3 rounded-card bg-[hsl(var(--surface))] border border-[hsl(var(--line))] flex items-center gap-2" data-testid="negotiation-closed">
          <XCircle size={16} className="text-[hsl(var(--ink-muted))]" />
          <div className="text-sm text-[hsl(var(--ink-muted))]">{STATUS_LABEL[status]}</div>
        </div>
      )}

      {isBuyer && status === "awaiting_buyer_response" && (
        <div className="mt-5 rule-t pt-5" data-testid="buyer-response-panel">
          <p className="text-sm mb-3">Оферта: <strong>{formatEUR(neg.seller_offer_eur)}</strong></p>
          <div className="space-y-2">
            <button onClick={() => submitResponse("accept")} disabled={submitting} className="btn btn-accent w-full sm:w-auto !px-5" data-testid="buyer-accept">Приеми</button>
            <div className="flex flex-col sm:flex-row gap-2">
              <input type="number" min={1} value={priceInput} onChange={(e) => setPriceInput(e.target.value)} placeholder="Контра (EUR)" className="w-full sm:w-40 border border-[hsl(var(--line))] h-11 px-3 text-sm" data-testid="buyer-counter-price" />
              <button onClick={() => submitResponse("counter")} disabled={submitting || !priceInput} className="btn btn-primary w-full sm:w-auto !px-5" data-testid="buyer-counter">Контраоферта</button>
            </div>
            <button onClick={() => submitResponse("decline")} disabled={submitting} className="btn btn-secondary w-full sm:w-auto !px-5" data-testid="buyer-decline">Откажи</button>
          </div>
        </div>
      )}

      {isSeller && status === "awaiting_seller_opening" && (
        <div className="mt-5 rule-t pt-5" data-testid="seller-opening-panel">
          <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Вашата начална оферта (EUR)</label>
          <div className="space-y-2">
            <input type="number" min={1} value={priceInput} onChange={(e) => setPriceInput(e.target.value)} placeholder="напр. 18000" className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm" data-testid="seller-opening-price" />
            <div className="flex flex-col sm:flex-row gap-2">
              <button onClick={() => submitOpening(false)} disabled={submitting || !priceInput} className="btn btn-accent w-full sm:w-auto !px-5" data-testid="seller-opening-submit">Изпрати оферта</button>
              <button onClick={() => submitOpening(true)} disabled={submitting} className="btn btn-secondary w-full sm:w-auto !px-5" data-testid="seller-opening-decline">Откажи</button>
            </div>
          </div>
        </div>
      )}

      {isSeller && status === "awaiting_seller_final" && (
        <div className="mt-5 rule-t pt-5" data-testid="seller-final-panel">
          <p className="text-sm mb-3">Контраоферта от купувача: <strong>{formatEUR(neg.buyer_counter_eur)}</strong></p>
          <div className="flex flex-col sm:flex-row flex-wrap gap-2">
            <button onClick={() => submitFinal("accept")} disabled={submitting} className="btn btn-accent w-full sm:w-auto !px-5" data-testid="seller-final-accept">Приеми</button>
            <button onClick={() => submitFinal("decline")} disabled={submitting} className="btn btn-secondary w-full sm:w-auto !px-5" data-testid="seller-final-decline">Откажи</button>
          </div>
        </div>
      )}

      {error && <p className="text-xs text-[hsl(var(--danger))] mt-3" data-testid="negotiation-error">{error}</p>}

      {/* Messaging */}
      <div className="mt-6 rule-t pt-5" data-testid="negotiation-messages">
        <div className="overline text-[hsl(var(--ink-muted))] mb-3">Чат</div>
        <div ref={scrollerRef} className="space-y-2 max-h-64 overflow-auto pr-1">
          {(neg.messages || []).length === 0 && <div className="text-xs text-[hsl(var(--ink-muted))]">Все още няма съобщения.</div>}
          {(neg.messages || []).map((m) => (
            <div key={m.id} className={`flex ${m.user_id === user.id ? "justify-end" : "justify-start"}`} data-testid={`neg-msg-${m.id}`}>
              <div className={`max-w-[78%] rounded-card px-3 py-2 text-sm ${m.user_id === user.id ? "bg-[hsl(var(--accent-soft))] border border-[hsl(var(--accent))]/30" : "bg-[hsl(var(--surface))] border border-[hsl(var(--line))]"}`}>
                <div className="flex items-center gap-1.5 text-[11px] text-[hsl(var(--ink-muted))]">
                  <span className="font-semibold text-[hsl(var(--ink))]">{m.user_name}</span>
                  {m.role === "seller" && (
                    <span className="text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-[hsl(var(--accent))] text-white">Продавач</span>
                  )}
                  <span>· {new Date(m.created_at).toLocaleString("bg-BG")}</span>
                </div>
                <div className="mt-1 leading-relaxed whitespace-pre-wrap">{m.text}</div>
              </div>
            </div>
          ))}
        </div>
        {open && (
          <div className="mt-3 flex gap-2">
            <input
              value={msgInput}
              onChange={(e) => setMsgInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), sendMessage())}
              placeholder="Напиши съобщение…"
              className="flex-1 border border-[hsl(var(--line))] h-11 px-3 text-sm"
              data-testid="negotiation-msg-input"
            />
            <button onClick={sendMessage} disabled={!msgInput.trim()} className="btn btn-primary !px-4 inline-flex items-center gap-1.5" data-testid="negotiation-msg-send">
              <Send size={14} /> Прати
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
