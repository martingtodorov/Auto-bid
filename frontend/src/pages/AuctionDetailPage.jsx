import React, { useEffect, useState, useCallback, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Calendar, Gauge, Fuel, Settings, MapPin, Palette, Zap, Cog, MessageCircle, Heart, ArrowLeft, Shield, Wifi, Share2, Languages, Gavel, ChevronUp, ChevronDown, TrendingUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api, API_BASE, formatEUR, formatLocal, formatKM, timeLeft, formatTimeLeft, intlLocale } from "../lib/apiClient";
import { translateEnum } from "../lib/carTranslations";
import { useAuth, formatError } from "../lib/auth";
import BidConfirmModal from "../components/BidConfirmModal";
import TopUpCreditModal from "../components/TopUpCreditModal";
import Picture from "../components/Picture";
import AuctionCard from "../components/AuctionCard";
import NegotiationPortal from "../components/NegotiationPortal";
import Lightbox from "../components/Lightbox";
import Avatar from "../components/Avatar";
import { useSiteSettings, computeBuyerFee } from "../lib/settings";
import { setPageMeta, resetPageMeta, buildVehicleJsonLd, buildBreadcrumbs, combineJsonLd } from "../lib/seo";
import AuctionVideo from "../components/AuctionVideo";
import { brandNameForLang } from "../i18n/index";
import { auctionUrl } from "../lib/auctionUrl";

