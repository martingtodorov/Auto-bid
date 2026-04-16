import React, { useState } from "react";
import { CreditCard, Lock, X } from "lucide-react";
import { formatEUR } from "../lib/apiClient";

/**
 * Mock Stripe-style card capture modal. Does no network call — returns a
 * synthetic payment_method_id back to caller. UI is realistic so it can be
 * swapped for real Stripe Elements later.
 */
export default function PreauthModal({ open, onClose, onConfirm, bidAmount }) {
  const [number, setNumber] = useState("4242 4242 4242 4242");
  const [exp, setExp] = useState("12/28");
  const [cvc, setCvc] = useState("123");
  const [name, setName] = useState("");
  const [processing, setProcessing] = useState(false);
  const [err, setErr] = useState("");

  if (!open) return null;
  const preauth = Math.round((Number(bidAmount) || 0) * 0.02);

  const formatCard = (v) => v.replace(/\D/g, "").slice(0, 16).replace(/(\d{4})(?=\d)/g, "$1 ");
  const formatExp = (v) => {
    const clean = v.replace(/\D/g, "").slice(0, 4);
    return clean.length > 2 ? `${clean.slice(0, 2)}/${clean.slice(2)}` : clean;
  };

  const submit = async () => {
    setErr("");
    const digits = number.replace(/\s/g, "");
    if (digits.length < 13) return setErr("Невалиден номер на карта");
    if (!/^\d{2}\/\d{2}$/.test(exp)) return setErr("Невалидна валидност (ММ/ГГ)");
    if (cvc.length < 3) return setErr("Невалиден CVC код");
    if (!name.trim()) return setErr("Въведете име върху картата");

    setProcessing(true);
    // Simulate Stripe tokenization latency
    await new Promise((r) => setTimeout(r, 900));
    const pm = `mock_pm_${digits}`;
    setProcessing(false);
    onConfirm(pm, digits.slice(-4));
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4" data-testid="preauth-modal">
      <div className="bg-white w-full max-w-md rounded-card border border-[hsl(var(--line))] overflow-hidden">
        <div className="p-5 flex items-center justify-between rule-b">
          <div className="flex items-center gap-2">
            <Lock size={16} />
            <span className="font-serif text-lg">Потвърди картата</span>
          </div>
          <button onClick={onClose} data-testid="preauth-close"><X size={18} /></button>
        </div>

        <div className="p-6">
          <div className="rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] p-4 flex items-center justify-between">
            <div>
              <div className="overline text-[hsl(var(--ink-muted))]">Блокиране (2%)</div>
              <div className="font-serif text-2xl mt-1">{formatEUR(preauth)}</div>
              <div className="text-xs text-[hsl(var(--ink-muted))] mt-1">Задържа се до финализиране на сделката. При победа се ползва за 2% buyer's premium, иначе се освобождава изцяло.</div>
            </div>
            <CreditCard size={40} className="text-[hsl(var(--ink-muted))]" />
          </div>

          <div className="mt-6 space-y-4">
            <div>
              <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Номер на карта</label>
              <input
                value={number}
                onChange={(e) => setNumber(formatCard(e.target.value))}
                placeholder="1234 5678 9012 3456"
                className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono"
                data-testid="preauth-card-number"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Валидност</label>
                <input value={exp} onChange={(e) => setExp(formatExp(e.target.value))} className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono" data-testid="preauth-exp" />
              </div>
              <div>
                <label className="overline text-[hsl(var(--ink-muted))] block mb-2">CVC</label>
                <input value={cvc} onChange={(e) => setCvc(e.target.value.replace(/\D/g, "").slice(0, 4))} className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm font-mono" data-testid="preauth-cvc" />
              </div>
            </div>
            <div>
              <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Име върху картата</label>
              <input value={name} onChange={(e) => setName(e.target.value)} className="w-full border border-[hsl(var(--line))] h-11 px-3 text-sm" data-testid="preauth-name" />
            </div>
            {err && <p className="text-sm text-[hsl(var(--danger))]" data-testid="preauth-error">{err}</p>}
          </div>

          <button onClick={submit} disabled={processing} className="btn btn-accent w-full mt-6" data-testid="preauth-confirm">
            {processing ? "Обработка…" : `Оторизирай ${formatEUR(preauth)} и наддай`}
          </button>
          <p className="text-xs text-center text-[hsl(var(--ink-muted))] mt-3 flex items-center justify-center gap-1">
            <Lock size={11} /> Тестов режим · Използвай 4242 4242 4242 4242
          </p>
        </div>
      </div>
    </div>
  );
}
