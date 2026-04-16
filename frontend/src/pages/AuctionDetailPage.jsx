import React, { useEffect, useState, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Calendar, Gauge, Fuel, Settings, MapPin, Palette, Zap, Cog, MessageCircle, Heart, ArrowLeft } from "lucide-react";
import { api, formatEUR, formatBGN, formatKM, timeLeft } from "../lib/apiClient";
import { useAuth, formatError } from "../lib/auth";

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

  useEffect(() => {
    if (!a) return;
    setT(timeLeft(a.ends_at));
    if (a.status === "sold" || a.status === "ended") return;
    const i = setInterval(() => setT(timeLeft(a.ends_at)), 1000);
    return () => clearInterval(i);
  }, [a]);

  const placeBid = async () => {
    setError("");
    if (!user) { navigate("/login?next=/auctions/" + id); return; }
    setPlacing(true);
    try {
      await api.post(`/auctions/${id}/bids`, { amount_eur: Number(bidAmount) });
      await load();
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
      await load();
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

  return (
    <main className="rule-b" data-testid="auction-detail-page">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-8">
        <Link to="/auctions" className="inline-flex items-center gap-2 text-sm text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]">
          <ArrowLeft size={14} /> Обратно към търговете
        </Link>

        <div className="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
          {/* Left: gallery + content */}
          <div className="lg:col-span-8">
            <div className="overline text-[hsl(var(--accent))]">{a.make} · {a.body_type}</div>
            <h1 className="font-serif text-3xl lg:text-5xl mt-3 tracking-tight leading-tight">{a.title}</h1>
            <div className="mt-3 text-sm text-[hsl(var(--ink-muted))]">
              {a.year} · {formatKM(a.mileage_km)} · {a.fuel} · {a.city}
            </div>

            <div className="mt-8 border border-[hsl(var(--line))] aspect-[4/3] overflow-hidden bg-[hsl(var(--surface))]">
              <img src={a.images?.[photoIdx]} alt={a.title} className="w-full h-full object-cover" />
            </div>
            {a.images?.length > 1 && (
              <div className="mt-3 grid grid-cols-5 gap-2">
                {a.images.map((img, i) => (
                  <button key={i} onClick={() => setPhotoIdx(i)} className={`aspect-[4/3] border overflow-hidden ${photoIdx === i ? "border-[hsl(var(--ink))]" : "border-[hsl(var(--line))]"}`} data-testid={`thumb-${i}`}>
                    <img src={img} alt="" className="w-full h-full object-cover" />
                  </button>
                ))}
              </div>
            )}

            {/* Specs */}
            <div className="mt-10">
              <div className="overline text-[hsl(var(--ink-muted))]">Спецификации</div>
              <div className="mt-4 border border-[hsl(var(--line))] grid grid-cols-2 md:grid-cols-4">
                {specs.map((s, i) => (
                  <div key={i} className="p-5 border-r border-b border-[hsl(var(--line))] last:border-r-0 [&:nth-child(4n)]:border-r-0 [&:nth-last-child(-n+4)]:border-b-0">
                    <s.i size={15} className="text-[hsl(var(--ink-muted))]" />
                    <div className="overline text-[hsl(var(--ink-muted))] mt-2">{s.l}</div>
                    <div className="mt-1 text-sm">{s.v}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Description */}
            <div className="mt-10">
              <div className="overline text-[hsl(var(--ink-muted))]">Описание от редакцията</div>
              <p className="mt-4 font-serif text-xl leading-[1.6] whitespace-pre-wrap max-w-3xl">{a.description}</p>
            </div>

            {/* Bid history */}
            <div className="mt-14">
              <div className="overline text-[hsl(var(--accent))]">История на търга</div>
              <h2 className="font-serif text-2xl lg:text-3xl mt-2">Наддавания ({bids.length})</h2>
              <div className="mt-6 border border-[hsl(var(--line))]">
                {bids.length === 0 ? (
                  <p className="p-6 text-sm text-[hsl(var(--ink-muted))]">Все още няма наддавания. Бъдете първи.</p>
                ) : (
                  bids.map((b) => (
                    <div key={b.id} className="flex items-center justify-between p-4 border-b border-[hsl(var(--line))] last:border-b-0">
                      <div>
                        <div className="text-sm font-medium">{b.user_name}</div>
                        <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">
                          {new Date(b.created_at).toLocaleString("bg-BG")}
                        </div>
                      </div>
                      <div className="font-serif text-xl">{formatEUR(b.amount_eur)}</div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Comments */}
            <div className="mt-14">
              <div className="overline text-[hsl(var(--accent))]">Общност</div>
              <h2 className="font-serif text-2xl lg:text-3xl mt-2 flex items-center gap-3">
                <MessageCircle size={22} /> Коментари ({comments.length})
              </h2>

              <div className="mt-5 border border-[hsl(var(--line))] p-4">
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
                  <div key={c.id} className="border border-[hsl(var(--line))] p-5" data-testid={`comment-${c.id}`}>
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-medium">{c.user_name}</div>
                      <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">{new Date(c.created_at).toLocaleString("bg-BG")}</div>
                    </div>
                    <p className="mt-3 text-sm leading-relaxed">{c.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right: sticky bid box */}
          <aside className="lg:col-span-4">
            <div className="lg:sticky lg:top-24 space-y-5">
              <div className="border border-[hsl(var(--line))] p-6 bg-white" data-testid="bid-section">
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
                      <button onClick={placeBid} disabled={placing} className="btn btn-accent !px-6" data-testid="place-bid-button">
                        {placing ? "…" : "Наддай"}
                      </button>
                    </div>
                    <p className="text-xs text-[hsl(var(--ink-muted))] mt-2">Минимум €{Math.floor(a.current_bid_eur) + 100}</p>
                    {error && <p className="text-xs text-[hsl(var(--danger))] mt-2" data-testid="bid-error">{error}</p>}
                  </div>
                )}

                <button className="mt-5 w-full btn btn-secondary flex items-center justify-center gap-2" data-testid="watch-button">
                  <Heart size={14} /> Следи търга
                </button>
              </div>

              <div className="border border-[hsl(var(--line))] p-6 bg-[hsl(var(--surface))]">
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
