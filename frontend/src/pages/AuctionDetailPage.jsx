import React, { useEffect, useState, useCallback, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Calendar, Gauge, Fuel, Settings, MapPin, Palette, Zap, Cog, MessageCircle, Heart, ArrowLeft, Shield, Wifi } from "lucide-react";
import { api, API_BASE, formatEUR, formatBGN, formatKM, timeLeft } from "../lib/apiClient";
import { useAuth, formatError } from "../lib/auth";
import PreauthModal from "../components/PreauthModal";
import AuctionCard from "../components/AuctionCard";

export default function AuctionDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [a, setA] = useState(null);
  const [bids, setBids] = useState([]);
  const [comments, setComments] = useState([]);
  const [photoIdx, setPhotoIdx] = useState(0);
  const [bidAmount, setBidAmount] = useState("");
  const [commentText, setCommentText] = useState("");
  const [t, setT] = useState({ label: "" });
  const [error, setError] = useState("");
  const [placing, setPlacing] = useState(false);
  const [showPreauth, setShowPreauth] = useState(false);
  const [wsStatus, setWsStatus] = useState("connecting");
  const [watching, setWatching] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [vinRequesting, setVinRequesting] = useState(false);
  const [vinMsg, setVinMsg] = useState("");
  const [vinErr, setVinErr] = useState("");
  const [related, setRelated] = useState([]);
  const wsRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const ra = await api.get(`/auctions/${id}`);
      const [rb, rc] = await Promise.all([
        api.get(`/auctions/${id}/bids`).catch(() => ({ data: [] })),
        api.get(`/auctions/${id}/comments`).catch(() => ({ data: [] })),
      ]);
      setA(ra.data);
      setBids(rb.data);
      setComments(rc.data);
      setBidAmount(String(Math.floor(ra.data.current_bid_eur) + 100));
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

  const toggleWatch = async () => {
    if (!user) { navigate("/login?next=/auctions/" + id); return; }
    try {
      const { data } = await api.post(`/auctions/${id}/watch`);
      setWatching(!!data.watching);
    } catch (e) {}
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
          setBidAmount((cur) => String(Math.max(Math.floor(msg.current_bid_eur) + 100, Number(cur || 0))));
        } else if (msg.type === "comment") {
          setComments((prev) => {
            if (prev.some((c) => c.id === msg.comment.id)) return prev;
            return [msg.comment, ...prev];
          });
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
    setT(timeLeft(a.ends_at));
    if (a.status === "sold" || a.status === "ended") return;
    const i = setInterval(() => setT(timeLeft(a.ends_at)), 1000);
    return () => clearInterval(i);
  }, [a]);

  const startBid = () => {
    setError("");
    if (!user) { navigate("/login?next=/auctions/" + id); return; }
    const amt = Number(bidAmount);
    const min = Math.floor(a.current_bid_eur) + 100;
    if (!amt || amt < min) { setError(`Минималната следваща наддавка е €${min}`); return; }
    setShowPreauth(true);
  };

  const confirmBid = async (paymentMethodId) => {
    setShowPreauth(false);
    setPlacing(true);
    try {
      await api.post(`/auctions/${id}/bids`, { amount_eur: Number(bidAmount), payment_method_id: paymentMethodId });
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
      <h1 className="font-serif text-4xl">Търгът не е намерен</h1>
      <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Обявата може да е оттеглена или archiveирана.</p>
      <Link to="/auctions" className="btn btn-primary mt-8 inline-flex">Към всички търгове</Link>
    </main>
  );
  if (!a) return <div className="py-24 text-center">Зареждане…</div>;

  const specs = [
    { i: Calendar, l: "Година", v: a.year },
    { i: Gauge, l: "Пробег", v: formatKM(a.mileage_km) },
    { i: Fuel, l: "Гориво", v: a.fuel },
    { i: Settings, l: "Скорости", v: a.transmission },
    { i: Cog, l: "Двигател", v: `${a.engine_cc} см³` },
    { i: Zap, l: "Мощност", v: `${a.power_hp} к.с.` },
    { i: Palette, l: "Цвят", v: a.color },
    { i: MapPin, l: "Локация", v: `${a.city}, обл. ${a.region}` },
  ];

  const isLive = a.status === "live";
  const preauthPreview = Math.round((Number(bidAmount) || 0) * 0.02);
  const hasPendingCounterForMe = a.counter_status === "pending" && a.counter_offer_to === user?.id;

  return (
    <main className="rule-b" data-testid="auction-detail-page">
      <PreauthModal open={showPreauth} onClose={() => setShowPreauth(false)} onConfirm={confirmBid} bidAmount={bidAmount} />

      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-8">
        <Link to="/auctions" className="inline-flex items-center gap-2 text-sm text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]">
          <ArrowLeft size={14} /> Обратно към търговете
        </Link>

        <div className="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
          <div className="lg:col-span-8">
            <div className="overline text-[hsl(var(--accent))]">{a.make} · {a.body_type}</div>
            <h1 className="font-serif text-3xl lg:text-5xl mt-3 tracking-tight leading-tight">{a.title}</h1>
            <div className="mt-3 text-sm text-[hsl(var(--ink-muted))] flex items-center gap-4 flex-wrap">
              <span>{a.year} · {formatKM(a.mileage_km)} · {a.fuel} · {a.city}</span>
              <span className={`flex items-center gap-1.5 text-xs ${wsStatus === "connected" ? "text-[hsl(var(--accent))]" : "text-[hsl(var(--ink-muted))]"}`} data-testid="ws-status">
                <Wifi size={11} /> {wsStatus === "connected" ? "На живо" : wsStatus === "connecting" ? "Свързване…" : "Offline"}
              </span>
            </div>

            <div className="mt-8 border border-[hsl(var(--line))] rounded-card aspect-[4/3] overflow-hidden bg-[hsl(var(--surface))]">
              <img src={a.images?.[photoIdx]} alt={a.title} className="w-full h-full object-cover" />
            </div>
            {a.images?.length > 1 && (
              <div className="mt-3 grid grid-cols-5 gap-2">
                {a.images.map((img, i) => (
                  <button key={i} onClick={() => setPhotoIdx(i)} className={`aspect-[4/3] rounded-card border overflow-hidden ${photoIdx === i ? "border-[hsl(var(--ink))]" : "border-[hsl(var(--line))]"}`} data-testid={`thumb-${i}`}>
                    <img src={img} alt="" className="w-full h-full object-cover" />
                  </button>
                ))}
              </div>
            )}

            <div className="mt-10">
              <div className="overline text-[hsl(var(--ink-muted))]">Спецификации</div>
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
                      <Shield size={12} /> VIN номер
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
                          <Shield size={12} /> {vinRequesting ? "Изпращане…" : "Заяви пълен VIN"}
                        </button>
                      )}
                      <p className="text-xs text-[hsl(var(--ink-muted))] max-w-[220px]" data-testid="vin-masked-note">
                        {!user
                          ? "Влезте и заявете VIN или наддайте, за да го видите тук."
                          : isLive
                            ? "Заявката изпраща пълния VIN на вашия имейл. Наддаването също го разкрива в обявата."
                            : "Заявка за VIN е достъпна само при активен търг."}
                      </p>
                    </div>
                  ) : (
                    <span className="pill pill-live" data-testid="vin-unmasked-badge">Пълен VIN · разкрит</span>
                  )}
                </div>
              )}
            </div>

            <div className="mt-10">
              <div className="overline text-[hsl(var(--ink-muted))]">Описание от редакцията</div>
              <DescriptionWithInteriorShots description={a.description} interiorImages={a.images_interior || []} />
            </div>

            <div className="mt-14">
              <div className="overline text-[hsl(var(--accent))]">История на търга</div>
              <h2 className="font-serif text-2xl lg:text-3xl mt-2">Наддавания ({bids.length})</h2>
              <div className="mt-6 rounded-card border border-[hsl(var(--line))] overflow-hidden">
                {bids.length === 0 ? (
                  <p className="p-6 text-sm text-[hsl(var(--ink-muted))]">Все още няма наддавания. Бъдете първи.</p>
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
                          {new Date(b.created_at).toLocaleString("bg-BG")}
                          {b.preauth_status === "authorized" && <span className="ml-2 text-[hsl(var(--accent))]">· preauth активен</span>}
                        </div>
                      </div>
                      <div className="font-serif text-xl">{formatEUR(b.amount_eur)}</div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="mt-14">
              <div className="overline text-[hsl(var(--accent))]">Общност</div>
              <h2 className="font-serif text-2xl lg:text-3xl mt-2 flex items-center gap-3">
                <MessageCircle size={22} /> Коментари ({comments.length})
              </h2>

              <div className="mt-5 rounded-card border border-[hsl(var(--line))] p-4">
                <textarea
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  placeholder={user ? "Споделете мнение или въпрос…" : "Влезте, за да коментирате"}
                  disabled={!user}
                  rows={3}
                  className="w-full border border-[hsl(var(--line))] p-3 text-sm resize-none"
                  data-testid="comment-input"
                />
                <div className="mt-3 flex justify-end">
                  <button onClick={postComment} disabled={!user || !commentText.trim()} className="btn btn-primary disabled:opacity-40" data-testid="submit-comment">
                    Публикувай
                  </button>
                </div>
              </div>

              <div className="mt-6 space-y-5">
                {comments.map((c) => (
                  <div key={c.id} className="rounded-card border border-[hsl(var(--line))] p-5" data-testid={`comment-${c.id}`}>
                    <div className="flex items-center justify-between">
                      {c.user_id ? (
                        <Link to={`/profile/${c.user_id}`} className="text-sm font-semibold hover:text-[hsl(var(--accent))]">{c.user_name}</Link>
                      ) : (
                        <div className="text-sm font-semibold">{c.user_name}</div>
                      )}
                      <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">{new Date(c.created_at).toLocaleString("bg-BG")}</div>
                    </div>
                    <p className="mt-3 text-sm leading-relaxed">{c.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <aside className="lg:col-span-4">
            <div className="lg:sticky lg:top-28 space-y-5">
              <div className="rounded-card border border-[hsl(var(--line))] p-6 bg-white" data-testid="bid-section">
                {hasPendingCounterForMe && (
                  <div className="mb-5 rounded-card bg-[hsl(var(--accent-soft))] border border-[hsl(var(--accent))]/30 p-4" data-testid="counter-banner">
                    <div className="overline text-[hsl(var(--accent))]">Контраоферта от продавача</div>
                    <div className="font-serif text-3xl mt-2">{formatEUR(a.counter_offer_eur)}</div>
                    <p className="mt-2 text-xs text-[hsl(var(--ink-muted))]">Резервът не бе достигнат. Продавачът предлага тази цена директно на вас.</p>
                    <div className="mt-3 flex gap-2">
                      <button onClick={() => respondCounter(true)} className="btn btn-accent !py-2 !px-4 text-xs flex-1" data-testid="counter-accept">Приеми</button>
                      <button onClick={() => respondCounter(false)} className="btn btn-secondary !py-2 !px-4 text-xs flex-1" data-testid="counter-decline">Откажи</button>
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-between flex-wrap gap-2">
                  {a.status === "sold" ? <span className="pill pill-sold">Продаден</span>
                    : a.status === "ended" ? <span className="pill pill-sold">Приключил</span>
                    : t.urgent ? <span className="pill pill-ending">{t.label}</span>
                    : <span className="pill pill-live">{t.label}</span>}
                  {a.has_reserve && (
                    a.reserve_met
                      ? <span className="pill pill-live" data-testid="reserve-met">Резервът е достигнат</span>
                      : <span className="pill" data-testid="with-reserve">С резерв</span>
                  )}
                  {a.has_reserve === false && <span className="pill" data-testid="no-reserve">Без резерв</span>}
                  <span className="overline text-[hsl(var(--ink-muted))] ml-auto">{a.bid_count || 0} наддавания</span>
                </div>

                <div className="mt-6">
                  <div className="overline text-[hsl(var(--ink-muted))]">{a.status === "sold" ? "Продаден за" : "Текуща наддавка"}</div>
                  <div className="font-serif text-5xl mt-2" data-testid="current-bid">{formatEUR(a.current_bid_eur)}</div>
                  <div className="text-sm text-[hsl(var(--ink-muted))] font-mono mt-1">{formatBGN(a.current_bid_eur)}</div>
                  {a.high_bidder_name && (
                    <div className="mt-2 text-xs text-[hsl(var(--ink-muted))]">Водещ: <span className="text-[hsl(var(--ink))]">{a.high_bidder_name}</span></div>
                  )}
                  {a.has_reserve && !a.reserve_met && isLive && (
                    <div className="mt-3 text-xs text-[hsl(var(--ink-muted))] flex items-center gap-1.5" data-testid="reserve-not-met">
                      <span className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--ink-muted))]"></span>
                      Резервната цена все още не е достигната
                    </div>
                  )}
                  {a.has_reserve && a.reserve_met && (
                    <div className="mt-3 text-xs text-[hsl(var(--accent))] flex items-center gap-1.5" data-testid="reserve-reached">
                      <span className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--accent))]"></span>
                      Резервната цена е достигната
                    </div>
                  )}
                </div>

                {isLive && (
                  <div className="mt-6 rule-t pt-5">
                    <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Вашата наддавка (EUR)</label>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        min={Math.floor(a.current_bid_eur) + 100}
                        value={bidAmount}
                        onChange={(e) => setBidAmount(e.target.value)}
                        className="flex-1 border border-[hsl(var(--line))] h-12 px-3 text-base"
                        data-testid="bid-amount-input"
                      />
                      <button onClick={startBid} disabled={placing} className="btn btn-accent !px-6" data-testid="place-bid-button">
                        {placing ? "…" : "Наддай"}
                      </button>
                    </div>
                    <p className="text-xs text-[hsl(var(--ink-muted))] mt-2">Минимум €{Math.floor(a.current_bid_eur) + 100}</p>

                    <div className="mt-4 p-3 rounded-card bg-[hsl(var(--accent-soft))] border border-[hsl(var(--accent))]/20 flex items-start gap-2">
                      <Shield size={14} className="text-[hsl(var(--accent))] shrink-0 mt-0.5" />
                      <div className="text-xs leading-relaxed">
                        <div className="font-semibold text-[hsl(var(--accent-ink))]">Pre-authorization {formatEUR(preauthPreview)}</div>
                        <div className="text-[hsl(var(--ink-muted))] mt-0.5">2% се блокират върху картата. При победа се прилагат като buyer's premium; иначе се освобождават изцяло.</div>
                      </div>
                    </div>

                    {error && <p className="text-xs text-[hsl(var(--danger))] mt-2" data-testid="bid-error">{error}</p>}
                  </div>
                )}

                <button onClick={toggleWatch} className={`mt-5 w-full btn flex items-center justify-center gap-2 ${watching ? "btn-primary" : "btn-secondary"}`} data-testid="watch-button">
                  <Heart size={14} className={watching ? "fill-current" : ""} /> {watching ? "В моя списък" : "Следи търга"}
                </button>
              </div>

              <div className="rounded-card border border-[hsl(var(--line))] p-6 bg-[hsl(var(--surface))]">
                <div className="overline text-[hsl(var(--ink-muted))]">Продавач</div>
                {a.seller_id && a.seller_id !== "platform" ? (
                  <Link to={`/profile/${a.seller_id}`} className="font-serif text-xl mt-2 block hover:text-[hsl(var(--accent))]" data-testid="seller-link">{a.seller_name}</Link>
                ) : (
                  <div className="font-serif text-xl mt-2">{a.seller_name}</div>
                )}
                <p className="text-xs text-[hsl(var(--ink-muted))] mt-2" data-testid="seller-badge">
                  {a.seller_is_verified_dealer ? "Проверен дилър" : "Частно лице"} · {a.region}
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
                <div className="overline text-[hsl(var(--accent))]">Също виж</div>
                <h2 className="font-serif text-3xl lg:text-4xl mt-2 tracking-tight">Подобни обяви</h2>
              </div>
              <Link to="/auctions" className="text-sm font-semibold text-[hsl(var(--accent))] hover:underline">
                Виж всички търгове →
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
    </main>
  );
}

