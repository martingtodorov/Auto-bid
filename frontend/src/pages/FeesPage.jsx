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
        <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6">
          <div className="overline text-[hsl(var(--accent))]">Публикуване</div>
          <div className="font-serif text-4xl mt-2">Безплатно</div>
          <p className="mt-3 text-[hsl(var(--ink-muted))]">
            Не удържаме такса за подаване, одобрение или приключване на обявата, независимо от изхода на търга.
          </p>
        </div>

        <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6 mt-4">
          <div className="overline text-[hsl(var(--accent))]">Резервна цена (по избор)</div>
          <div className="font-serif text-2xl mt-2">0 €</div>
          <p className="mt-3 text-[hsl(var(--ink-muted))]">
            Поставянето на резервна цена е безплатно. Ако резервът не бъде достигнат — нямате задължение да продавате.
          </p>
        </div>
      </InfoSection>

      <InfoSection title="Допълнителни услуги (по избор)">
        <ul className="space-y-2 text-[hsl(var(--ink))]/90">
          <li>• <strong>Професионално фотозаснемане</strong> — от €120 (за София)</li>
          <li>• <strong>Промотиране на заглавна страница</strong> — €39 за 7 дни</li>
        </ul>
        <p className="text-xs text-[hsl(var(--ink-muted))] mt-4">
          За повече информация — свържете се с нашия екип през страницата „Контакти“.
        </p>
      </InfoSection>
    </InfoPage>
  );
}
