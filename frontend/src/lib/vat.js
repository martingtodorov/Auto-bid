// Gross (incl. VAT) amount helper — mirrors backend `_gross_amount` in
// server.py so list/card/ticker UIs don't drift from how the bid is billed.
//
// Usage:
//   import { grossEUR } from "../lib/vat";
//   formatEUR(grossEUR(auction.current_bid_eur, auction))
//
// Contract:
//   • `vat_status === "vat_inclusive"` → returns `net * (1 + rate/100)`.
//   • any other status (incl. missing) → returns the net amount unchanged
//     (vat_exempt auctions quote prices without VAT by design).
export function grossEUR(netEur, auction) {
  const n = Number(netEur || 0);
  if (!auction || auction.vat_status !== "vat_inclusive") return n;
  const rate = Number(auction.vat_rate_pct || 0);
  if (!rate) return n;
  return Math.round(n * (1 + rate / 100) * 100) / 100;
}
