/**
 * Variable bid step (mirrors backend _bid_step — halved brackets).
 * Used both on AuctionDetailPage (live ticker) and MyBidsPage (quick re-bid).
 */
export function bidStepFor(price) {
  const p = Number(price) || 0;
  if (p < 1000) return 25;
  if (p < 5000) return 50;
  if (p < 10000) return 125;
  if (p < 25000) return 250;
  if (p < 50000) return 400;
  if (p < 100000) return 500;
  if (p < 200000) return 1000;
  if (p < 500000) return 2500;
  if (p < 1000000) return 5000;
  return 10000;
}

/** Next minimum bid given the current price. */
export function minNextBid(currentBid) {
  return Math.floor(Number(currentBid) || 0) + bidStepFor(currentBid);
}
