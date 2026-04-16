import React, { useEffect, useState, useCallback, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Calendar, Gauge, Fuel, Settings, MapPin, Palette, Zap, Cog, MessageCircle, Heart, ArrowLeft, Shield, Wifi } from "lucide-react";
import { api, API_BASE, formatEUR, formatBGN, formatKM, timeLeft } from "../lib/apiClient";
import { useAuth, formatError } from "../lib/auth";
import PreauthModal from "../components/PreauthModal";

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
  const wsRef = useRef(null);

  const load = useCallback(async () => {
    const [ra, rb, rc] = await Promise.all([
      api.get(`/auctions/${id}`),
      api.get(`/auctions/${id}/bids`),
      api.get(`/auctions/${id}/comments`),
    ]);
    setA(ra.data);
    setBids(rb.data);
    setComments(rc.data);
    setBidAmount(String(Math.floor(ra.data.current_bid_eur) + 100));
  }, [id]);

  useEffect(() => { load(); }, [load]);

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
  const preauthPreview = Math.round((Number(bidAmount) || 0) * 0.03);

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
            </div>

            <div className="mt-10">
              <div className="overline text-[hsl(var(--ink-muted))]">Описание от редакцията</div>
              <p className="mt-4 font-serif text-xl leading-[1.6] whitespace-pre-wrap max-w-3xl">{a.description}</p>
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
                        <div className="text-sm font-semibold">{b.user_name}</div>
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
                      <div className="text-sm font-semibold">{c.user_name}</div>
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
                <div className="flex items-center justify-between">
                  {a.status === "sold" ? <span className="pill pill-sold">Продаден</span>
                    : a.status === "ended" ? <span className="pill pill-sold">Приключил</span>
                    : t.urgent ? <span className="pill pill-ending">{t.label}</span>
                    : <span className="pill pill-live">{t.label}</span>}
                  <span className="overline text-[hsl(var(--ink-muted))]">{a.bid_count || 0} наддавания</span>
                </div>

                <div className="mt-6">
                  <div className="overline text-[hsl(var(--ink-muted))]">{a.status === "sold" ? "Продаден за" : "Текуща наддавка"}</div>
                  <div className="font-serif text-5xl mt-2" data-testid="current-bid">{formatEUR(a.current_bid_eur)}</div>
                  <div className="text-sm text-[hsl(var(--ink-muted))] font-mono mt-1">{formatBGN(a.current_bid_eur)}</div>
                  {a.high_bidder_name && (
                    <div className="mt-2 text-xs text-[hsl(var(--ink-muted))]">Водещ: <span className="text-[hsl(var(--ink))]">{a.high_bidder_name}</span></div>
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
                        <div className="text-[hsl(var(--ink-muted))] mt-0.5">3% се блокират върху картата. При победа се прилагат като buyer's premium; иначе се освобождават изцяло.</div>
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
                <div className="font-serif text-xl mt-2">{a.seller_name}</div>
                <p className="text-xs text-[hsl(var(--ink-muted))] mt-2">Проверен дилър · {a.region}</p>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}
