import React from "react";
import { Link } from "react-router-dom";
import { Shield, FileCheck, Gavel, Sparkles, TrendingUp, Camera, Users, Award } from "lucide-react";

export default function HowItWorksPage() {
  return (
    <main data-testid="how-it-works-page">
      <section className="rule-b">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-20 lg:py-28 text-center">
          <div className="overline text-[hsl(var(--accent))]">Прозрачни търгове</div>
          <h1 className="hero-headline text-5xl lg:text-7xl mt-5">
            Наддаване, както<br/><em>трябва да бъде.</em>
          </h1>
          <p className="mt-8 text-lg text-[hsl(var(--ink-muted))] max-w-2xl mx-auto leading-relaxed">
            AutoBid.bg съчетава редакционния подход на американския Bring a Trailer с българската автомобилна общност.
          </p>
        </div>
      </section>

      <section className="rule-b bg-[hsl(var(--surface))]">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-0 border border-[hsl(var(--line))] bg-white">
            {[
              { n: "01", i: Shield, t: "Регистрация", d: "Създайте безплатен акаунт. Потвърждаваме самоличността с кратка верификация преди първата наддавка." },
              { n: "02", i: FileCheck, t: "Проучване", d: "Всеки автомобил преминава фото отчет от 60+ снимки, независима техническа проверка и VIN декодиране." },
              { n: "03", i: Gavel, t: "Наддаване", d: "Седемдневен онлайн търг. Последните 2 минути автоматично удължават продължителността при нова наддавка." },
              { n: "04", i: Sparkles, t: "Финализиране", d: "Свързваме победителя с продавача. Помощ за плащане, транспорт и регистрация — всичко на едно място." },
            ].map((s, i) => (
              <div key={i} className="p-10 rule-b md:border-r md:border-[hsl(var(--line))] md:[&:nth-child(2n)]:border-r-0 md:[&:nth-last-child(-n+2)]:border-b-0">
                <div className="font-mono text-xs text-[hsl(var(--accent))]">{s.n}</div>
                <s.i size={28} className="mt-4 text-[hsl(var(--ink))]" />
                <h3 className="font-serif text-2xl mt-5">{s.t}</h3>
                <p className="mt-3 text-sm text-[hsl(var(--ink-muted))] leading-relaxed">{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rule-b">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16 lg:py-24">
          <div className="overline text-[hsl(var(--accent))]">Такси</div>
          <h2 className="font-serif text-3xl lg:text-5xl mt-3">Проста структура на таксите</h2>
          <div className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-0 border border-[hsl(var(--line))]">
            <div className="p-8 border-b md:border-b-0 md:border-r border-[hsl(var(--line))]">
              <div className="overline text-[hsl(var(--ink-muted))]">Купувач</div>
              <div className="font-serif text-5xl mt-3">2%</div>
              <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Buyer's premium при спечелен търг. 2% pre-authorization се блокира при всяка наддавка и се прилага като комисионна при победа.</p>
            </div>
            <div className="p-8 border-b md:border-b-0 md:border-r border-[hsl(var(--line))]">
              <div className="overline text-[hsl(var(--ink-muted))]">Продавач</div>
              <div className="font-serif text-5xl mt-3">€0</div>
              <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Безплатно публикуване, одобрение, промотиране и финализиране на обявата — независимо от изхода на търга.</p>
            </div>
            <div className="p-8">
              <div className="overline text-[hsl(var(--ink-muted))]">Неуспешен търг</div>
              <div className="font-serif text-5xl mt-3">€0</div>
              <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Нулева такса, ако не бъде достигната резервната цена или при отказ на сделка.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-[hsl(var(--ink))] text-white">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-20 flex flex-col md:flex-row items-center justify-between gap-8">
          <h2 className="hero-headline text-4xl lg:text-5xl">Готов за първата наддавка?</h2>
          <Link to="/register" className="btn !border-white bg-white !text-[hsl(var(--ink))] hover:!bg-[hsl(var(--accent))] hover:!text-white hover:!border-[hsl(var(--accent))]">Създай акаунт</Link>
        </div>
      </section>
    </main>
  );
}
