import React, { useState, useEffect } from "react";
import { X, Shield, Zap, CreditCard, TrendingUp } from "lucide-react";
import { api, formatEUR } from "../lib/apiClient";
import { formatError } from "../lib/auth";

export default function BiddingCreditModal({ auctionId, currentBid, currentCredit, onClose, onSaved }) {
  const [amount, setAmount] = useState(currentCredit?.max_amount_eur || Math.max(Math.ceil((currentBid + 10000) / 1000) * 1000, 10000));
  const [cardNumber, setCardNumber] = useState(currentCredit?.card_last4 ? `4242 4242 4242 ${currentCredit.card_last4}` : "4242 4242 4242 4242");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [releasing, setReleasing] = useState(false);

  const preauthAmount = Math.max(0, Math.round(amount * 0.02 * 100) / 100);
  const minAllowed = currentCredit ? Math.floor(currentCredit.max_amount_eur) + 1 : currentBid + 100;

  const submit = async () => {
    setErr(""); setBusy(true);
    try {
      const pmId = cardNumber.replace(/\s/g, "").trim();
      if (pmId.length < 4) { setErr("Моля, въведете валиден номер на карта"); setBusy(false); return; }
      const { data } = await api.post(`/auctions/${auctionId}/bidding-credit`, {
        max_amount_eur: Number(amount),
        payment_method_id: pmId,
      });
      onSaved && onSaved(data.credit);
      onClose();
    } catch (e) {
      setErr(formatError(e));
    } finally { setBusy(false); }
  };

  const release = async () => {
    if (!window.confirm("Сигурни ли сте, че искате да освободите кредита? Ще трябва да се преавторизирате отново за следващи наддавания.")) return;
    setErr(""); setReleasing(true);
    try {
      await api.delete(`/auctions/${auctionId}/bidding-credit`);
      onSaved && onSaved(null);
      onClose();
    } catch (e) { setErr(formatError(e)); }
    finally { setReleasing(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" data-testid="bidding-credit-modal">
      <div className="bg-white rounded-card w-full max-w-lg shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[hsl(var(--line))]">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full bg-[hsl(var(--accent-soft))] flex items-center justify-center text-[hsl(var(--accent))]">
              <Zap size={16} />
            </div>
            <h2 className="font-serif text-2xl">{currentCredit ? "Увеличи кредита" : "Наддавателен кредит"}</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-[hsl(var(--surface))] rounded-full"><X size={18} /></button>
        </div>

        <div className="p-6 space-y-5">
          <div className="rounded-card bg-[hsl(var(--accent-soft))] border border-[hsl(var(--accent))]/20 p-4 text-sm leading-relaxed">
            <div className="flex items-start gap-2.5">
              <Shield size={16} className="text-[hsl(var(--accent))] shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-[hsl(var(--accent-ink))] mb-1">Как работи?</p>
                <p className="text-[hsl(var(--ink))]/80">
                  Избирате <strong>максимална сума</strong>, до която сте готови да наддавате. Блокираме <strong>2% от тази сума</strong> на картата. След това можете да наддавате свободно до този лимит <strong>без нови картови транзакции</strong>. Ако бъдете надиграни — сумата се освобождава изцяло.
                </p>
              </div>
            </div>
          </div>

          {currentCredit && (
            <div className="rounded-card border border-[hsl(var(--line))] p-4 bg-[hsl(var(--surface))]">
              <div className="flex items-center justify-between">
                <div>
                  <div className="overline text-[hsl(var(--ink-muted))]">Активен кредит</div>
                  <div className="font-serif text-2xl mt-1">{formatEUR(currentCredit.max_amount_eur)}</div>
                </div>
                <div className="text-right">
                  <div className="overline text-[hsl(var(--ink-muted))]">Блокирани</div>
                  <div className="font-mono text-lg mt-1">{formatEUR(currentCredit.preauth_amount_eur)}</div>
                </div>
              </div>
            </div>
          )}

          <div>
            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">
              {currentCredit ? "Нов максимум (трябва да е по-висок)" : "Максимум до колкото ще наддавате"}
            </label>
            <div className="relative">
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                min={minAllowed}
                step={1000}
                className="w-full border border-[hsl(var(--line))] h-14 px-4 text-2xl font-serif pr-12"
                data-testid="credit-amount-input"
              />
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-xl text-[hsl(var(--ink-muted))]">€</span>
            </div>
            <p className="mt-1.5 text-xs text-[hsl(var(--ink-muted))]">
              Текуща водеща оферта: {formatEUR(currentBid)} · Минимум: {formatEUR(minAllowed)}
            </p>
          </div>

          <div className="rounded-card border border-[hsl(var(--line))] p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[hsl(var(--ink-muted))] flex items-center gap-1.5">
                <TrendingUp size={13} /> Pre-authorization (2%)
              </span>
              <span className="font-serif text-xl">{formatEUR(preauthAmount)}</span>
            </div>
            <p className="text-xs text-[hsl(var(--ink-muted))]">
              Блокира се сега на картата ви. Удържа се само ако спечелите търга.
            </p>
          </div>

          {!currentCredit && (
            <div>
              <label className="overline text-[hsl(var(--ink-muted))] block mb-2 flex items-center gap-1.5">
                <CreditCard size={11} /> Номер на карта
              </label>
              <input
                type="text"
                value={cardNumber}
                onChange={(e) => setCardNumber(e.target.value)}
                placeholder="4242 4242 4242 4242"
                className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono"
                data-testid="credit-card-input"
              />
              <p className="mt-1.5 text-xs text-[hsl(var(--ink-muted))]">
                Тестов режим · използвайте 4242 4242 4242 4242
              </p>
            </div>
          )}

          {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="credit-error">{err}</p>}

          <div className="flex items-center gap-2 pt-2">
            {currentCredit && (
              <button onClick={release} disabled={releasing || busy} className="btn btn-secondary !py-2.5 !px-4 text-sm !text-[hsl(var(--danger))] !border-[hsl(var(--danger))]/30" data-testid="credit-release">
                {releasing ? "Освобождавам…" : "Освободи кредита"}
              </button>
            )}
            <div className="flex-1" />
            <button onClick={onClose} disabled={busy || releasing} className="btn btn-secondary">Отказ</button>
            <button onClick={submit} disabled={busy || releasing} className="btn btn-accent flex items-center gap-2" data-testid="credit-submit">
              <Zap size={14} /> {busy ? "Обработка…" : currentCredit ? "Увеличи" : "Блокирай 2%"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
