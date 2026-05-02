import React, { useEffect } from "react";
import { useTranslation } from "react-i18next";
import InfoPage, { InfoSection, FAQItem } from "../components/InfoPage";
import MarkdownBody from "../components/MarkdownBody";
import HtmlBody from "../components/HtmlBody";
import { useSiteSettings, pickCmsContent, pickCmsHtml } from "../lib/settings";
import { setPageMeta, resetPageMeta, buildBreadcrumbs, buildFaqJsonLd, combineJsonLd } from "../lib/seo";
import { useBrandName } from "../lib/brand";

const DEFAULT_QA = (pct, brand) => [
  { q: "Как да наддавам?", a: `Регистрирайте се, добавете платежен метод за pre-authorization и натиснете „Наддай" на всяка активна обява. При всяко наддаване се блокират ${pct}% от сумата като buyer's premium.` },
  { q: "Какво е pre-authorization?", a: `Това е временно блокиране (не плащане) на ${pct}% от наддаваната сума върху вашата карта. Ако спечелите търга, тези ${pct}% се прилагат като комисионна към ${brand}. Ако не спечелите — сумата се освобождава автоматично в рамките на 5–7 работни дни.` },
  { q: "Какво става, когато наддавам в последните минути?", a: "Ако ново наддаване постъпи по-малко от 2 минути преди края, търгът автоматично се удължава с 2 минути. Така никой не губи автомобил заради мрежови забавяния." },
  { q: "Мога ли да оттегля наддаване?", a: "Не, наддаванията са обвързващи. Подайте оферта само ако сте готови да платите заявената сума." },
  { q: "Колко струва да подам автомобил?", a: "Подаването, промотирането и приключването на обява са абсолютно безплатни за продавачите — без такси, без абонаменти и без скрити комисионни, независимо от изхода на търга." },
  { q: "Колко време отнема одобрение на моята обява?", a: "Нашият редакционен екип преглежда новите заявки в рамките на 48 часа." },
  { q: "Какво става, ако резервната цена не е достигната?", a: "Можете да изберете да приемете най-високата оферта или да изпратите контра-оферта на водещия наддавач." },
];

// Simple markdown-like Q/A extractor: expects "## Question?\nAnswer" pairs
function parseFaqMarkdown(md) {
  if (!md) return [];
  const lines = md.split(/\r?\n/);
  const pairs = [];
  let currentQ = null;
  let currentA = [];
  for (const line of lines) {
    const h = line.match(/^#{1,3}\s+(.+)$/);
    if (h) {
      if (currentQ) pairs.push({ q: currentQ, a: currentA.join(" ").trim() });
      currentQ = h[1].trim();
      currentA = [];
    } else if (currentQ) {
      if (line.trim()) currentA.push(line.trim());
    }
  }
  if (currentQ) pairs.push({ q: currentQ, a: currentA.join(" ").trim() });
  return pairs.filter((p) => p.a);
}

export default function FAQPage() {
  const { i18n } = useTranslation();
  const brand = useBrandName();
  const settings = useSiteSettings();
  const html = pickCmsHtml(settings, "faq", i18n.language);
  const custom = pickCmsContent(settings, "faq_content", i18n.language);
  const pct = settings?.buyer_fee_pct ?? 2;

  const qa = custom ? parseFaqMarkdown(custom) : DEFAULT_QA(pct, brand);

  useEffect(() => {
    const url = window.location.origin + "/faq";
    const origin = window.location.origin;
    const breadcrumbs = buildBreadcrumbs([
      { name: "Начало", url: origin + "/" },
      { name: "Често задавани въпроси", url },
    ]);
    const faq = buildFaqJsonLd(qa);
    setPageMeta({
      title: `Често задавани въпроси — ${brand}`,
      description: `Отговори на най-честите въпроси за наддаването, продаването и сделките в ${brand}.`,
      url,
      jsonLd: combineJsonLd(faq, breadcrumbs),
    });
    return () => resetPageMeta();
  }, [qa.length, pct, brand]);

  return (
    <InfoPage overline="Помощ" title="Често задавани въпроси">
      {html ? (
        <HtmlBody html={html} />
      ) : custom ? (
        <MarkdownBody>{custom}</MarkdownBody>
      ) : (
        <>
          <p className="text-lg text-[hsl(var(--ink-muted))]">
            Отговори на най-честите въпроси за наддаването, продаването и сделките в {brand}.
          </p>
          <InfoSection title="Наддаване">
            {DEFAULT_QA(pct, brand).slice(0, 4).map((it, i) => (
              <FAQItem key={i} q={it.q} a={it.a} />
            ))}
          </InfoSection>
          <InfoSection title="Продаване">
            {DEFAULT_QA(pct, brand).slice(4).map((it, i) => (
              <FAQItem key={i} q={it.q} a={it.a} />
            ))}
          </InfoSection>
        </>
      )}
    </InfoPage>
  );
}