function DescriptionWithInteriorShots({ description, interiorImages }) {
  const text = (description || "").trim();
  const shots = (interiorImages || []).slice(0, 3);

  // Split description into paragraphs on empty lines or fallback to sentence groups
  let paragraphs = text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  if (paragraphs.length < 2) {
    // Break by sentences into ~2 balanced chunks
    const sentences = text.split(/(?<=[.!?])\s+/).filter(Boolean);
    if (sentences.length >= 2) {
      const mid = Math.ceil(sentences.length / 2);
      paragraphs = [sentences.slice(0, mid).join(" "), sentences.slice(mid).join(" ")].filter(Boolean);
    } else {
      paragraphs = [text];
    }
  }

  if (shots.length === 0) {
    return (
      <div className="mt-4 max-w-3xl space-y-4" data-testid="auction-description">
        {paragraphs.map((p, i) => (
          <p key={i} className="text-[15px] leading-[1.7] whitespace-pre-wrap text-[hsl(var(--ink))]/90">{p}</p>
        ))}
      </div>
    );
  }

  // Intersperse shots between paragraphs. We place one shot after each paragraph until we run out.
  const blocks = [];
  paragraphs.forEach((p, i) => {
    blocks.push(
      <p key={`p-${i}`} className="text-[15px] leading-[1.7] whitespace-pre-wrap text-[hsl(var(--ink))]/90">{p}</p>
    );
    if (i < shots.length) {
      blocks.push(
        <figure key={`s-${i}`} className="my-2 rounded-card overflow-hidden border border-[hsl(var(--line))] bg-[hsl(var(--surface))]">
          <img src={shots[i]} alt="Интериор" loading="lazy" className="w-full h-auto object-cover max-h-[480px]" data-testid={`interior-shot-${i}`} />
          <figcaption className="px-3 py-2 text-xs text-[hsl(var(--ink-muted))] font-mono tracking-wide">Интериор · {i + 1}/{shots.length}</figcaption>
        </figure>
      );
    }
  });

  // If there are leftover shots (more shots than paragraph gaps), append them at the end
  if (shots.length > paragraphs.length) {
    for (let i = paragraphs.length; i < shots.length; i++) {
      blocks.push(
        <figure key={`s-tail-${i}`} className="my-2 rounded-card overflow-hidden border border-[hsl(var(--line))] bg-[hsl(var(--surface))]">
          <img src={shots[i]} alt="Интериор" loading="lazy" className="w-full h-auto object-cover max-h-[480px]" data-testid={`interior-shot-${i}`} />
          <figcaption className="px-3 py-2 text-xs text-[hsl(var(--ink-muted))] font-mono tracking-wide">Интериор · {i + 1}/{shots.length}</figcaption>
        </figure>
      );
    }
  }

  return (
    <div className="mt-4 max-w-3xl space-y-4" data-testid="auction-description">
      {blocks}
    </div>
  );
}

