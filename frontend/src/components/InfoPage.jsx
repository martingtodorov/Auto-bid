import React from "react";

export default function InfoPage({ title, overline, children }) {
  return (
    <main className="rule-b" data-testid={`info-${(overline || title).toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="max-w-[900px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        {overline && <div className="overline text-[hsl(var(--accent))]">{overline}</div>}
        <h1 className="font-serif text-4xl lg:text-5xl tracking-tight mt-3">{title}</h1>
        <div className="mt-10 space-y-8 text-[15px] leading-[1.75] text-[hsl(var(--ink))]/90">
          {children}
        </div>
      </div>
    </main>
  );
}

export function InfoSection({ title, children }) {
  return (
    <section>
      <h2 className="font-serif text-2xl lg:text-3xl mt-2 tracking-tight">{title}</h2>
      <div className="mt-4 space-y-3">
        {children}
      </div>
    </section>
  );
}

export function FAQItem({ q, a }) {
  return (
    <details className="rounded-card border border-[hsl(var(--line))] bg-white p-5 group">
      <summary className="cursor-pointer list-none flex items-center justify-between gap-4">
        <span className="font-semibold text-base">{q}</span>
        <span className="text-[hsl(var(--accent))] text-xl group-open:rotate-45 transition-transform">+</span>
      </summary>
      <div className="mt-3 text-[hsl(var(--ink))]/80 leading-relaxed">{a}</div>
    </details>
  );
}