export default function AuctionDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [a, setA] = useState(null);
  const [bids, setBids] = useState([]);
  const [comments, setComments] = useState([]);
  const [photoIdx, setPhotoIdx] = useState(0);
  const [lightboxIdx, setLightboxIdx] = useState(null);
  const [bidAmount, setBidAmount] = useState("");
  const [commentText, setCommentText] = useState("");
  const [tl, setTl] = useState({ label: "" });
  const [error, setError] = useState("");
  const [placing, setPlacing] = useState(false);
  const [buyingNow, setBuyingNow] = useState(false);
  const [showCredit, setShowCredit] = useState(false);
  const [showBidConfirm, setShowBidConfirm] = useState(false);
  // Stash the typed bid amounts at the moment the user clicked "Наддай"
  // so the confirm overlay always reflects what they intended, not the
  // input field which may keep changing in the background while a modal
  // is open.
  const [pendingBid, setPendingBid] = useState(null);
  const [wsStatus, setWsStatus] = useState("connecting");
  const [watching, setWatching] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [vinRequesting, setVinRequesting] = useState(false);
  const [vinMsg, setVinMsg] = useState("");
  const [vinErr, setVinErr] = useState("");
  const [related, setRelated] = useState([]);
  // Account-level credit pool (universal, not per-auction). Powers the
  // bid validation gate below — if the user doesn't have enough free
  // credit we open `TopUpCreditModal` instead of placing the bid.
  const [accountCredit, setAccountCredit] = useState(null);
  const [nextBid, setNextBid] = useState({ min_next_eur: 0, buyer_fee_eur: 150, step_eur: 100 });
  const titleRef = useRef(null);
  const wsRef = useRef(null);
  const mainImageRef = useRef(null);

  // ── Mobile big-image swipe ────────────────────────────────────────────────
  // On mobile, swiping the hero image left/right moves between photos using
  // the same 10° lock rule as the AuctionCard mini-carousel:
  //   • If the gesture deviates ≤10° from the horizontal axis, lock to
  //     horizontal and call `preventDefault()` on every touchmove so the
  //     page doesn't scroll under the finger.
  //   • Anything steeper (i.e. clearly vertical) bubbles up to the
  //     browser → user can scroll the page normally even if their thumb
  //     happens to land on the image.
  // The click handler that opens the lightbox is suppressed when a swipe
  // actually fires (`swipeRef.current.cancelClick = true`).
  const swipeRef = useRef(null);
  const photoIdxRef = useRef(0);
  useEffect(() => { photoIdxRef.current = photoIdx; }, [photoIdx]);
  useEffect(() => {
    const el = mainImageRef.current;
    if (!el) return;
    const total = a?.images?.length || 0;
    if (total < 2) return;
    // 10° from horizontal → tan(10°) ≈ 0.176
    const ANGLE_TAN = Math.tan((10 * Math.PI) / 180);
    const COMMIT_PX = 50;        // min horizontal distance to commit a slide change
    const DETECT_PX = 8;         // min movement before deciding axis lock

    const onStart = (e) => {
      const t = e.touches[0];
      swipeRef.current = {
        x: t.clientX,
        y: t.clientY,
        dx: 0,
        locked: null,
        cancelClick: false,
      };
    };
    const onMove = (e) => {
      const s = swipeRef.current;
      if (!s) return;
      const t = e.touches[0];
      const dx = t.clientX - s.x;
      const dy = t.clientY - s.y;
      const absX = Math.abs(dx), absY = Math.abs(dy);
      if (s.locked === null) {
        if (absX < DETECT_PX && absY < DETECT_PX) return;
        // 10° rule: angle from horizontal axis = atan(|dy|/|dx|).
        // Horizontal lock when |dy| < |dx| * tan(10°).
        s.locked = absX > absY && absY <= absX * ANGLE_TAN ? "h" : "v";
      }
      if (s.locked === "h") {
        e.preventDefault(); // requires non-passive listener (set below)
        s.dx = dx;
      }
    };
    const onEnd = () => {
      const s = swipeRef.current;
      if (!s) return;
      if (s.locked === "h" && Math.abs(s.dx) > COMMIT_PX) {
        const cur = photoIdxRef.current;
        const next = s.dx < 0
          ? Math.min(total - 1, cur + 1)   // swipe left → next photo
          : Math.max(0, cur - 1);          // swipe right → prev photo
        if (next !== cur) setPhotoIdx(next);
        s.cancelClick = true;
      }
      // Keep the ref alive briefly so the synthetic `click` that fires
      // after touchend can read `cancelClick`. We null it on the next tick.
      setTimeout(() => { swipeRef.current = null; }, 0);
    };

    // touchmove must be non-passive so `preventDefault()` works on iOS.
    el.addEventListener("touchstart", onStart, { passive: true });
    el.addEventListener("touchmove", onMove, { passive: false });
    el.addEventListener("touchend", onEnd, { passive: true });
    el.addEventListener("touchcancel", onEnd, { passive: true });
    return () => {
      el.removeEventListener("touchstart", onStart);
      el.removeEventListener("touchmove", onMove);
      el.removeEventListener("touchend", onEnd);
      el.removeEventListener("touchcancel", onEnd);
    };
  }, [a?.images?.length]);
  const settings = useSiteSettings();

  // Client-side buyer fee for preview (mirrors backend _buyer_fee)
  const buyerFeeFor = (amount) => computeBuyerFee(amount, settings);

  // Variable bid step (mirrors backend _bid_step — halved brackets)
  const bidStepFor = (price) => {
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
  };

  const load = useCallback(async () => {
    try {
      const ra = await api.get(`/auctions/${id}`);
      const [rb, rc, rn] = await Promise.all([
        api.get(`/auctions/${id}/bids`).catch(() => ({ data: [] })),
        api.get(`/auctions/${id}/comments`).catch(() => ({ data: [] })),
        api.get(`/auctions/${id}/next-bid`).catch(() => ({ data: null })),
      ]);
      setA(ra.data);
      setBids(rb.data);
      setComments(rc.data);
      const step = bidStepFor(ra.data.current_bid_eur);
      const minNext = rn.data?.min_next_eur || (Math.floor(ra.data.current_bid_eur) + step);
      setNextBid(rn.data || { min_next_eur: minNext, buyer_fee_eur: buyerFeeFor(minNext), step_eur: step });
      // Prefill the bid input with the gross-equivalent of `minNext` when the
      // auction is sold INCL. VAT — the user is shown a gross value in the
      // input and we convert back to net only on submit (see `startBid`).
      const rate = ra.data.vat_status === "vat_inclusive" ? Number(ra.data.vat_rate_pct || 0) : 0;
      const minDisplay = rate > 0 ? Math.ceil(minNext * (1 + rate / 100)) : minNext;
      setBidAmount(String(Math.floor(minDisplay)));
    } catch (e) {
      if (e?.response?.status === 404) setNotFound(true);
      else console.error(e);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Fetch related auctions (same make preferred, fallback to same body_type; excluding self)
  // All three queries pass `view: "list"` to ensure we get the lightweight
  // card shape (~1.5 KB / item) instead of the legacy heavy shape that
  // included full descriptions + every gallery bucket (>9 MB on prod).
  useEffect(() => {
    if (!a) return;
    let cancelled = false;
    (async () => {
      try {
        const byMake = await api.get("/auctions", { params: { make: a.make, status: "live", limit: 12, view: "list" } }).catch(() => ({ data: [] }));
        let items = (byMake.data || []).filter((x) => x.id !== a.id);
        if (items.length < 4) {
          const byBody = await api.get("/auctions", { params: { body_type: a.body_type, status: "live", limit: 12, view: "list" } }).catch(() => ({ data: [] }));
          const extra = (byBody.data || []).filter((x) => x.id !== a.id && !items.find((y) => y.id === x.id));
          items = [...items, ...extra];
        }
        if (items.length < 4) {
          const any = await api.get("/auctions", { params: { status: "live", limit: 12, view: "list" } }).catch(() => ({ data: [] }));
          const extra = (any.data || []).filter((x) => x.id !== a.id && !items.find((y) => y.id === x.id));
          items = [...items, ...extra];
        }
        if (!cancelled) setRelated(items.slice(0, 4));
      } catch (e) { /* skip */ }
    })();
    return () => { cancelled = true; };
  }, [a]);

  // Watch status
  useEffect(() => {
    if (!user || !id) { setWatching(false); return; }
    api.get(`/auctions/${id}/watch-status`).then((r) => setWatching(!!r.data.watching)).catch(() => {});
  }, [user, id]);

  // Account-level credit pool (universal, not per-auction).
  // Refreshed on user/auction load + on `credits-updated` events
  // (dispatched from top-up / release flows). This drives the
  // "do you have enough credit to bid?" gate in `startBid` below.
  useEffect(() => {
    if (!user) { setAccountCredit(null); return; }
    let cancelled = false;
    const fetchCredit = () => {
      api.get("/stripe/authorizations/my-credits")
        .then((r) => { if (!cancelled) setAccountCredit(r.data || null); })
        .catch(() => { if (!cancelled) setAccountCredit(null); });
    };
    fetchCredit();
    const onUpdate = () => fetchCredit();
    window.addEventListener("credits-updated", onUpdate);
    return () => {
      cancelled = true;
      window.removeEventListener("credits-updated", onUpdate);
    };
  }, [user, id]);

  // SEO meta tags + structured data
  useEffect(() => {
    if (!a) return;
    const url = window.location.href;
    const origin = window.location.origin;
    const lang = (i18n.resolvedLanguage || i18n.language || "bg").slice(0, 2);
    const breadcrumbs = buildBreadcrumbs([
      { name: t("nav.home", "Home"), url: origin + "/" },
      { name: t("nav.auctions", "Auctions"), url: origin + "/auctions" },
      { name: a.title, url },
    ]);
    const vehicle = buildVehicleJsonLd(a, url);
    const brand = brandNameForLang(lang);

    // ---- Locale-aware title / description ---------------------------------
    // Fallback verige: Gemini cache (`title_<lang>` / `seo_description_<lang>`)
    // → пълно описание на локала → BG оригинал.
    const auctionPrefix = t("seo.auction_prefix", "Auction");
    const titleLocalized = a[`title_${lang}`] || a.title || "";
    const finalTitle = `${auctionPrefix} ${titleLocalized} — ${brand}`;
    const finalDescription =
      a[`seo_description_${lang}`] ||
      (a[`description_${lang}`] || "").slice(0, 280) ||
      (a.description || "").slice(0, 280);

    // ---- Cross-domain alternates (hreflang) -------------------------------
    // Същият path се сервира на трите TLD-та; DomainDetector ще избере
    // правилния език при посещение от crawler / потребител.
    const path = window.location.pathname + window.location.search;
    const alternates = {
      bg: `https://autoandbid.bg${path}`,
      en: `https://autoandbid.com${path}`,
      ro: `https://autoandbid.ro${path}`,
    };

    setPageMeta({
      title: finalTitle,
      description: finalDescription,
      // Dynamic per-auction OG image (English, with Auto&Bid wordmark,
      // time remaining + current bid). Backend endpoint returns a
      // 1200×630 PNG keyed on bid + ends_at so crawlers see fresh
      // numbers after each bid.
      image: `${API_BASE}/og/auction/${a.id}.png`,
      url,
      locale: lang,
      alternates,
      jsonLd: combineJsonLd(vehicle, breadcrumbs),
    });
    return () => resetPageMeta();
  }, [a, i18n.language, i18n.resolvedLanguage]);

  const toggleWatch = async () => {
    if (!user) { navigate("/login?next=/auctions/" + id); return; }
    try {
      const { data } = await api.post(`/auctions/${id}/watch`);
      setWatching(!!data.watching);
    } catch (e) {}
  };

  const onBuyNow = async () => {
    if (!user) { navigate("/login?next=/auctions/" + id); return; }
    if (!a?.buy_now_eur) return;
    const grossPrice = a.vat_status === "vat_inclusive" ? Math.round(Number(a.buy_now_eur) * (1 + Number(a.vat_rate_pct || 0) / 100)) : Number(a.buy_now_eur);
    const confirmMsg = t("auction.buy_now_confirm", "Сигурни ли сте, че искате да купите този автомобил веднага за {{price}} €?", { price: grossPrice.toLocaleString("bg-BG") });
    if (!window.confirm(confirmMsg)) return;
    setBuyingNow(true);
    setError("");
    try {
      // Hand off to Stripe Checkout. The backend creates a PaymentIntent
      // for the full GROSS price (incl. VAT) and returns a hosted URL.
      // `origin` preserves the domain the user is on (.bg vs .com) so
      // Stripe's success_url redirects back to the SAME domain.
      const { data } = await api.post(`/auctions/${id}/buy-now`, {
        origin: window.location.origin,
      });
      if (data?.url) {
        window.location.assign(data.url);
        return;
      }
      // Fallback (should never happen — backend always returns redirect)
      const { data: fresh } = await api.get(`/auctions/${id}`);
      setA(fresh);
    } catch (e) {
      setError(formatError(e));
    } finally {
      setBuyingNow(false);
    }
  };

  // WebSocket for real-time updates
  useEffect(() => {
    if (!id) return;
    const wsUrl = API_BASE.replace(/^http/, "ws") + `/ws/auctions/${id}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onopen = () => setWsStatus("connected");
    ws.onclose = () => setWsStatus("disconnected");
    ws.onerror = () => setWsStatus("disconnected");
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "bid") {
          setA((prev) => prev ? ({
            ...prev,
            current_bid_eur: msg.current_bid_eur,
            bid_count: msg.bid_count,
            high_bidder_name: msg.high_bidder_name,
            ends_at: msg.ends_at,
          }) : prev);
          setBids((prev) => {
            if (prev.some((b) => b.id === msg.bid.id)) return prev;
            return [{ ...msg.bid, user_name: msg.high_bidder_name, amount_eur: msg.current_bid_eur }, ...prev];
          });
          const step = bidStepFor(msg.current_bid_eur);
          const newMin = Math.floor(msg.current_bid_eur) + step;
          setNextBid({ min_next_eur: newMin, buyer_fee_eur: buyerFeeFor(newMin), step_eur: step });
          // bidAmount is held in GROSS when the auction is vat_inclusive — bump
          // the displayed gross min, not the net one.
          const rate = (a && a.vat_status === "vat_inclusive") ? Number(a.vat_rate_pct || 0) : 0;
          const newMinDisplay = rate > 0 ? Math.ceil(newMin * (1 + rate / 100)) : newMin;
          setBidAmount((cur) => String(Math.max(newMinDisplay, Number(cur || 0))));
        } else if (msg.type === "comment") {
          setComments((prev) => {
            if (prev.some((c) => c.id === msg.comment.id)) return prev;
            return [msg.comment, ...prev];
          });
        } else if (msg.type === "comment_deleted") {
          setComments((prev) => prev.map((c) => c.id === msg.comment.id ? { ...c, ...msg.comment } : c));
        }
      } catch (e) {}
    };
    // keepalive ping every 25s
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 25000);
    return () => { clearInterval(ping); ws.close(); };
  }, [id]);

  useEffect(() => {
    if (!a) return;
    setTl(timeLeft(a.ends_at));
    if (a.status === "sold" || a.status === "ended") return;
    const i = setInterval(() => setTl(timeLeft(a.ends_at)), 1000);
    return () => clearInterval(i);
  }, [a]);

  const startBid = () => {
    setError("");
    if (!user) { navigate("/login?next=/auctions/" + id); return; }
    // The user types a GROSS (incl. VAT) amount when the listing is VAT-inclusive.
    // The backend always tracks bids in NET — so convert here before validation.
    const typed = Number(bidAmount);
    const netAmt = vatRate > 0 ? typed / (1 + vatRate / 100) : typed;
    const minNet = nextBid.min_next_eur || (Math.floor(a.current_bid_eur) + bidStepFor(a.current_bid_eur));
    if (!typed || netAmt < minNet - 0.5) {
      const minDisplay = vatRate > 0 ? Math.ceil(minNet * (1 + vatRate / 100)) : minNet;
      setError(`${t("auction.min_bid_error", "Минималното следващо наддаване е")} €${minDisplay.toLocaleString()}`);
      return;
    }
    // Account-level credit pool check. We treat the user's existing
    // high-bid on THIS auction as already-committed, so a top-up bid
    // only needs the *delta* to fit within the available pool.
    const isAdmin = ["admin", "moderator"].includes(user?.role);
    const myCurrent = a.high_bidder_id === user.id ? Number(a.current_bid_eur || 0) : 0;
    const newCommitDelta = Math.max(0, netAmt - myCurrent);
    const available = Number(accountCredit?.total_available_eur || 0);
    if (!isAdmin && newCommitDelta > available + 0.5) {
      // Not enough — open the top-up modal pre-filled with the shortfall.
      setPendingBid({ gross: typed, net: netAmt });
      setShowCredit(true);
      return;
    }
    // Sufficient credit — show the confirmation overlay.
    setPendingBid({ gross: typed, net: netAmt });
    setShowBidConfirm(true);
  };

  const confirmBid = async (overrideNet) => {
    setPlacing(true);
    try {
      // The modal passes the user-edited net amount. Fall back to the
      // form value when a non-modal flow (e.g. credit-backed quick
      // confirm path) calls without an argument.
      let netAmt = Number(overrideNet);
      if (!netAmt) {
        const typed = Number(bidAmount);
        netAmt = vatRate > 0 ? Math.round(typed / (1 + vatRate / 100)) : typed;
      } else {
        netAmt = Math.round(netAmt);
      }
      await api.post(`/auctions/${id}/bids`, { amount_eur: netAmt });
      // refresh auction so user sees updated current_bid immediately
      await load();
      // Refresh the global credit counter so the bid's commitment is
      // reflected in the nav wallet without waiting for the 90-s poll.
      window.dispatchEvent(new Event("credits-updated"));
    } catch (e) {
      setError(formatError(e));
    } finally {
      setPlacing(false);
    }
  };

  // ─── Post-Stripe-Checkout return handler ───
  // When the user returns from Stripe's hosted checkout, the URL contains
  // `?stripe_session_id=cs_test_...`. We then:
  //   1. Pull the active authorization for this auction;
  //   2. If a pending bid is in localStorage, place it (auth covers preauth);
  //   3. If a pending credit intent is in localStorage, register it;
  //   4. Clear the URL params.
  // The card data was handled entirely by Stripe — we never see the PAN.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sid = params.get("stripe_session_id");
    const cancelled = params.get("stripe_cancelled");
    // ─── Buy Now return handler ────────────────────────────────────────
    // Separate param name so we don't collide with the bidding flow.
    // Backend `/buy-now/finalize` atomically claims the auction; if we
    // lost the race it refunds us automatically. `paid` is determined
    // by Stripe's webhook — poll up to 10× (20s) for the session to
    // transition to `paid` in case the browser redirect beat the webhook.
    const buyNowSid = params.get("buy_now_session");
    const buyNowCancelled = params.get("buy_now_cancelled");
    if (buyNowCancelled) {
      setError(t("auction.buy_now_cancelled", "Покупката бе отказана."));
      params.delete("buy_now_cancelled");
      window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
      return;
    }
    if (buyNowSid && id) {
      let cancel = false;
      (async () => {
        for (let i = 0; i < 10 && !cancel; i++) {
          try {
            await api.post(`/auctions/${id}/buy-now/finalize`, { session_id: buyNowSid });
            const { data: fresh } = await api.get(`/auctions/${id}`);
            setA(fresh);
            break;
          } catch (e) {
            const status = e?.response?.status;
            if (status === 409) {
              // Someone else won — refund already issued by backend.
              setError(formatError(e));
              break;
            }
            if (status === 402) {
              // Payment not yet confirmed by Stripe webhook — retry.
              await new Promise((r) => setTimeout(r, 2000));
              continue;
            }
            setError(formatError(e));
            break;
          }
        }
        params.delete("buy_now_session");
        window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
      })();
      return () => { cancel = true; };
    }
    if (cancelled) {
      setError(t("preauth.stripe_cancelled", "Плащането през Stripe бе отказано."));
      params.delete("stripe_cancelled");
      window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
      try { localStorage.removeItem(`pending_bid_${id}`); } catch (_e) { /* ignore */ }
      try { localStorage.removeItem(`pending_credit_${id}`); } catch (_e) { /* ignore */ }
      return;
    }
    if (!sid || !id) return;
    let cancel = false;
    (async () => {
      // Account-level top-up flow now lands on /my-bids, so this
      // handler is mostly a safety net for users who navigate back to
      // the auction page with the session_id still in the URL. We
      // just refresh the credit counter and clean up the URL.
      window.dispatchEvent(new Event("credits-updated"));
      // Clean up URL.
      params.delete("stripe_session_id");
      window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? "?" + params : ""}`);
      // Clear any stale legacy localStorage from the old per-auction flow.
      try { localStorage.removeItem(`pending_credit_${id}`); } catch (_e) { /* ignore */ }
      try { localStorage.removeItem(`pending_bid_${id}`); } catch (_e) { /* ignore */ }
    })();
    return () => { cancel = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const postComment = async () => {
    setError("");
    if (!user) { navigate("/login?next=/auctions/" + id); return; }
    if (!commentText.trim()) return;
    try {
      await api.post(`/auctions/${id}/comments`, { text: commentText.trim() });
      setCommentText("");
    } catch (e) { setError(formatError(e)); }
  };

  const respondCounter = async (accept) => {
    setError("");
    try {
      await api.post(`/auctions/${id}/counter-offer/respond`, { accept });
      await load();
    } catch (e) { setError(formatError(e)); }
  };

  const requestVin = async () => {
    setVinMsg(""); setVinErr(""); setVinRequesting(true);
    try {
      const { data } = await api.post(`/auctions/${id}/request-vin`);
      setVinMsg(data.message || "Изпратено");
    } catch (e) {
      setVinErr(formatError(e));
    } finally {
      setVinRequesting(false);
    }
  };

  if (notFound) return (
    <main className="py-24 text-center" data-testid="auction-not-found">
      <h1 className="font-serif text-4xl">{t("auction.not_found")}</h1>
      <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Обявата може да е оттеглена или archiveирана.</p>
      <Link to="/auctions" className="btn btn-primary mt-8 inline-flex">Към всички търгове</Link>
    </main>
  );
  if (!a) return <div className="py-24 text-center">{t("common.loading")}</div>;

  const lng = i18n.language;
  const specs = [
    { i: Calendar, l: t("spec.year", "Година"), v: a.year },
    { i: Gauge, l: t("spec.mileage", "Пробег"), v: formatKM(a.mileage_km) },
    { i: Fuel, l: t("auction.fuel_label"), v: translateEnum(a.fuel, "fuel", lng) },
    { i: Settings, l: t("auction.transmission_label"), v: translateEnum(a.transmission, "transmission", lng) },
    { i: Cog, l: t("spec.engine", "Двигател"), v: `${a.engine_cc} cm³` },
    { i: Zap, l: t("spec.power", "Мощност"), v: `${a.power_hp} ${t("spec.hp", "к.с.")}` },
    { i: Palette, l: t("spec.colour", "Цвят"), v: translateEnum(a.color, "colour", lng) },
    { i: MapPin, l: t("spec.location", "Локация"), v: `${translateEnum(a.city, "city", lng)}${a.country ? `, ${a.country}` : ""}` },
  ];

  const isLive = a.status === "live";
  // VAT helpers — when an auction is sold WITH VAT (vat_inclusive), the user
  // enters their bid as GROSS in the input box (the label says "вкл. ДДС") and
  // we convert to NET only on submit. `bidAmount` here is already the gross
  // value; for vat_exempt auctions gross == net, so no conversion needed.
  const vatRate = a.vat_status === "vat_inclusive" ? Number(a.vat_rate_pct || 0) : 0;
  const grossOf = (net) => Math.round(Number(net || 0) * (1 + vatRate / 100));
  const currentBidGross = grossOf(a.current_bid_eur);
  const bidAmountGross = Math.round(Number(bidAmount || 0));  // bidAmount IS gross
  const preauthPreview = buyerFeeFor(bidAmountGross);
  const hasPendingCounterForMe = false;  // superseded by NegotiationPortal
  const isAdmin = user?.role === "admin";

  const deleteComment = async (commentId) => {
    if (!window.confirm("Да се премахне ли този коментар?")) return;
    try {
      await api.delete(`/admin/comments/${commentId}`);
      setComments((prev) => prev.map((c) => c.id === commentId ? { ...c, deleted: true, text: t("auction.comment_removed") } : c));
    } catch (e) {
      alert(formatError(e));
    }
  };

  return (
    <main className="rule-b" data-testid="auction-detail-page">
      {/*
        Mobile-only sticky header — uses `sticky top-16` (NOT `fixed`) so
        it lives in the document flow right below the main nav (64 px
        tall, `sticky top-0 z-50`). The `sticky` positioning keeps it
        correctly offset from the nav during the top-banner reveal /
        iOS address-bar bounce — `fixed` was overlapping the nav by a
        few pixels at scroll-top because the nav rides with the banner
        above it before it actually sticks.
      */}
      {a && (
        <div
          className="sticky top-[65px] z-40 lg:hidden"
          data-testid="mobile-sticky-header"
        >
          <div className="bg-[hsl(var(--bg))]/95 backdrop-blur-md border-b border-[hsl(var(--line))] shadow-lg">
            <div className="px-3 pt-[15px] pb-2.5">
              <div className="flex items-center gap-3">
                {/*
                  Left: bold current bid + meta row (time + bid count).
                  Title sits above on its own line, larger, so it remains
                  readable during fast scroll. Bold price leads the eye.
                */}
                <div className="flex-1 min-w-0">
                  <h1
                    className="font-serif text-[17px] leading-tight truncate text-[hsl(var(--ink))]"
                    data-testid="sticky-title"
                  >
                    {a.title}
                  </h1>
                  <div className="mt-1.5 flex items-center gap-2.5 text-[hsl(var(--ink-muted))]">
                    <span
                      className="font-mono font-bold tabular-nums whitespace-nowrap text-[18px] text-[hsl(var(--ink))]"
                      data-testid="sticky-bid"
                    >
                      {formatEUR(vatRate > 0 ? currentBidGross : a.current_bid_eur)}
                    </span>
                    <span className="text-[hsl(var(--line))]">·</span>
                    <span
                      className="font-mono tabular-nums whitespace-nowrap text-[15px]"
                      data-testid="sticky-time"
                    >
                      {formatTimeLeft(tl, t) || "—"}
                    </span>
                    <span className="text-[hsl(var(--line))]">·</span>
                    <span
                      className="flex items-center gap-1 whitespace-nowrap text-[15px]"
                      data-testid="sticky-bid-count"
                    >
                      <Gavel size={14} /> {a.bid_count || 0}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={toggleWatch}
                  aria-label={watching ? t("auction.watchlist_remove") : t("auction.watchlist_add")}
                  className={`shrink-0 h-10 w-10 rounded-full border flex items-center justify-center transition ${
                    watching
                      ? "border-[hsl(var(--accent))] text-[hsl(var(--accent))]"
                      : "border-[hsl(var(--line))] text-[hsl(var(--ink-muted))]"
                  }`}
                  data-testid="sticky-watch-button"
                >
                  <Heart size={18} className={watching ? "fill-current" : ""} />
                </button>
                {isLive ? (
                  <button
                    type="button"
                    onClick={() => {
                      const el = document.querySelector('[data-testid="place-bid-button"]');
                      if (el) {
                        el.scrollIntoView({ behavior: "smooth", block: "center" });
                        setTimeout(() => {
                          const input = document.querySelector('[data-testid="bid-amount-input"]');
                          if (input) input.focus();
                        }, 400);
                      }
                    }}
                    className="shrink-0 btn btn-accent !px-5 !py-2.5 !text-sm"
                    data-testid="sticky-bid-button"
                  >
                    {t("auction.place_bid", "Наддавай")}
                  </button>
                ) : (
                  <span className="shrink-0 text-[12px] uppercase tracking-wider text-[hsl(var(--ink-muted))] px-2">
                    {a.status === "sold" ? t("auction.sold", "Продаден") : t("auction.ended", "Завършил")}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
      {/* Account-level top-up modal — replaces the old per-auction
          BiddingCreditModal. Opens when the user tries to bid without
          enough credit in their universal pool. The shortfall is
          pre-filled as the suggested top-up amount. */}
      {showCredit && a && (
        <TopUpCreditModal
          suggestedAmount={(() => {
            const typed = Number(bidAmount);
            const net = typed && vatRate > 0 ? Math.round(typed / (1 + vatRate / 100)) : typed;
            const myCurrent = a.high_bidder_id === user?.id ? Number(a.current_bid_eur || 0) : 0;
            const delta = Math.max(0, (net || 0) - myCurrent);
            const avail = Number(accountCredit?.total_available_eur || 0);
            const shortfall = Math.max(1000, delta - avail);
            // Round up to nearest €1k for a cleaner default.
            return Math.ceil(shortfall / 1000) * 1000;
          })()}
          onClose={() => setShowCredit(false)}
        />
      )}

      {showBidConfirm && a && pendingBid && (
        <BidConfirmModal
          amountGross={pendingBid.gross}
          amountNet={pendingBid.net}
          vatRate={vatRate}
          stepEur={bidStepFor(a.current_bid_eur)}
          minNet={nextBid.min_next_eur || (Math.floor(a.current_bid_eur) + bidStepFor(a.current_bid_eur))}
          accountCredit={accountCredit}
          currentLeadByMe={a.high_bidder_id === user?.id ? Number(a.current_bid_eur || 0) : 0}
          onConfirm={(netAmount) => confirmBid(netAmount)}
          onTopUp={() => {
            setShowBidConfirm(false);
            setShowCredit(true);
          }}
          onClose={() => setShowBidConfirm(false)}
        />
      )}

      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-8">
        <Link to="/auctions" className="inline-flex items-center gap-2 text-sm text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]">
          <ArrowLeft size={14} /> {t("auction.back_to_auctions")}
        </Link>

        <div className="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
          <div className="lg:col-span-8">
            <div className="overline text-[hsl(var(--accent))]">{a.make} · {translateEnum(a.body_type, "body_type", lng)}</div>
            <h1 ref={titleRef} className="hidden lg:block font-serif text-3xl lg:text-5xl mt-3 tracking-tight leading-tight">{a.title}</h1>
            <div className="mt-3 text-sm text-[hsl(var(--ink-muted))] flex items-center gap-4 flex-wrap">
              <span>{a.year} · {formatKM(a.mileage_km)} · {translateEnum(a.fuel, "fuel", lng)} · {translateEnum(a.city, "city", lng)}{a.country ? `, ${a.country}` : ""}</span>
            </div>

            {/*
              Gallery layout:
              - Mobile: main photo 4:3 + 5-thumb strip below (unchanged).
              - Desktop: outer grid with explicit `aspectRatio: '9/5'` so the
                container height is deterministic. Main photo (5fr) gets an
                aspect of 3:2 which naturally fills 9/5 × 5/6 = 3/2 ✓ and
                the thumb column (1fr) splits that height into 5 equal
                `flex-1` rows. No circular sizing / no flex-stretch bugs.
            */}
            <div
              className="mt-8 lg:grid lg:grid-cols-[5fr_1fr] lg:gap-3"
              style={{ aspectRatio: "unset" }}
              ref={(el) => {
                // Inline-style aspect-ratio only on desktop. We can't use a
                // media query inside inline style, so set via JS ref callback.
                if (el && typeof window !== "undefined") {
                  const apply = () => {
                    if (window.matchMedia("(min-width: 1024px)").matches) {
                      // 5fr main photo × 3:2 aspect → container aspect = 9/5.
                      el.style.aspectRatio = "9 / 5";
                    } else {
                      el.style.aspectRatio = "unset";
                    }
                  };
                  apply();
                  // Re-apply on resize — lightweight, runs on rAF throttle.
                  if (!el._abResizeListener) {
                    el._abResizeListener = () => requestAnimationFrame(apply);
                    window.addEventListener("resize", el._abResizeListener);
                  }
                }
              }}
            >
              <div
                ref={mainImageRef}
                className="aspect-[4/3] lg:aspect-[3/2] border border-[hsl(var(--line))] rounded-card overflow-hidden bg-[hsl(var(--surface))] cursor-zoom-in relative group select-none"
                onClick={() => {
                  if (swipeRef.current?.cancelClick) return; // swipe consumed the gesture
                  setLightboxIdx(photoIdx);
                }}
                style={{ touchAction: "pan-y" }}
                data-testid="main-gallery-image"
              >
                <Picture
                  variant={a.images_variants?.[photoIdx]}
                  fallbackSrc={a.images?.[photoIdx] || a.thumbnails?.[photoIdx]}
                  size="gallery"
                  alt={a.title}
                  className="w-full h-full object-cover transition group-hover:scale-[1.02]"
                  priority
                />
                {a.images?.length > 0 && (
                  <div className="absolute bottom-3 right-3 px-2.5 py-1 rounded-full bg-black/55 text-white text-xs font-mono opacity-0 group-hover:opacity-100 transition pointer-events-none">
                    {photoIdx + 1} / {a.images.length} · {t("common.zoom")}
                  </div>
                )}
              </div>
              {a.images?.length > 1 && (() => {
                const total = a.images.length;
                const MOBILE_MAX = 5;
                const DESKTOP_MAX = 5;
                const mobileExtra = total - MOBILE_MAX;
                const desktopExtra = total - DESKTOP_MAX;
                return (
                  <div className="mt-3 lg:mt-0 grid grid-cols-5 gap-2 lg:flex lg:flex-col lg:gap-2 lg:h-full lg:min-h-0">
                    {a.images.map((img, i) => {
                      const hideOnMobile = i >= MOBILE_MAX;
                      const hideOnDesktop = i >= DESKTOP_MAX;
                      const isMobileLastVisible = i === MOBILE_MAX - 1 && mobileExtra > 0;
                      const isDesktopLastVisible = i === DESKTOP_MAX - 1 && desktopExtra > 0;
                      const onThumbClick = () => {
                        const isDesktopVp = typeof window !== "undefined" && window.matchMedia && window.matchMedia("(min-width: 768px)").matches;
                        if (isDesktopVp ? isDesktopLastVisible : isMobileLastVisible) {
                          setLightboxIdx(i);
                        } else {
                          setPhotoIdx(i);
                        }
                      };
                      // Small thumbs render at ~100 px — use the 400 px
                      // pre-generated thumbnail (browser downscales) instead
                      // of the full 1920 px original. Hidden thumbs past
                      // position 5 keep `loading="lazy"` so they don't fetch
                      // unless they scroll into view (they don't on desktop —
                      // the rest live in the lightbox).
                      const thumbSrc = a.thumbnails?.[i] || img;
                      return (
                        <button
                          key={i}
                          onClick={onThumbClick}
                          className={`relative aspect-[4/3] lg:aspect-auto lg:flex-1 lg:min-h-0 w-full rounded-card border overflow-hidden ${
                            photoIdx === i ? "border-[hsl(var(--ink))]" : "border-[hsl(var(--line))]"
                          } ${hideOnMobile && hideOnDesktop ? "hidden" : hideOnMobile ? "hidden md:block" : hideOnDesktop ? "block md:hidden" : ""}`}
                          data-testid={`thumb-${i}`}
                        >
                          <Picture
                            variant={a.images_variants?.[i]}
                            fallbackSrc={thumbSrc}
                            size="thumb"
                            alt={`${a.title} — ${t("auction.photo", "снимка")} ${i + 1}`}
                            className="w-full h-full object-cover"
                          />
                          {isMobileLastVisible && (
                            <span
                              className="md:hidden absolute inset-0 bg-black/65 hover:bg-black/75 transition-colors flex items-center justify-center text-white font-serif text-lg cursor-zoom-in"
                              data-testid="thumb-more-overlay-mobile"
                            >
                              +{mobileExtra}
                            </span>
                          )}
                          {isDesktopLastVisible && (
                            <span
                              className="hidden md:flex absolute inset-0 bg-black/65 hover:bg-black/75 transition-colors items-center justify-center text-white font-serif text-lg cursor-zoom-in"
                              data-testid="thumb-more-overlay-desktop"
                            >
                              +{desktopExtra}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                );
              })()}
            </div>

            <div className="mt-10">
              <div className="overline text-[hsl(var(--ink-muted))]">{t("auction.specs_overline")}</div>
              <div className="mt-4 rounded-card border border-[hsl(var(--line))] grid grid-cols-2 md:grid-cols-4 overflow-hidden">
                {specs.map((s, i) => (
                  <div key={i} className="p-5 border-r border-b border-[hsl(var(--line))] last:border-r-0 [&:nth-child(4n)]:border-r-0 [&:nth-last-child(-n+4)]:border-b-0">
                    <s.i size={15} className="text-[hsl(var(--ink-muted))]" />
                    <div className="overline text-[hsl(var(--ink-muted))] mt-2">{s.l}</div>
                    <div className="mt-1 text-sm">{s.v}</div>
                  </div>
                ))}
              </div>
              {a.vin && (
                <div className="mt-4 rounded-card border border-[hsl(var(--line))] p-5 flex items-center justify-between gap-3 flex-wrap" data-testid="vin-block">
                  <div>
                    <div className="overline text-[hsl(var(--ink-muted))] flex items-center gap-1.5">
                      <Shield size={12} /> {t("auction.vin_number")}
                    </div>
                    <div className="flex items-center gap-3 mt-1 flex-wrap">
                      <div className="font-mono text-lg tracking-wider" data-testid="vin-value">{a.vin}</div>
                      {/* CarVertical affiliate check — placeholder URL
                          until the affiliate code is provided. Swap the
                          `AFFILIATE_CODE` segment once we have it; the
                          query structure below matches CarVertical's
                          public affiliate link format. */}
                      <a
                        href={`https://www.carvertical.com/bg/?a=AFFILIATE_CODE&vin=${encodeURIComponent(a.vin)}`}
                        target="_blank"
                        rel="noopener noreferrer sponsored"
                        className="btn btn-secondary !py-1.5 !px-3 text-xs inline-flex items-center gap-1.5"
                        data-testid="carvertical-check-btn"
                        title={t("auction.carvertical_hint", "Провери историята на автомобила в CarVertical")}
                      >
                        <Shield size={12} /> {t("auction.carvertical_check", "Провери в CarVertical")}
                      </a>
                    </div>
                    {vinMsg && <div className="text-xs text-[hsl(var(--accent))] mt-2" data-testid="vin-request-msg">{vinMsg}</div>}
                    {vinErr && <div className="text-xs text-[hsl(var(--danger))] mt-2" data-testid="vin-request-err">{vinErr}</div>}
                  </div>
                  {a.vin_masked ? (
                    <div className="flex items-center gap-3 flex-wrap">
                      {user && isLive && (
                        <button
                          onClick={requestVin}
                          disabled={vinRequesting || !!vinMsg}
                          className="btn btn-secondary !py-2 !px-4 text-xs flex items-center gap-2 disabled:opacity-50"
                          data-testid="request-vin-btn"
                        >
                          <Shield size={12} /> {vinRequesting ? t("auction.vin_sending") : t("auction.vin_request_cta")}
                        </button>
                      )}
                      <p className="text-xs text-[hsl(var(--ink-muted))] max-w-[220px]" data-testid="vin-masked-note">
                        {!user
                          ? t("auction.vin_masked_note_anon")
                          : isLive
                            ? t("auction.vin_masked_note_live")
                            : t("auction.vin_masked_note_ended")}
                      </p>
                    </div>
                  ) : (
                    <span className="pill pill-live" data-testid="vin-unmasked-badge">{t("auction.vin_unmasked")}</span>
                  )}
                </div>
              )}
            </div>

            <div className="mt-10">
              <div className="overline text-[hsl(var(--ink-muted))]">{t("auction.editorial_description")}</div>
              <h2 className="sr-only">{t("auction.editorial_description")} — {a.title}</h2>
              <DescriptionWithInteriorShots
                auctionId={id}
                auctionTitle={a.title}
                description={a.description}
                interiorImages={a.images_interior || []}
                interiorThumbnails={(() => {
                  // Interior lives at the tail of the merged `images` /
                  // `thumbnails` arrays (order = exterior + bumper + wheels +
                  // interior). Slice the 400 px thumbnails for cheap
                  // inline display.
                  const exteriorLen = (a.images_exterior || []).length;
                  const bumperLen = (a.images_bumper || []).length;
                  const wheelsLen = (a.images_wheels || []).length;
                  const start = exteriorLen + bumperLen + wheelsLen;
                  return (a.thumbnails || []).slice(start);
                })()}
                interiorStartIdx={(a.images_exterior || []).length + (a.images_bumper || []).length + (a.images_wheels || []).length}
                onOpenLightbox={(idx) => setLightboxIdx(idx)}
                preTranslated={{ ro: a.description_ro || "", en: a.description_en || "" }}
              />
            </div>

            {a.video_url && (
              <div className="mt-10" data-testid="auction-video-section">
                <div className="overline text-[hsl(var(--ink-muted))]">{t("auction.video_section", "Видео на колата")}</div>
                <h2 className="sr-only">{t("auction.video_section", "Видео на колата")} — {a.title}</h2>
                <div className="mt-3 max-w-3xl">
                  <AuctionVideo
                    src={a.video_url.startsWith("http") ? a.video_url : `${API_BASE}${a.video_url}`}
                    srcAv1={a.video_url_av1 ? (a.video_url_av1.startsWith("http") ? a.video_url_av1 : `${API_BASE}${a.video_url_av1}`) : null}
                    poster={a.video_poster_url ? (a.video_poster_url.startsWith("http") ? a.video_poster_url : `${API_BASE}${a.video_poster_url}`) : null}
                    duration={a.video_duration_seconds}
                  />
                </div>
              </div>
            )}

            {a.status === "reserve_not_met" && (
              <NegotiationPortal auctionId={id} auction={a} />
            )}

            <div className="mt-14">
              <div className="overline text-[hsl(var(--accent))]">{t("auction.bids_history_overline")}</div>
              <h2 className="font-serif text-2xl lg:text-3xl mt-2">{t("auction.bids_history_title")} ({bids.length})</h2>
              <div className="mt-6 rounded-card border border-[hsl(var(--line))] overflow-hidden">
                {bids.length === 0 ? (
                  <p className="p-6 text-sm text-[hsl(var(--ink-muted))]">{t("auction.no_bids_yet")}</p>
                ) : (
                  bids.map((b) => (
                    <div key={b.id} className="flex items-center justify-between p-4 border-b border-[hsl(var(--line))] last:border-b-0" data-testid={`bid-row-${b.id}`}>
                      <div>
                        {b.user_id ? (
                          <Link to={`/profile/${b.user_slug || b.user_id}`} className="text-sm font-semibold hover:text-[hsl(var(--accent))]" data-testid={`bidder-link-${b.id}`}>{b.user_name}</Link>
                        ) : (
                          <div className="text-sm font-semibold">{b.user_name}</div>
                        )}
                        <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">
                          {new Date(b.created_at).toLocaleString(intlLocale(i18n.language))}
                          {b.preauth_status === "authorized" && <span className="ml-2 text-[hsl(var(--accent))]">· {t("auction.preauth_active")}</span>}
                        </div>
                      </div>
                      <div className="font-serif text-xl">{formatEUR(b.amount_eur)}</div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="mt-14">
              <div className="overline text-[hsl(var(--accent))]">{t("auction.comments_overline")}</div>
              <h2 className="font-serif text-2xl lg:text-3xl mt-2 flex items-center gap-3">
                <MessageCircle size={22} /> {t("auction.comments_title")} ({comments.length})
              </h2>
              <div className="mt-5 rounded-card border border-[hsl(var(--line))] p-4">
                <textarea
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  placeholder={user ? t("auction.comments_placeholder") : t("auction.comments_placeholder_logged_out")}
                  disabled={!user}
                  rows={3}
                  className="w-full border border-[hsl(var(--line))] p-3 text-sm resize-none"
                  data-testid="comment-input"
                />
                <div className="mt-3 flex justify-end">
                  <button onClick={postComment} disabled={!user || !commentText.trim()} className="btn btn-primary disabled:opacity-40" data-testid="submit-comment">
                    {t("auction.comments_submit")}
                  </button>
                </div>
              </div>

              <div className="mt-6 space-y-5">
                {comments.map((c) => (
                  <CommentItem
                    key={c.id}
                    c={c}
                    t={t}
                    i18nLang={i18n.language}
                    isAdmin={isAdmin}
                    onDelete={() => deleteComment(c.id)}
                  />
                ))}
              </div>
            </div>
          </div>

          <aside className="lg:col-span-4">
            <div className="lg:sticky lg:top-[72px] space-y-5">
              <div className="rounded-card border border-[hsl(var(--line))] p-6 bg-white" data-testid="bid-section">
                {hasPendingCounterForMe && (
                  <div className="mb-5 rounded-card bg-[hsl(var(--accent-soft))] border border-[hsl(var(--accent))]/30 p-4" data-testid="counter-banner">
                    <div className="overline text-[hsl(var(--accent))]">{t("auction.counter_offer_overline")}</div>
                    <div className="font-serif text-3xl mt-2">{formatEUR(a.counter_offer_eur)}</div>
                    <p className="mt-2 text-xs text-[hsl(var(--ink-muted))]">{t("auction.counter_offer_text")}</p>
                    <div className="mt-3 flex gap-2">
                      <button onClick={() => respondCounter(true)} className="btn btn-accent !py-2 !px-4 text-xs flex-1" data-testid="counter-accept">Приеми</button>
                      <button onClick={() => respondCounter(false)} className="btn btn-secondary !py-2 !px-4 text-xs flex-1" data-testid="counter-decline">Откажи</button>
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-between flex-wrap gap-2">
                  {a.status === "sold" ? <span className="pill pill-sold">{t("auction.status_sold", "Продаден")}</span>
                    : a.status === "ended" ? <span className="pill pill-sold">{t("auction.status_ended", "Приключил")}</span>
                    : tl.urgent ? <span className="pill pill-ending">{formatTimeLeft(tl, t)}</span>
                    : <span className="pill pill-live">{formatTimeLeft(tl, t)}</span>}
                  {a.has_reserve && <span className="pill" data-testid="with-reserve">{t("auction.with_reserve")}</span>}
                  {a.has_reserve === false && <span className="pill no-reserve-gradient" data-testid="no-reserve">{t("auction.no_reserve_badge")}</span>}
                  {a.vat_status === "vat_inclusive" ? (
                    <span className="pill" data-testid="vat-inclusive" style={{ background: "hsl(var(--accent-soft))", color: "hsl(var(--accent-ink))", borderColor: "hsl(var(--accent))" }}>
                      {t("auction.vat_inclusive_badge", "С ДДС {{rate}}%", { rate: vatRate })}
                    </span>
                  ) : a.vat_status === "exempt" ? (
                    <span className="pill" data-testid="vat-exempt">
                      {t("auction.vat_exempt_badge", "Освободена от ДДС")}
                    </span>
                  ) : null}
                  <span className="overline text-[hsl(var(--ink-muted))] ml-auto">{a.bid_count || 0} {t("auction.bids_word")}</span>
                </div>

                <div className="mt-6">
                  <div className="overline text-[hsl(var(--ink-muted))]">{a.status === "sold" ? t("auction.sold_for") : t("auction.current_bid_label")}</div>
                  <div className="font-serif text-5xl mt-2 flex items-baseline gap-2 flex-wrap" data-testid="current-bid">
                    {formatEUR(vatRate > 0 ? currentBidGross : a.current_bid_eur)}
                    {vatRate > 0 && (
                      <span className="text-[11px] uppercase tracking-wider text-[hsl(var(--ink-muted))] font-sans font-semibold">
                        {t("auction.incl_vat", "вкл. ДДС")} {vatRate}%
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-[hsl(var(--ink-muted))] font-mono mt-1">{formatLocal(vatRate > 0 ? currentBidGross : a.current_bid_eur, i18n.language)}</div>
                  {vatRate > 0 && (
                    <div className="mt-2 text-xs text-[hsl(var(--ink-muted))]" data-testid="vat-net-block">
                      {t("auction.without_vat_label", "Без ДДС")}: <span className="font-mono text-[hsl(var(--ink))]">{formatEUR(a.current_bid_eur)}</span>
                    </div>
                  )}
                  {a.high_bidder_name && (
                    <div className="mt-2 text-xs text-[hsl(var(--ink-muted))]">{t("auction.leading_bidder")}: <span className="text-[hsl(var(--ink))]">{a.high_bidder_name}</span></div>
                  )}
                  {a.has_reserve && a.status === "reserve_not_met" && (
                    <div className="mt-3 text-xs text-[hsl(var(--ink-muted))] flex items-center gap-1.5" data-testid="reserve-not-met">
                      <span className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--ink-muted))]"></span>
                      {t("auction.reserve_not_met")}
                    </div>
                  )}
                  {a.has_reserve && a.reserve_met === true && (a.status === "sold" || a.status === "ended") && (
                    <div className="mt-3 text-xs text-[hsl(var(--accent))] flex items-center gap-1.5" data-testid="reserve-reached">
                      <span className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--accent))]"></span>
                      {t("auction.reserve_met_long")}
                    </div>
                  )}
                </div>

                {isLive && (
                  <div className="mt-6 rule-t pt-5">
                    <label className="overline text-[hsl(var(--ink-muted))] block mb-2">
                      {vatRate > 0
                        ? t("auction.your_bid_eur_gross", "Вашето наддаване (EUR, вкл. ДДС {{rate}}%)", { rate: vatRate })
                        : t("auction.your_bid_eur")}
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        min={vatRate > 0 ? Math.ceil(Number(nextBid.min_next_eur || 0) * (1 + vatRate / 100)) : nextBid.min_next_eur}
                        step={vatRate > 0 ? Math.max(1, Math.round(Number(nextBid.step_eur || 0) * (1 + vatRate / 100))) : nextBid.step_eur}
                        value={bidAmount}
                        onChange={(e) => setBidAmount(e.target.value)}
                        className="flex-1 border border-[hsl(var(--line))] h-12 px-3 text-base"
                        data-testid="bid-amount-input"
                      />
                      <button onClick={startBid} disabled={placing} className="btn btn-accent !px-6" data-testid="place-bid-button">
                        {placing ? "…" : t("auction.place_bid")}
                      </button>
                    </div>
                    {vatRate > 0 && Number(bidAmount) > 0 && (
                      <div className="mt-2 flex items-baseline gap-2 px-1" data-testid="bid-net-preview">
                        <span className="text-xs text-[hsl(var(--ink-muted))]">{t("auction.without_vat_label", "Без ДДС")}:</span>
                        <span className="font-mono text-sm text-[hsl(var(--ink))]">{formatEUR(Math.round(Number(bidAmount) / (1 + vatRate / 100)))}</span>
                      </div>
                    )}
                    <p className="text-xs text-[hsl(var(--ink-muted))] mt-2">{t("auction.min_next_bid", {
                      min: (vatRate > 0 ? Math.ceil(Number(nextBid.min_next_eur || 0) * (1 + vatRate / 100)) : Number(nextBid.min_next_eur || 0)).toLocaleString(intlLocale(i18n.language)),
                      step: (vatRate > 0 ? Math.round(Number(nextBid.step_eur || 0) * (1 + vatRate / 100)) : Number(nextBid.step_eur || 0)).toLocaleString(intlLocale(i18n.language)),
                    })}</p>

                    <div className="mt-4 p-3 rounded-card bg-[hsl(var(--accent-soft))] border border-[hsl(var(--accent))]/20 flex items-start gap-2">
                      <Shield size={14} className="text-[hsl(var(--accent))] shrink-0 mt-0.5" />
                      <div className="text-xs leading-relaxed">
                        <div className="font-semibold text-[hsl(var(--accent-ink))]">{t("auction.buyer_fee_label")} {formatEUR(preauthPreview)}</div>
                        <div className="text-[hsl(var(--ink-muted))] mt-0.5">{t("auction.buyer_fee_detail", { pct: settings.buyer_fee_pct, min: settings.buyer_fee_min_eur, max: settings.buyer_fee_max_eur })}</div>
                      </div>
                    </div>

                    {/* Account-level credit pitch.
                        Account credit is universal — the user tops up
                        once and bids on any auction. We show one of:
                          • A compact "У вас има €X на разположение"
                            badge when they have enough credit for the
                            typed bid,
                          • "Заредете още" prompt when the typed bid
                            exceeds available credit,
                          • A subtle pitch to top-up when no credit is
                            yet authorized. */}
                    {user && (() => {
                      const typedNet = (() => {
                        const v = Number(bidAmount);
                        if (!v) return 0;
                        return vatRate > 0 ? Math.round(v / (1 + vatRate / 100)) : v;
                      })();
                      const myCurrent = a.high_bidder_id === user?.id ? Number(a.current_bid_eur || 0) : 0;
                      const delta = Math.max(0, typedNet - myCurrent);
                      const available = Number(accountCredit?.total_available_eur || 0);
                      const limit = Number(accountCredit?.total_limit_eur || 0);
                      const needsTopUp = typedNet > 0 && delta > available + 0.5;

                      if (limit === 0) {
                        return (
                          <button
                            onClick={() => setShowCredit(true)}
                            className="mt-3 w-full rounded-card border border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent-soft))]/60 hover:bg-[hsl(var(--accent-soft))] p-3 text-left transition"
                            data-testid="credit-pitch"
                          >
                            <div className="flex items-center gap-2 text-xs">
                              <Zap size={13} className="text-[hsl(var(--accent))] shrink-0" />
                              <div>
                                <div className="font-semibold text-[hsl(var(--accent))]">
                                  {t("auction.credit_pitch_title", "Заредете наддавателен кредит")}
                                </div>
                                <div className="text-[hsl(var(--ink-muted))] mt-0.5">
                                  {t("auction.credit_pitch_body", "Универсален — работи на всеки търг.")}
                                </div>
                              </div>
                            </div>
                          </button>
                        );
                      }
                      if (needsTopUp) {
                        return (
                          <button
                            onClick={() => setShowCredit(true)}
                            className="mt-3 w-full rounded-card border border-amber-400/50 bg-amber-50/70 hover:bg-amber-50 p-3 text-left transition"
                            data-testid="credit-increase-prompt"
                          >
                            <div className="flex items-center gap-2 text-xs">
                              <TrendingUp size={13} className="text-amber-700 shrink-0" />
                              <div>
                                <div className="font-semibold text-amber-800">
                                  {t("auction.credit_topup_needed", "Недостатъчен кредит — заредете още")}
                                </div>
                                <div className="text-[hsl(var(--ink-muted))] mt-0.5">
                                  {t("auction.credit_topup_body", "Налично {{avail}} → Вашето наддаване иска {{need}}. Кликнете да заредите.", {
                                    avail: formatEUR(available),
                                    need: formatEUR(delta),
                                  })}
                                </div>
                              </div>
                            </div>
                          </button>
                        );
                      }
                      // Has credit and it covers — show a discreet badge.
                      return (
                        <div className="mt-3 p-2.5 rounded-card bg-[hsl(var(--accent-soft))]/40 border border-[hsl(var(--accent))]/20 text-xs flex items-center justify-between" data-testid="credit-active-badge">
                          <div className="flex items-center gap-1.5 text-[hsl(var(--accent))]">
                            <Zap size={12} />
                            <span className="font-semibold">
                              {t("auction.credit_available_short", "Налично")}: {formatEUR(available)} / {formatEUR(limit)}
                            </span>
                          </div>
                          <button
                            onClick={() => setShowCredit(true)}
                            className="text-xs font-semibold text-[hsl(var(--accent))] hover:underline"
                            data-testid="credit-manage-btn"
                          >
                            {t("auction.credit_topup_short", "Зареди още")}
                          </button>
                        </div>
                      );
                    })()}

                    {error && <p className="text-xs text-[hsl(var(--danger))] mt-2" data-testid="bid-error">{error}</p>}
                  </div>
                )}

                {/* Buy now — instant purchase at the seller's "Купи сега" price */}
                {isLive && a.buy_now_eur && Number(a.buy_now_eur) > 0 && Number(a.current_bid_eur || 0) <= Number(a.buy_now_eur) && (
                  <div className="mt-5 rounded-card border-2 border-[hsl(var(--accent))] bg-[hsl(var(--accent-soft))]/40 p-4" data-testid="buy-now-block">
                    <div className="flex items-center gap-2 mb-2">
                      <Zap size={16} className="text-[hsl(var(--accent))]" />
                      <span className="overline text-[hsl(var(--accent-ink))] font-semibold">{t("auction.buy_now_title", "Купи сега")}</span>
                    </div>
                    <div className="font-serif text-3xl text-[hsl(var(--ink))] flex items-baseline gap-2 flex-wrap" data-testid="buy-now-price">
                      {formatEUR(vatRate > 0 ? grossOf(a.buy_now_eur) : a.buy_now_eur)}
                      {vatRate > 0 && (
                        <span className="text-[10px] uppercase tracking-wider text-[hsl(var(--ink-muted))] font-sans font-semibold">
                          {t("auction.incl_vat", "вкл. ДДС")} {vatRate}%
                        </span>
                      )}
                    </div>
                    {vatRate > 0 && (
                      <div className="text-xs text-[hsl(var(--ink-muted))] font-mono mt-0.5">
                        {t("auction.without_vat_label", "Без ДДС")}: <span className="text-[hsl(var(--ink))]">{formatEUR(a.buy_now_eur)}</span>
                      </div>
                    )}
                    {(() => {
                      const grossPrice = vatRate > 0 ? grossOf(a.buy_now_eur) : Number(a.buy_now_eur || 0);
                      const buyNowFee = buyerFeeFor(grossPrice);
                      return buyNowFee > 0 && (
                        <div className="mt-2 text-xs text-[hsl(var(--ink-muted))]" data-testid="buy-now-fee-preview">
                          <div>
                            {t("auction.buy_now_charge_label", "Stripe ще таксува само комисионна:")}{" "}
                            <span className="font-mono text-[hsl(var(--ink))] font-semibold">{formatEUR(buyNowFee)}</span>
                            <span className="ml-1">({settings.buyer_fee_pct}%)</span>
                          </div>
                          <div className="mt-0.5">
                            {t("auction.buy_now_settle_offline", "Остатъкът се урежда директно с продавача.")}
                          </div>
                        </div>
                      );
                    })()}
                    <button
                      onClick={onBuyNow}
                      disabled={!user || buyingNow}
                      className="mt-3 w-full btn btn-primary !bg-[hsl(var(--accent))] !text-white !border-transparent hover:!bg-[hsl(var(--accent))]/85 disabled:opacity-50 flex items-center justify-center gap-2"
                      data-testid="buy-now-btn"
                    >
                      <Zap size={14} />
                      {buyingNow ? t("auction.buy_now_processing", "Обработваме…") : !user ? t("auction.login_to_buy", "Влез, за да купиш") : t("auction.buy_now_action", "Купи сега за {{price}}", { price: formatEUR(vatRate > 0 ? grossOf(a.buy_now_eur) : a.buy_now_eur) })}
                    </button>
                  </div>
                )}

                <button onClick={toggleWatch} className={`mt-5 w-full btn flex items-center justify-center gap-2 ${watching ? "btn-primary" : "btn-secondary"}`} data-testid="watch-button">
                  <Heart size={14} className={watching ? "fill-current" : ""} /> {watching ? t("auction.watchlist_remove") : t("auction.watchlist_add")}
                </button>
                <ShareButton auction={a} />
              </div>

              <div className="rounded-card border border-[hsl(var(--line))] p-6 bg-[hsl(var(--surface))]">
                <div className="overline text-[hsl(var(--ink-muted))]">{t("auction.seller")}</div>
                {a.seller_id && a.seller_id !== "platform" ? (
                  <div className="mt-2 flex items-center gap-3">
                    <Avatar
                      url={a.seller_avatar_url}
                      name={a.seller_name}
                      size={44}
                      testId="seller-avatar"
                    />
                    <h2 className="font-serif text-xl">
                      <Link to={`/profile/${a.seller_slug || a.seller_id}`} className="block hover:text-[hsl(var(--accent))]" data-testid="seller-link">{a.seller_name}</Link>
                    </h2>
                  </div>
                ) : (
                  <div className="mt-2 flex items-center gap-3">
                    <Avatar url={a.seller_avatar_url} name={a.seller_name} size={44} />
                    <h2 className="font-serif text-xl">{a.seller_name}</h2>
                  </div>
                )}
                <p className="text-xs text-[hsl(var(--ink-muted))] mt-2" data-testid="seller-badge">
                  {a.seller_is_verified_dealer ? t("auction.verified_dealer") : t("auction.private_person", "Частно лице")} · {translateEnum(a.city, "city", i18n.language)}{a.country ? `, ${a.country}` : ""}
                </p>
              </div>
            </div>
          </aside>
        </div>
      </div>

      {related.length > 0 && (
        <section className="rule-t bg-[hsl(var(--surface))]" data-testid="related-section">
          <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
            <div className="flex items-end justify-between gap-6 flex-wrap">
              <div>
                <div className="overline text-[hsl(var(--accent))]">{t("auction.also_see")}</div>
                <h2 className="font-serif text-3xl lg:text-4xl mt-2 tracking-tight">{t("auction.similar_listings")}</h2>
              </div>
              <Link to="/auctions" className="text-sm font-semibold text-[hsl(var(--accent))] hover:underline">
                {t("auction.view_all_auctions")} →
              </Link>
            </div>
            <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {related.map((r) => (
                <AuctionCard key={r.id} auction={r} />
              ))}
            </div>
          </div>
        </section>
      )}

      {lightboxIdx !== null && (
        <Lightbox
          images={a.images || []}
          thumbnails={a.thumbnails || []}
          index={lightboxIdx}
          onClose={() => setLightboxIdx(null)}
          onChange={(i) => { setLightboxIdx(i); setPhotoIdx(i); }}
        />
      )}
    </main>
  );
}

function DescriptionWithInteriorShots({ auctionId, auctionTitle = "", description, interiorImages, interiorThumbnails = [], interiorStartIdx = 0, onOpenLightbox, preTranslated = {} }) {
  const { t, i18n } = useTranslation();
  const lang = (i18n.language || "bg").slice(0, 2);
  const needsTranslation = lang !== "bg" && !!(description || "").trim();
  // Show original when: BG, user clicked "show original", or we haven't yet fetched/have no translation.
  const [showOriginal, setShowOriginal] = React.useState(!needsTranslation);
  const [translated, setTranslated] = React.useState(preTranslated[lang] || "");
  const [loadingTrans, setLoadingTrans] = React.useState(false);
  const [transErr, setTransErr] = React.useState("");

  // Auto-fetch on language change if a cached translation is present on the auction doc
  React.useEffect(() => {
    setShowOriginal(!needsTranslation);
    setTranslated(preTranslated[lang] || "");
    setTransErr("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, auctionId]);

  const requestTranslation = async () => {
    if (!needsTranslation || translated) { setShowOriginal(false); return; }
    setLoadingTrans(true); setTransErr("");
    try {
      const { data } = await api.get(`/auctions/${auctionId}/translate-description`, { params: { lang } });
      setTranslated(data?.text || "");
      setShowOriginal(false);
    } catch (e) {
      setTransErr("AI translation temporarily unavailable — showing original.");
      setShowOriginal(true);
    } finally { setLoadingTrans(false); }
  };

  const displayText = (!showOriginal && translated) ? translated : (description || "");
  const text = displayText.trim();
  // Split description into exactly 3 chunks by sentence count.  Sentence
  // boundaries are stable across languages (AI translator preserves them),
  // so the image positions don't jump when the user toggles translation.
  const sentences = text.split(/(?<=[.!?])\s+/).filter(Boolean);
  let chunks;
  if (sentences.length >= 3) {
    const per = Math.ceil(sentences.length / 3);
    chunks = [
      sentences.slice(0, per).join(" "),
      sentences.slice(per, per * 2).join(" "),
      sentences.slice(per * 2).join(" "),
    ].filter(Boolean);
  } else {
    chunks = [text];
  }

  const allShots = interiorImages || [];
  const visibleShots = allShots.slice(0, 3);

  const translateControls = needsTranslation ? (
    <div className="flex items-center gap-3 flex-wrap mt-4 mb-1" data-testid="translate-controls">
      {translated ? (
        <>
          {showOriginal ? (
            <button
              onClick={() => setShowOriginal(false)}
              className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1.5"
              data-testid="translate-show-translated"
            >
              <Languages size={12} /> {t("auction.translate_to_current")}
            </button>
          ) : (
            <>
              <span className="pill text-xs text-[hsl(var(--accent))] border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent-soft))]" data-testid="translated-badge">
                <Languages size={11} /> {t("auction.translated_by_ai")}
              </span>
              <button
                onClick={() => setShowOriginal(true)}
                className="text-xs underline text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]"
                data-testid="translate-show-original"
              >
                {t("auction.show_original")}
              </button>
            </>
          )}
        </>
      ) : (
        <button
          onClick={requestTranslation}
          disabled={loadingTrans}
          className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1.5"
          data-testid="translate-fetch"
        >
          <Languages size={12} /> {loadingTrans ? t("auction.translating") : t("auction.translate_to_current")}
        </button>
      )}
      {transErr && <span className="text-xs text-[hsl(var(--danger))]">{transErr}</span>}
    </div>
  ) : null;

  const paraBlocks = chunks.map((p, i) => (
    <p key={i} className="text-[15px] leading-[1.7] whitespace-pre-wrap text-[hsl(var(--ink))]/90">{p}</p>
  ));

  if (visibleShots.length === 0) {
    return (
      <div className="max-w-3xl" data-testid="auction-description">
        {translateControls}
        <div className="mt-4 space-y-4">{paraBlocks}</div>
      </div>
    );
  }

  const blocks = [];
  chunks.forEach((p, i) => {
    blocks.push(
      <p key={`p-${i}`} className="text-[15px] leading-[1.7] whitespace-pre-wrap text-[hsl(var(--ink))]/90">{p}</p>
    );
    const shot = visibleShots[i];
    if (shot) {
      // Interior shots render up to 600-800 px wide on desktop and lazy-load
      // only when scrolled near. Use the full-resolution image so the photo
      // stays sharp; the lazy attribute still keeps the network footprint
      // small on initial paint.
      const thumbSrc = shot;
      const lightboxIdxForShot = interiorStartIdx + i;
      return blocks.push(
        <figure
          key={`s-${i}`}
          className="my-2 rounded-card overflow-hidden border border-[hsl(var(--line))] bg-[hsl(var(--surface))]"
        >
          <button
            type="button"
            onClick={() => onOpenLightbox && onOpenLightbox(lightboxIdxForShot)}
            className="block w-full cursor-zoom-in"
            data-testid={`interior-shot-btn-${i}`}
          >
            <img
              src={thumbSrc}
              alt={`${auctionTitle} — ${t("spec.interior", "интериор")} ${i + 1}`}
              loading="lazy"
              decoding="async"
              className="w-full h-auto object-cover max-h-[480px]"
              data-testid={`interior-shot-${i}`}
            />
          </button>
        </figure>
      );
    }
  });

  return (
    <div className="max-w-3xl" data-testid="auction-description">
      {translateControls}
      <div className="mt-4 space-y-4">{blocks}</div>
    </div>
  );
}


function CommentItem({ c, t, i18nLang, isAdmin, onDelete }) {
  const lang = (i18nLang || "bg").slice(0, 2);
  // If the comment ships with a pre-translated value for the current locale, use it
  const preTranslated = c[`text_${lang}`];
  const [translated, setTranslated] = React.useState(preTranslated || "");
  const [showOriginal, setShowOriginal] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState("");
  // Vote state: seed from server + update optimistically on click.
  // `viewerVote` tri-state: 1 upvoted, -1 downvoted, 0 no vote.
  const [vote, setVote] = React.useState({
    score: c.score ?? 0,
    viewerVote: c.viewer_vote ?? 0,
  });

  const castVote = async (dir) => {
    // Clicking an already-active button clears the vote, matching
    // Reddit's muscle memory and avoiding a dedicated "unvote" button.
    const next = vote.viewerVote === dir ? 0 : dir;
    const delta = next - vote.viewerVote;
    setVote((p) => ({ score: p.score + delta, viewerVote: next }));
    try {
      const { data } = await api.post(`/comments/${c.id}/vote`, { vote: next });
      setVote({ score: data.score, viewerVote: data.viewer_vote });
    } catch (e) {
      // Rollback on error
      setVote((p) => ({ score: p.score - delta, viewerVote: vote.viewerVote }));
      if (e?.response?.status === 401) {
        toast.error(t("comments.login_to_vote", "Влезте, за да гласувате."));
      }
    }
  };

  const source = c.text || "";
  // Heuristic: offer translation when viewer's UI language is not BG and the
  // raw text contains Cyrillic letters (assumed Bulgarian origin) or the other way around.
  const hasCyrillic = /[А-Яа-яЁё]/.test(source);
  const hasLatin = /[A-Za-z]/.test(source);
  const needsTranslation = !c.deleted && (
    (lang !== "bg" && hasCyrillic) ||
    (lang === "bg" && hasLatin && !hasCyrillic)
  );

  const runTranslate = async () => {
    if (translated) { setShowOriginal(false); return; }
    setLoading(true); setErr("");
    try {
      const { data } = await api.get(`/comments/${c.id}/translate`, { params: { lang } });
      setTranslated(data.text || "");
    } catch (e) {
      setErr(formatError(e));
    } finally { setLoading(false); }
  };

  const displayText = (!showOriginal && translated) ? translated : source;

  return (
    <div className={`rounded-card border border-[hsl(var(--line))] p-5 ${c.deleted ? "bg-[hsl(var(--surface))] opacity-70" : ""}`} data-testid={`comment-${c.id}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          {!c.deleted && (
            <Avatar url={c.user_avatar_url} name={c.user_name} size={28} testId={`comment-avatar-${c.id}`} />
          )}
          {c.user_id && !c.deleted ? (
            <Link to={`/profile/${c.user_slug || c.user_id}`} className="text-sm font-semibold hover:text-[hsl(var(--accent))]">{c.user_name}</Link>
          ) : (
            <div className="text-sm font-semibold">{c.deleted ? "—" : c.user_name}</div>
          )}
          {c.is_owner && !c.deleted && (
            <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[hsl(var(--accent))] text-white" data-testid={`comment-owner-badge-${c.id}`}>{t("auction.seller_short", "Продавач")}</span>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">{new Date(c.created_at).toLocaleString(intlLocale(i18nLang))}</div>
          {isAdmin && !c.deleted && (
            <button
              onClick={onDelete}
              className="text-xs text-[hsl(var(--danger))] hover:underline"
              data-testid={`admin-delete-comment-${c.id}`}
            >
              {t("auction.delete", "Изтрий")}
            </button>
          )}
        </div>
      </div>
      <p className={`mt-3 text-sm leading-relaxed ${c.deleted ? "italic text-[hsl(var(--ink-muted))]" : ""}`}>
        {c.deleted ? t("auction.comment_removed") : displayText}
      </p>
      {!c.deleted && (
        <div className="mt-3 flex items-center gap-1" data-testid={`comment-votes-${c.id}`}>
          <button
            onClick={() => castVote(1)}
            aria-label={t("comments.upvote", "Upvote")}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
              vote.viewerVote === 1
                ? "bg-[hsl(var(--accent))]/15 text-[hsl(var(--accent))]"
                : "text-[hsl(var(--ink-muted))] hover:bg-[hsl(var(--surface))] hover:text-[hsl(var(--ink))]"
            }`}
            data-testid={`comment-upvote-${c.id}`}
          >
            <ChevronUp size={18} strokeWidth={2.5} />
          </button>
          <span
            className={`min-w-[2ch] text-center text-sm font-semibold tabular-nums ${
              vote.score > 0
                ? "text-[hsl(var(--accent))]"
                : vote.score < 0
                  ? "text-[hsl(var(--danger))]"
                  : "text-[hsl(var(--ink-muted))]"
            }`}
            data-testid={`comment-score-${c.id}`}
          >
            {vote.score}
          </span>
          <button
            onClick={() => castVote(-1)}
            aria-label={t("comments.downvote", "Downvote")}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
              vote.viewerVote === -1
                ? "bg-[hsl(var(--danger))]/15 text-[hsl(var(--danger))]"
                : "text-[hsl(var(--ink-muted))] hover:bg-[hsl(var(--surface))] hover:text-[hsl(var(--ink))]"
            }`}
            data-testid={`comment-downvote-${c.id}`}
          >
            <ChevronDown size={18} strokeWidth={2.5} />
          </button>
        </div>
      )}
      {needsTranslation && (
        <div className="mt-3 flex items-center gap-2 flex-wrap text-xs" data-testid={`comment-translate-controls-${c.id}`}>
          {translated ? (
            showOriginal ? (
              <button onClick={() => setShowOriginal(false)} className="inline-flex items-center gap-1 text-[hsl(var(--accent))] hover:underline" data-testid={`comment-show-translated-${c.id}`}>
                <Languages size={11} /> {t("auction.translate_to_current")}
              </button>
            ) : (
              <>
                <span className="inline-flex items-center gap-1 text-[hsl(var(--accent))]" data-testid={`comment-translated-badge-${c.id}`}>
                  <Languages size={11} /> {t("auction.translated_by_ai")}
                </span>
                <button onClick={() => setShowOriginal(true)} className="text-[hsl(var(--ink-muted))] hover:underline" data-testid={`comment-show-original-${c.id}`}>
                  {t("auction.show_original")}
                </button>
              </>
            )
          ) : (
            <button onClick={runTranslate} disabled={loading} className="inline-flex items-center gap-1 text-[hsl(var(--accent))] hover:underline disabled:opacity-50" data-testid={`comment-translate-${c.id}`}>
              <Languages size={11} /> {loading ? t("auction.translating") : t("auction.translate_to_current")}
            </button>
          )}
          {err && <span className="text-[hsl(var(--danger))]">{err}</span>}
        </div>
      )}
    </div>
  );
}

function ShareButton({ auction }) {
  const { t, i18n } = useTranslation();
  const brand = brandNameForLang(i18n.resolvedLanguage || i18n.language);
  const [copied, setCopied] = React.useState(false);
  // Use the canonical SEO-friendly slug URL — `/auctions/<slug>-<short-id>`.
  // Social crawlers hitting this path are routed by the backend
  // `social_bot_share_middleware` to the OG-rich `/api/share/auction/{id}`
  // handler, so they still get the title + description + OG image; real
  // users get the React SPA. End URL stays clean and shareable.
  const shareUrl = `${window.location.origin}${auctionUrl(auction)}`;

  const share = async () => {
    const data = { title: auction?.title || brand, url: shareUrl };
    if (navigator.share) {
      try {
        await navigator.share(data);
      } catch (err) {
        // AbortError = user cancelled the native share sheet — DO
        // NOT fall through to clipboard / prompt (that's what was
        // surfacing the ugly `window.prompt` dialog after Cancel).
        // Any other error means navigator.share threw before showing
        // the sheet, so we still try clipboard as a graceful fallback.
        const name = err?.name || "";
        if (name === "AbortError" || name === "NotAllowedError") return;
      }
      // navigator.share resolved successfully — nothing else to do.
      return;
    }
    // No Web Share API → silent clipboard copy + green "Copied!" pill.
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard blocked — give up silently */ }
  };

  return (
    <button onClick={share} className="mt-2 w-full btn btn-secondary flex items-center justify-center gap-2" data-testid="share-button">
      <Share2 size={14} /> {copied ? t("auction.link_copied") : t("auction.share_auction")}
    </button>
  );
}

