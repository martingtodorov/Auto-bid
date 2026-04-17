import React from "react";
import InfoPage, { InfoSection } from "../components/InfoPage";

export default function FeesPage() {
  return (
    <InfoPage overline="Помощ" title="Такси и комисионни">
      <p className="text-lg text-[hsl(var(--ink-muted))]">
        Прозрачни условия за всички страни. Без скрити такси.
      </p>

      <InfoSection title="За купувачи">
        <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6">
          <div className="overline text-[hsl(var(--accent))]">Buyer's premium</div>
          <div className="font-serif text-4xl mt-2">2%</div>
          <p className="mt-3 text-[hsl(var(--ink-muted))]">
            Върху финалната цена. Блокират се при всяка наддавка и се удържат само при печалба. При загуба — пълно освобождаване.
          </p>
          <p className="mt-3 text-xs text-[hsl(var(--ink-muted))]">Пример: финална цена €20 000 → комисионна €400 (€20 400 обща стойност на сделката).</p>
        </div>
      </InfoSection>

      <InfoSection title="За продавачи">
        <div className="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-6">
          <div className="overline text-[hsl(var(--accent))]">Безплатно</div>
          <div className="font-serif text-4xl mt-2">0 €</div>
          <p className="mt-3 text-[hsl(var(--ink))]/80 leading-relaxed">
            Никакви такси при публикуване, одобрение, промотиране или финализиране на обявата — независимо от изхода на търга. Без абонамент, без скрити комисионни.
          </p>
          <ul className="mt-4 space-y-1.5 text-sm text-[hsl(var(--ink))]/90">
            <li>✓ Безплатно създаване на обява</li>
            <li>✓ Безплатно поставяне на резервна цена</li>
            <li>✓ Безплатен редакторски преглед от нашия екип</li>
            <li>✓ Безплатно промотиране на заглавната страница</li>
            <li>✓ Без такса при неуспешен търг</li>
          </ul>
        </div>
      </InfoSection>
    </InfoPage>
  );
}
