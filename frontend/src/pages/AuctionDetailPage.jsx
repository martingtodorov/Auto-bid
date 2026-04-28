import React, { useEffect, useState, useCallback, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Calendar, Gauge, Fuel, Settings, MapPin, Palette, Zap, Cog, MessageCircle, Heart, ArrowLeft, Shield, Wifi, Share2, Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api, API_BASE, formatEUR, formatLocal, formatKM, timeLeft, formatTimeLeft, intlLocale } from "../lib/apiClient";
import { translateEnum } from "../lib/carTranslations";
import { useAuth, formatError } from "../lib/auth";
import PreauthModal from "../components/PreauthModal";
import BiddingCreditModal from "../components/BiddingCreditModal";
import AuctionCard from "../components/AuctionCard";
import NegotiationPortal from "../components/NegotiationPortal";
import Lightbox from "../components/Lightbox";
import { useSiteSettings, computeBuyerFee } from "../lib/settings";
import { setPageMeta, resetPageMeta, buildVehicleJsonLd, buildBreadcrumbs, combineJsonLd } from "../lib/seo";
import { brandNameForLang } from "../i18n/index";

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
  const [showPreauth, setShowPreauth] = useState(false);
  const [wsStatus, setWsStatus] = useState("connecting");
  const [watching, setWatching] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [vinRequesting, setVinRequesting] = useState(false);
  const [vinMsg, setVinMsg] = useState("");
  const [vinErr, setVinErr] = useState("");
  const [related, setRelated] = useState([]);
  const [credit, setCredit] = useState(null);
  const [showCredit, setShowCredit] = useState(false);
  const [nextBid, setNextBid] = useState({ min_next_eur: 0, buyer_fee_eur: 150, step_eur: 100 });
  const wsRef = useRef(null);
  const settings = useSiteSettings();

  // Client-side buyer fee for preview (mirrors backend _buyer_fee)
  const buyerFeeFor = (amount) => computeBuyerFee(amount, settings);

  // Variable bid step (mirrors backend _bid_step)
  const bidStepFor = (price) => {
    const p = Number(price) || 0;
    if (p < 1000) return 50;
    if (p < 5000) return 100;
    if (p < 10000) return 250;
    if (p < 25000) return 500;
    if (p < 50000) return 750;
    if (p < 100000) return 1000;
    if (p < 200000) return 2000;
    if (p < 500000) return 5000;
    if (p < 1000000) return 10000;
    return 25000;
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
  useEffect(() => {
    if (!a) return;
    let cancelled = false;
    (async () => {
      try {
        const byMake = await api.get("/auctions", { params: { make: a.make, status: "live", limit: 12 } }).catch(() => ({ data: [] }));
        let items = (byMake.data || []).filter((x) => x.id !== a.id);
        if (items.length < 4) {
          const byBody = await api.get("/auctions", { params: { body_type: a.body_type, status: "live", limit: 12 } }).catch(() => ({ data: [] }));
          const extra = (byBody.data || []).filter((x) => x.id !== a.id && !items.find((y) => y.id === x.id));
          items = [...items, ...extra];
        }
        if (items.length < 4) {
          const any = await api.get("/auctions", { params: { status: "live", limit: 12 } }).catch(() => ({ data: [] }));
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

  // Bidding credit
  useEffect(() => {
    if (!user || !id) { setCredit(null); return; }
    api.get(`/auctions/${id}/bidding-credit`).then((r) => setCredit(r.data || null)).catch(() => setCredit(null));
  }, [user, id]);

  // SEO meta tags + structured data
  useEffect(() => {
    if (!a) return;
    const url = window.location.href;
    const origin = window.location.origin;
    const breadcrumbs = buildBreadcrumbs([
      { name: t("nav.home", "Home"), url: origin + "/" },
      { name: t("nav.auctions", "Auctions"), url: origin + "/auctions" },
      { name: a.title, url },
    ]);
    const vehicle = buildVehicleJsonLd(a, url);
    const brand = brandNameForLang(i18n.resolvedLanguage || i18n.language);
    setPageMeta({
      title: `${a.title} — ${brand}`,
      description: a.description,
      image: a.images?.[0],
      url,
      jsonLd: combineJsonLd(vehicle, breadcrumbs),
    });
    return () => resetPageMeta();
  }, [a]);

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
      await api.post(`/auctions/${id}/buy-now`);
      // server broadcasts via WS; refresh anyway
      const { data } = await api.get(`/auctions/${id}`);
      setA(data);
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
      setError(`${t("auction.min_bid_error", "Минималната следваща наддавка е")} €${minDisplay.toLocaleString()}`);
      return;
    }
    if (credit && Number(credit.max_amount_eur) >= netAmt) {
      confirmBid(null);
      return;
    }
    setShowPreauth(true);
  };

  const confirmBid = async (paymentMethodId) => {
    setShowPreauth(false);
    setPlacing(true);
    try {
      const typed = Number(bidAmount);
      const netAmt = vatRate > 0 ? Math.round(typed / (1 + vatRate / 100)) : typed;
      const payload = { amount_eur: netAmt };
      if (paymentMethodId) payload.payment_method_id = paymentMethodId;
      await api.post(`/auctions/${id}/bids`, payload);
    } catch (e) {
      setError(formatError(e));
    } finally {
      setPlacing(false);
    }
  };

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
      <PreauthModal open={showPreauth} onClose={() => setShowPreauth(false)} onConfirm={confirmBid} bidAmount={bidAmount} />
      {showCredit && a && (
        <BiddingCreditModal
          auctionId={id}
          currentBid={a.current_bid_eur}
          currentCredit={credit}
          onClose={() => setShowCredit(false)}
          onSaved={(c) => setCredit(c)}
        />
      )}

      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-8">
        <Link to="/auctions" className="inline-flex items-center gap-2 text-sm text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]">
          <ArrowLeft size={14} /> {t("auction.back_to_auctions")}
        </Link>

        <div className="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
          <div className="lg:col-span-8">
            <div className="overline text-[hsl(var(--accent))]">{a.make} · {translateEnum(a.body_type, "body_type", lng)}</div>
            <h1 className="font-serif text-3xl lg:text-5xl mt-3 tracking-tight leading-tight">{a.title}</h1>
            <div className="mt-3 text-sm text-[hsl(var(--ink-muted))] flex items-center gap-4 flex-wrap">
              <span>{a.year} · {formatKM(a.mileage_km)} · {translateEnum(a.fuel, "fuel", lng)} · {translateEnum(a.city, "city", lng)}{a.country ? `, ${a.country}` : ""}</span>
              <span className={`flex items-center gap-1.5 text-xs ${wsStatus === "connected" ? "text-[hsl(var(--accent))]" : "text-[hsl(var(--ink-muted))]"}`} data-testid="ws-status">
                <Wifi size={11} /> {wsStatus === "connected" ? t("auction.live") : wsStatus === "connecting" ? t("auction.connecting") : t("auction.offline")}
              </span>
            </div>

            <div className="mt-8 border border-[hsl(var(--line))] rounded-card aspect-[4/3] overflow-hidden bg-[hsl(var(--surface))] cursor-zoom-in relative group" onClick={() => setLightboxIdx(photoIdx)} data-testid="main-gallery-image">
              <img src={a.images?.[photoIdx]} alt={a.title} className="w-full h-full object-cover transition group-hover:scale-[1.02]" />
              {a.images?.length > 0 && (
                <div className="absolute bottom-3 right-3 px-2.5 py-1 rounded-full bg-black/55 text-white text-xs font-mono opacity-0 group-hover:opacity-100 transition pointer-events-none">
                  {photoIdx + 1} / {a.images.length} · {t("common.zoom")}
                </div>
              )}
            </div>
            {a.images?.length > 1 && (() => {
              const total = a.images.length;
              // Mobile shows at most 5 thumbnails (1 row). The 5th gets a
              // "+N more" dark overlay if there are extra photos hidden.
              // Desktop shows all thumbs in the 5-col grid as usual.
              const MOBILE_MAX = 5;
              const mobileExtra = total - MOBILE_MAX;
              return (
                <div className="mt-3 grid grid-cols-5 gap-2">
                  {a.images.map((img, i) => {
                    // hide thumbs >= 5 on mobile only
                    const hideOnMobile = i >= MOBILE_MAX;
                    const isMobileLastVisible = i === MOBILE_MAX - 1 && mobileExtra > 0;
                    return (
                      <button
                        key={i}
                        onClick={() => isMobileLastVisible ? setLightboxIdx(i) : setPhotoIdx(i)}
                        className={`relative aspect-[4/3] rounded-card border overflow-hidden ${
                          photoIdx === i ? "border-[hsl(var(--ink))]" : "border-[hsl(var(--line))]"
                        } ${hideOnMobile ? "hidden md:block" : ""}`}
                        data-testid={`thumb-${i}`}
                      >
                        <img src={img} alt="" className="w-full h-full object-cover" />
                        {isMobileLastVisible && (
                          <span
                            className="md:hidden absolute inset-0 bg-black/65 hover:bg-black/75 transition-colors flex items-center justify-center text-white font-serif text-lg cursor-zoom-in"
                            data-testid="thumb-more-overlay"
                          >
                            +{mobileExtra}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            })()}

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
                    <div className="font-mono text-lg mt-1 tracking-wider" data-testid="vin-value">{a.vin}</div>
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
                description={a.description}
                interiorImages={a.images_interior || []}
                preTranslated={{ ro: a.description_ro || "", en: a.description_en || "" }}
              />
            </div>

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
                          <Link to={`/profile/${b.user_id}`} className="text-sm font-semibold hover:text-[hsl(var(--accent))]" data-testid={`bidder-link-${b.id}`}>{b.user_name}</Link>
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
            <div className="lg:sticky lg:top-28 space-y-5">
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
                        ? t("auction.your_bid_eur_gross", "Вашата наддавка (EUR, вкл. ДДС {{rate}}%)", { rate: vatRate })
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
                      <div className="mt-2 flex items-baseline justify-between gap-2 px-1" data-testid="bid-net-preview">
                        <span className="text-xs text-[hsl(var(--ink-muted))]">{t("auction.without_vat_label", "Без ДДС")}</span>
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
                        {vatRate > 0 && bidAmountGross > 0 && (
                          <div className="text-[hsl(var(--ink-muted))] mt-1">
                            {t("auction.buyer_fee_on_gross", "Изчислено върху цена с ДДС: {{gross}}", { gross: formatEUR(bidAmountGross) })}
                          </div>
                        )}
                      </div>
                    </div>

                    {user && credit && (
                      <div className="mt-3 p-3 rounded-card bg-white border border-[hsl(var(--accent))]/40 flex items-start justify-between gap-2" data-testid="credit-active-badge">
                        <div className="text-xs leading-relaxed">
                          <div className="font-semibold text-[hsl(var(--accent))] flex items-center gap-1.5">
                            <Zap size={12} /> {t("auction.active_credit_short")} · {formatEUR(credit.max_amount_eur)}
                          </div>
                          <div className="text-[hsl(var(--ink-muted))] mt-0.5">{t("auction.up_to_credit_hint")}</div>
                        </div>
                        <button onClick={() => setShowCredit(true)} className="text-xs font-semibold text-[hsl(var(--accent))] hover:underline shrink-0" data-testid="credit-manage-btn">Управи</button>
                      </div>
                    )}
                    {user && !credit && (
                      <button onClick={() => setShowCredit(true)} className="mt-3 w-full rounded-card border border-dashed border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent-soft))]/50 hover:bg-[hsl(var(--accent-soft))] p-3 text-left transition" data-testid="credit-open-btn">
                        <div className="flex items-center gap-2 text-xs">
                          <Zap size={13} className="text-[hsl(var(--accent))] shrink-0" />
                          <div>
                            <div className="font-semibold text-[hsl(var(--accent-ink))]">{t("auction.bid_no_new_tx")}</div>
                            <div className="text-[hsl(var(--ink-muted))] mt-0.5">Преавторизирай се за по-голяма сума →</div>
                          </div>
                        </div>
                      </button>
                    )}

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
                    <p className="text-xs text-[hsl(var(--ink-muted))] mt-2">{t("auction.buy_now_hint", "Купувайте веднага без да чакате края на търга. Резервът се счита за изпълнен.")}</p>
                    {(() => {
                      const grossPrice = vatRate > 0 ? grossOf(a.buy_now_eur) : Number(a.buy_now_eur || 0);
                      const buyNowFee = buyerFeeFor(grossPrice);
                      return buyNowFee > 0 && (
                        <div className="mt-2 text-xs text-[hsl(var(--ink-muted))]" data-testid="buy-now-fee-preview">
                          {t("auction.buyer_fee_label")}: <span className="font-mono text-[hsl(var(--ink))]">{formatEUR(buyNowFee)}</span>
                          <span className="ml-1">({settings.buyer_fee_pct}% {t("auction.incl_vat", "вкл. ДДС")})</span>
                        </div>
                      );
                    })()}
                    <button
                      onClick={onBuyNow}
                      disabled={!user || buyingNow}
                      className="mt-3 w-full btn btn-primary !bg-[hsl(var(--accent))] !text-black hover:!bg-[hsl(var(--accent))]/85 disabled:opacity-50 flex items-center justify-center gap-2"
                      data-testid="buy-now-btn"
                    >
                      <Zap size={14} />
                      {buyingNow ? t("auction.buy_now_processing", "Обработваме…") : !user ? t("auction.login_to_buy", "Влез, за да закупиш") : t("auction.buy_now_action", "Закупи сега за {{price}}", { price: formatEUR(vatRate > 0 ? grossOf(a.buy_now_eur) : a.buy_now_eur) })}
                    </button>
                  </div>
                )}

                <button onClick={toggleWatch} className={`mt-5 w-full btn flex items-center justify-center gap-2 ${watching ? "btn-primary" : "btn-secondary"}`} data-testid="watch-button">
                  <Heart size={14} className={watching ? "fill-current" : ""} /> {watching ? t("auction.watchlist_remove") : t("auction.watchlist_add")}
                </button>
                <ShareButton auctionId={id} title={a?.title} />
              </div>

              <div className="rounded-card border border-[hsl(var(--line))] p-6 bg-[hsl(var(--surface))]">
                <div className="overline text-[hsl(var(--ink-muted))]">{t("auction.seller")}</div>
                {a.seller_id && a.seller_id !== "platform" ? (
                  <h2 className="font-serif text-xl mt-2">
                    <Link to={`/profile/${a.seller_id}`} className="block hover:text-[hsl(var(--accent))]" data-testid="seller-link">{a.seller_name}</Link>
                  </h2>
                ) : (
                  <h2 className="font-serif text-xl mt-2">{a.seller_name}</h2>
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
          index={lightboxIdx}
          onClose={() => setLightboxIdx(null)}
          onChange={(i) => { setLightboxIdx(i); setPhotoIdx(i); }}
        />
      )}
    </main>
  );
}

function DescriptionWithInteriorShots({ auctionId, description, interiorImages, preTranslated = {} }) {
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
      blocks.push(
        <figure
          key={`s-${i}`}
          className="my-2 rounded-card overflow-hidden border border-[hsl(var(--line))] bg-[hsl(var(--surface))]"
        >
          <img
            src={shot}
            alt="Interior"
            loading="lazy"
            className="w-full h-auto object-cover max-h-[480px]"
            data-testid={`interior-shot-${i}`}
          />
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
          {c.user_id && !c.deleted ? (
            <Link to={`/profile/${c.user_id}`} className="text-sm font-semibold hover:text-[hsl(var(--accent))]">{c.user_name}</Link>
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

function ShareButton({ auctionId, title }) {
  const { t, i18n } = useTranslation();
  const brand = brandNameForLang(i18n.resolvedLanguage || i18n.language);
  const [copied, setCopied] = React.useState(false);
  const shareUrl = `${window.location.origin}/api/share/auction/${auctionId}`;

  const share = async () => {
    const data = { title: title || brand, url: shareUrl };
    try {
      if (navigator.share) {
        await navigator.share(data);
        return;
      }
    } catch { /* user cancelled or not supported */ }
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt(shareUrl, shareUrl);
    }
  };

  return (
    <button onClick={share} className="mt-2 w-full btn btn-secondary flex items-center justify-center gap-2" data-testid="share-button">
      <Share2 size={14} /> {copied ? t("auction.link_copied") : t("auction.share_auction")}
    </button>
  );
}

