import React from "react";
import InfoPage, { InfoSection, FAQItem } from "../components/InfoPage";
import MarkdownBody from "../components/MarkdownBody";
import { useSiteSettings } from "../lib/settings";

export default function FAQPage() {
  const settings = useSiteSettings();
  const custom = settings?.faq_content?.trim();

  return (
    <InfoPage overline="Помощ" title="Често задавани въпроси">
      {custom ? (
        <MarkdownBody>{custom}</MarkdownBody>
      ) : (
        <DefaultFAQ pct={settings?.buyer_fee_pct ?? 2} />
      )}
    </InfoPage>
  );
}

function DefaultFAQ({ pct }) {
  return (
    <>
      <p className="text-lg text-[hsl(var(--ink-muted))]">
        Отговори на най-честите въпроси за наддаването, продаването и сделките в AutoBid.bg.
      </p>
      <InfoSection title="Наддаване">
        <FAQItem q="Как да наддавам?" a={`Регистрирайте се, добавете платежен метод за pre-authorization и натиснете „Наддай“ на всяка активна обява. При всяка наддавка се блокират ${pct}% от сумата като buyer's premium.`} />
        <FAQItem q="Какво е pre-authorization?" a={`Това е временно блокиране (не плащане) на ${pct}% от наддаваната сума върху вашата карта. Ако спечелите търга, тези ${pct}% се прилагат като комисионна към AutoBid.bg. Ако не спечелите — сумата се освобождава автоматично в рамките на 5–7 работни дни.`} />
        <FAQItem q="Какво става, когато наддавам в последните минути?" a="Ако нова наддавка постъпи по-малко от 2 минути преди края, търгът автоматично се удължава с 2 минути. Така никой не губи автомобил заради мрежови забавяния." />
        <FAQItem q="Мога ли да оттегля наддавка?" a="Не, наддаванията са обвързващи. Подайте оферта само ако сте готови да платите заявената сума." />
      </InfoSection>
      <InfoSection title="Продаване">
        <FAQItem q="Колко струва да подам автомобил?" a="Подаването, промотирането и приключването на обява са абсолютно безплатни за продавачите — без такси, без абонаменти и без скрити комисионни, независимо от изхода на търга." />
        <FAQItem q="Колко време отнема одобрение на моята обява?" a="Нашият редакционен екип преглежда новите заявки в рамките на 48 часа." />
        <FAQItem q="Какво става, ако резервната цена не е достигната?" a="Можете да изберете да приемете най-високата оферта или да изпратите контра-оферта на водещия наддавач." />
      </InfoSection>
    </>
  );
}
