import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Shield, Gavel, FileCheck, Sparkles } from "lucide-react";
import { api, formatEUR, formatBGN } from "../lib/apiClient";
import AuctionCard from "../components/AuctionCard";

const HERO_IMAGE = "https://images.unsplash.com/photo-1698995339730-86b3dd454001?crop=entropy&cs=srgb&fm=jpg&q=85&w=2000";

export default function LandingPage() {
  const [auctions, setAuctions] = useState([]);
  const [featured, setFeatured] = useState([]);
  const [sold, setSold] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [l, f, s] = await Promise.all([
          api.get("/auctions", { params: { sort: "ending_soon", status: "live", limit: 6 } }),
          api.get("/auctions/featured"),
          api.get("/auctions/sold"),
        ]);
        setAuctions(l.data);
        setFeatured(f.data);
        setSold(s.data);
      } catch (e) {
        console.error(e);
      }
    })();
  }, []);

  const hero = featured[0] || auctions[0];

  return (
    <main data-testid="landing-page">
      {/* Hero */}
      <section className="rule-b hero-ambient">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-10 lg:py-16">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-14 items-center">
            <div className="lg:col-span-6 fade-up">
              <div className="overline text-[hsl(var(--accent))]">Автомобилни търгове</div>
              <h1 className="hero-headline text-5xl sm:text-6xl lg:text-7xl mt-6">
                Открийте <em>изключителни</em><br />автомобили.
              </h1>
              <p className="mt-6 text-lg text-[hsl(var(--ink-muted))] leading-relaxed max-w-xl">
                AutoBid.bg е платформа за онлайн търгове — всеки автомобил е внимателно подбран, документиран и представен от нашия екип.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/auctions" className="btn btn-primary !px-10" data-testid="hero-cta-browse">
                  Разгледай търгове <ArrowRight size={16} className="ml-2" />
                </Link>
                <Link to="/sell" className="btn btn-sell-gradient !px-10" data-testid="hero-cta-sell">
                  Продай своя автомобил
                </Link>
              </div>
            </div>

            <div className="lg:col-span-6 fade-up">
              {hero ? (
                <Link to={`/auctions/${hero.id}`} className="block group" data-testid="hero-featured-auction">
                  <div className="aspect-[4/3] overflow-hidden rounded-card border border-[hsl(var(--line))]">
                    <img src={hero.images?.[0] || HERO_IMAGE} alt={hero.title} className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" />
                  </div>
                  <div className="mt-4 flex items-end justify-between gap-4">
                    <div>
                      <div className="overline text-[hsl(var(--accent))]">Избрана обява</div>
                      <h3 className="font-serif text-2xl lg:text-3xl mt-2 tracking-tight">{hero.title}</h3>
                      <div className="text-sm text-[hsl(var(--ink-muted))] mt-2">
                        {hero.year} · {hero.city} · {hero.fuel}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="overline text-[hsl(var(--ink-muted))]">Текуща</div>
                      <div className="font-serif text-2xl">{formatEUR(hero.current_bid_eur)}</div>
                      <div className="text-xs font-mono text-[hsl(var(--ink-muted))]">{formatBGN(hero.current_bid_eur)}</div>
                    </div>
                  </div>
                </Link>
              ) : (
                <div className="aspect-[4/3] border border-[hsl(var(--line))] bg-[hsl(var(--surface))]" />
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Active Auctions */}
      <section className="rule-b">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
          <div className="flex items-end justify-between mb-10">
            <div>
              <div className="overline text-[hsl(var(--accent))]">Актуални</div>
              <h2 className="font-serif text-3xl lg:text-5xl tracking-tight mt-3">Активни търгове</h2>
            </div>
            <Link to="/auctions" className="text-sm hover:text-[hsl(var(--accent))] flex items-center gap-1" data-testid="landing-view-all-auctions">
              Всички <ArrowRight size={14} />
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 stagger" data-testid="landing-auctions-grid">
            {auctions.slice(0, 6).map((a) => <AuctionCard key={a.id} auction={a} />)}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="rule-b bg-[hsl(var(--surface))]">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
            <div className="lg:col-span-4">
              <div className="overline text-[hsl(var(--accent))]">Процесът</div>
              <h2 className="font-serif text-3xl lg:text-5xl tracking-tight mt-3">Как работи</h2>
              <p className="mt-5 text-[hsl(var(--ink-muted))] leading-relaxed">
                Четири стъпки от регистрацията до ключовете в ръцете на новия собственик.
              </p>
            </div>
            <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-2 gap-0 border border-[hsl(var(--line))] bg-white">
              {[
                { icon: Shield, t: "01. Регистрация", d: "Създайте безплатен акаунт за минута. Потвърждаваме самоличността преди първата наддавка." },
                { icon: FileCheck, t: "02. Проучване", d: "Пълен фото отчет, сервизна история, VIN проверка и независим технически доклад." },
                { icon: Gavel, t: "03. Наддаване", d: "Онлайн, в реално време, със защита от snipe-ване — последните 2 минути удължават търга." },
                { icon: Sparkles, t: "04. Приемане", d: "Директен контакт с продавача, помощ за транспорт, регистрация и финализиране." },
              ].map((s, i) => (
                <div key={i} className="p-8 rule-b md:border-r md:border-[hsl(var(--line))] md:[&:nth-child(2n)]:border-r-0 md:[&:nth-last-child(-n+2)]:border-b-0">
                  <s.icon size={22} className="text-[hsl(var(--accent))]" />
                  <h3 className="font-serif text-xl mt-5">{s.t}</h3>
                  <p className="mt-3 text-sm text-[hsl(var(--ink-muted))] leading-relaxed">{s.d}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Featured editorial */}
      {featured.length > 1 && (
        <section className="rule-b">
          <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
            <div className="flex items-end justify-between mb-10">
              <div>
                <div className="overline text-[hsl(var(--accent))]">Редакцията препоръчва</div>
                <h2 className="font-serif text-3xl lg:text-5xl tracking-tight mt-3">Избрани екземпляри</h2>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 stagger">
              {featured.slice(0, 6).map((a) => <AuctionCard key={a.id} auction={a} />)}
            </div>
          </div>
        </section>
      )}

      {/* Top sales */}
      {sold.length > 0 && (
        <section className="rule-b bg-[hsl(var(--surface))]">
          <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
            <div className="flex items-end justify-between mb-10">
              <div>
                <div className="overline text-[hsl(var(--accent))]">Архив</div>
                <h2 className="font-serif text-3xl lg:text-5xl tracking-tight mt-3">Последни продажби</h2>
              </div>
              <Link to="/sales" className="text-sm hover:text-[hsl(var(--accent))] flex items-center gap-1">
                Всички продажби <ArrowRight size={14} />
              </Link>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {sold.slice(0, 4).map((a) => <AuctionCard key={a.id} auction={a} compact />)}
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="bg-[hsl(var(--ink))] text-white">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-20 lg:py-28 grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7">
            <div className="overline text-[hsl(var(--accent))]" style={{color: "#6DE0B1"}}>Станете част от общността</div>
            <h2 className="hero-headline text-4xl lg:text-6xl mt-5">Готов ли сте за следващата<br/>си сделка?</h2>
            <p className="mt-6 text-white/70 max-w-xl leading-relaxed">
              Създайте акаунт и получавайте новите обяви преди всички останали.
            </p>
          </div>
          <div className="lg:col-span-5 lg:justify-self-end flex flex-wrap gap-3">
            <Link to="/register" className="btn !border-white bg-white !text-[hsl(var(--ink))] hover:!bg-[hsl(var(--accent))] hover:!text-white hover:!border-[hsl(var(--accent))]" data-testid="cta-register">
              Регистрирай се безплатно
            </Link>
            <Link to="/sell" className="btn !border-white/60 bg-transparent !text-white hover:!bg-white hover:!text-[hsl(var(--ink))]" data-testid="cta-sell">
              Продай автомобил
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
