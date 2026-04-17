import React from "react";
import InfoPage, { InfoSection } from "../components/InfoPage";
import MarkdownBody from "../components/MarkdownBody";
import { useSiteSettings } from "../lib/settings";
import { useInfoPageSeo } from "../lib/useInfoPageSeo";

export default function FeesPage() {
  const settings = useSiteSettings();
  const custom = settings?.fees_content?.trim();
  const pct = settings?.buyer_fee_pct ?? 2;
  const min = settings?.buyer_fee_min_eur ?? 150;
  const max = settings?.buyer_fee_max_eur ?? 4000;
  useInfoPageSeo({
    title: "Такси и комисионни — AutoBid.bg",
    description: `AutoBid.bg: ${pct}% buyer's premium (мин. €${min}, макс. €${max}). Безплатно за продавачите — без скрити такси.`,
    path: "/fees",
    crumb: "Такси",
  });
  return (
    <InfoPage overline="Помощ" title="Такси и комисионни">
      {custom ? (
        <MarkdownBody>{custom}</MarkdownBody>
      ) : (
        <DefaultFees pct={pct} min={min} max={max} />
      )}
    </InfoPage>
  );
}

function DefaultFees({ pct, min, max }) {
  return (
    <>
      <p className="text-lg text-[hsl(var(--ink-muted))]">Прозрачни условия за всички страни. Без скрити такси.</p>
      <InfoSection title="За купувачи">
        <div className="rounded-card border border-[hsl(var(--line))] bg-white p-6">
          <div className="overline text-[hsl(var(--accent))]">Buyer's premium</div>
          <div className="font-serif text-4xl mt-2">{pct}%</div>
          <p className="mt-3 text-[hsl(var(--ink-muted))]">Върху финалната цена. Минимум €{min} / максимум €{max} на транзакция. Блокират се при всяка наддавка и се удържат само при печалба.</p>
          <p className="mt-3 text-xs text-[hsl(var(--ink-muted))]">Пример: финална цена €20 000 → комисионна €{Math.min(max, Math.max(min, Math.round(20000 * pct / 100)))}.</p>
        </div>
      </InfoSection>
      <InfoSection title="За продавачи">
        <div className="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-6">
          <div className="overline text-[hsl(var(--accent))]">Безплатно</div>
          <div className="font-serif text-4xl mt-2">0 €</div>
          <p className="mt-3 text-[hsl(var(--ink))]/80 leading-relaxed">Никакви такси при публикуване, одобрение, промотиране или финализиране на обявата.</p>
        </div>
      </InfoSection>
    </>
  );
}
