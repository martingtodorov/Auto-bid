/**
 * Default HTML съдържания за CMS-управляемите страници.  Използва се от
 * AdminSettingsTab за prefill на празните `<base>_html_<lang>` полета,
 * така че админът да вижда текущото съдържание като стартова точка за
 * редакция, без да го пише от нула.
 *
 * Стойностите се попълват само в локалния form state — НЕ се записват
 * автоматично в Mongo.  Admin трябва да натисне "Запази", за да се
 * персистират.
 *
 * Шаблоните използват плейсхолдъри: {{pct}}, {{min}}, {{max}}, {{brand}}.
 * Заместват се клиентски преди да се поставят в textarea.
 */

const TERMS_BG = `<p class="text-sm text-[hsl(var(--ink-muted))]">Последна актуализация: 15 февруари 2026 г.</p>

<h2>1. Обхват и предмет</h2>
<p>Настоящите общи условия уреждат отношенията между „{{brand}}“ и потребителите — купувачи и продавачи, участващи в онлайн търгове за моторни превозни средства.</p>

<h2>2. Регистрация</h2>
<p>Регистрацията е безплатна. Потребителят гарантира истинността на предоставените лични данни.</p>

<h2>3. Търгове и наддаване</h2>
<p>Всяка активна обява е договорно обвързваща. Наддаването представлява неотменима оферта за покупка на обявената цена плюс {{pct}}% buyer's premium. Pre-authorization от {{pct}}% се блокира на картата на наддавача при всяка нова оферта.</p>

<h2>4. Продавачи и обяви</h2>
<p>Обявите се одобряват от редакцията в рамките на 48 часа. Резервна цена (по избор) не е задължителна.</p>

<h2>5. Сделка и предаване</h2>
<p>Плащането между купувача и продавача се извършва директно — банков превод или ескроу. {{brand}} не съхранява средствата на сделката.</p>

<h2>6. Контакти и спорове</h2>
<p>За въпроси: <a href="mailto:contact@autoandbid.com">contact@autoandbid.com</a>. Компетентен е Софийски районен съд.</p>`;

const FEES_BG = `<p class="text-lg text-[hsl(var(--ink-muted))]">Прозрачни условия за всички страни. Без скрити такси.</p>

<h2>За купувачи</h2>
<div class="rounded-card border border-[hsl(var(--line))] bg-white p-6">
  <div class="overline text-[hsl(var(--accent))]">Buyer's premium</div>
  <div class="font-serif text-4xl mt-2">{{pct}}%</div>
  <p class="mt-3 text-[hsl(var(--ink-muted))]">Върху финалната цена. Минимум €{{min}} / максимум €{{max}} на транзакция. Блокират се при всяка наддавка и се удържат само при печалба.</p>
  <p class="mt-3 text-xs text-[hsl(var(--ink-muted))]">Пример: финална цена €20 000 → комисионна €{{example_fee}}.</p>
</div>

<h2>За продавачи</h2>
<div class="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-6">
  <div class="overline text-[hsl(var(--accent))]">Безплатно</div>
  <div class="font-serif text-4xl mt-2">0 €</div>
  <p class="mt-3 leading-relaxed">Никакви такси при публикуване, одобрение, промотиране или финализиране на обявата.</p>
</div>`;

const FAQ_BG = `<p class="text-lg text-[hsl(var(--ink-muted))]">Отговори на най-честите въпроси за наддаването, продаването и сделките в {{brand}}.</p>

<h2>Наддаване</h2>

<h3>Как да наддавам?</h3>
<p>Регистрирайте се, добавете платежен метод за pre-authorization и натиснете „Наддай" на всяка активна обява. При всяка наддавка се блокират {{pct}}% от сумата като buyer's premium.</p>

<h3>Какво е pre-authorization?</h3>
<p>Това е временно блокиране (не плащане) на {{pct}}% от наддаваната сума върху вашата карта. Ако спечелите търга, тези {{pct}}% се прилагат като комисионна към {{brand}}. Ако не спечелите — сумата се освобождава автоматично в рамките на 5–7 работни дни.</p>

<h3>Какво става, когато наддавам в последните минути?</h3>
<p>Ако нова наддавка постъпи по-малко от 2 минути преди края, търгът автоматично се удължава с 2 минути. Така никой не губи автомобил заради мрежови забавяния.</p>

<h3>Мога ли да оттегля наддавка?</h3>
<p>Не, наддаванията са обвързващи. Подайте оферта само ако сте готови да платите заявената сума.</p>

<h2>Продаване</h2>

<h3>Колко струва да подам автомобил?</h3>
<p>Подаването, промотирането и приключването на обява са абсолютно безплатни за продавачите — без такси, без абонаменти и без скрити комисионни, независимо от изхода на търга.</p>

<h3>Колко време отнема одобрение на моята обява?</h3>
<p>Нашият редакционен екип преглежда новите заявки в рамките на 48 часа.</p>

<h3>Какво става, ако резервната цена не е достигната?</h3>
<p>Можете да изберете да приемете най-високата оферта или да изпратите контра-оферта на водещия наддавач.</p>`;

const CONTACTS_BG = `<p class="text-lg text-[hsl(var(--ink-muted))]">Нашият екип отговаря в рамките на 1 работен ден.</p>

<div class="grid grid-cols-1 md:grid-cols-2 gap-5">
  <a href="mailto:contact@autoandbid.com" class="block rounded-card border border-[hsl(var(--line))] bg-white p-5 transition hover:border-[hsl(var(--accent))]">
    <div class="overline text-[hsl(var(--ink-muted))]">Имейл</div>
    <div class="mt-3 font-serif text-xl">contact@autoandbid.com</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">За общи запитвания и поддръжка</div>
  </a>
  <a href="tel:+359878279269" class="block rounded-card border border-[hsl(var(--line))] bg-white p-5 transition hover:border-[hsl(var(--accent))]">
    <div class="overline text-[hsl(var(--ink-muted))]">Телефон</div>
    <div class="mt-3 font-serif text-xl">+359 87 827 9269</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">Понеделник–Петък · 10:00–17:00</div>
  </a>
  <a href="https://www.google.com/maps/search/?api=1&amp;query=ул.+Карнеги+11А,+София" target="_blank" rel="noopener noreferrer" class="block rounded-card border border-[hsl(var(--line))] bg-white p-5 transition hover:border-[hsl(var(--accent))]">
    <div class="overline text-[hsl(var(--ink-muted))]">Адрес</div>
    <div class="mt-3 font-serif text-xl">ул. Карнеги 11А, София, България</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">Отвори в Google Maps · срещи по предварителна уговорка</div>
  </a>
  <div class="block rounded-card border border-[hsl(var(--line))] bg-white p-5">
    <div class="overline text-[hsl(var(--ink-muted))]">Работно време</div>
    <div class="mt-3 font-serif text-xl">Пн–Пт: 10:00–17:00</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">Събота и неделя — почивни</div>
  </div>
</div>

<h2>Специализирани запитвания</h2>
<div class="grid grid-cols-1 md:grid-cols-2 gap-5">
  <div class="rounded-card border border-[hsl(var(--line))] bg-white p-5">
    <div class="overline text-[hsl(var(--accent))]">Партньорства и дилъри</div>
    <p class="mt-2 text-sm">Интересувате се от статус „Проверен дилър" или обемна продажба?</p>
    <a href="mailto:contact@autoandbid.com" class="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))]">contact@autoandbid.com →</a>
  </div>
  <div class="rounded-card border border-[hsl(var(--line))] bg-white p-5">
    <div class="overline text-[hsl(var(--accent))]">Преса и медии</div>
    <p class="mt-2 text-sm">За интервюта, доклади и статистики.</p>
    <a href="mailto:contact@autoandbid.com" class="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))]">contact@autoandbid.com →</a>
  </div>
</div>`;

const HOW_IT_WORKS_BG = `<p class="text-lg text-[hsl(var(--ink-muted))]">Прозрачен и справедлив процес от подаване до връчване на ключовете.</p>

<h2>Как работи търгът</h2>
<ol>
  <li><strong>Подаване</strong> — Продавачите попълват подробна форма с минимум 60 снимки, технически данни и история. Подаването е безплатно.</li>
  <li><strong>Редакторски преглед</strong> — Нашият екип одобрява обявата в рамките на 48 часа, проверява документи и снимки.</li>
  <li><strong>Активен търг</strong> — Обявите вървят 7 дни. Купувачите наддават с {{pct}}% pre-authorization върху всяка оферта.</li>
  <li><strong>Сделката</strong> — Победителят и продавачът се свързват директно. Плащането и доставката се уговарят между тях.</li>
</ol>

<h2>Логика на наддаване</h2>
<p>{{brand}} следва принципи за честно и прозрачно наддаване:</p>
<ul>
  <li><strong>Проверени наддавачи</strong> — Всеки наддавач преминава KYC (имейл + телефон + карта).</li>
  <li><strong>Pre-authorization</strong> — При всяка наддавка се блокират {{pct}}% от сумата (мин. €150 / макс. €4 000).</li>
  <li><strong>Динамичен бид</strong> — Стъпката нараства спрямо текущата цена (€50 → €5 000).</li>
  <li><strong>Auto-extend</strong> — Наддавка в последните 2 минути удължава търга с още 2 минути.</li>
  <li><strong>Резервна цена</strong> (по избор) — Минимална цена, под която продавачът не е длъжен да продаде.</li>
  <li><strong>Контра-оферти</strong> — Ако резервата не е достигната, продавачът може да договори с лидера.</li>
  <li><strong>Обвързваща оферта</strong> — Подадените наддавки не могат да се оттеглят.</li>
  <li><strong>Прозрачна история</strong> — Всички наддавки и коментари остават публични за рефериране.</li>
</ul>

<h2>Такси</h2>
<table class="w-full border border-[hsl(var(--line))]">
  <thead>
    <tr>
      <th class="p-3 text-left">Страна</th>
      <th class="p-3 text-left">Такса</th>
      <th class="p-3 text-left">Бележки</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="p-3 border-t border-[hsl(var(--line))]">Купувачи</td>
      <td class="p-3 border-t border-[hsl(var(--line))]"><strong>{{pct}}%</strong></td>
      <td class="p-3 border-t border-[hsl(var(--line))]">Buyer's premium върху финалната цена.</td>
    </tr>
    <tr>
      <td class="p-3 border-t border-[hsl(var(--line))]">Продавачи</td>
      <td class="p-3 border-t border-[hsl(var(--line))]"><strong>€0</strong></td>
      <td class="p-3 border-t border-[hsl(var(--line))]">Безплатно — публикуване, одобрение и финализиране.</td>
    </tr>
    <tr>
      <td class="p-3 border-t border-[hsl(var(--line))]">Неуспешен търг</td>
      <td class="p-3 border-t border-[hsl(var(--line))]"><strong>€0</strong></td>
      <td class="p-3 border-t border-[hsl(var(--line))]">Ако обявата не достигне резервата — никакви такси.</td>
    </tr>
  </tbody>
</table>`;

// Шаблоните за всеки base+lang.  RO/EN са съзнателно празни — админът
// може да ги попълни ръчно или да копира BG като starting point.
const TEMPLATES = {
  terms: { bg: TERMS_BG, ro: "", en: "" },
  fees: { bg: FEES_BG, ro: "", en: "" },
  faq: { bg: FAQ_BG, ro: "", en: "" },
  contacts: { bg: CONTACTS_BG, ro: "", en: "" },
  how_it_works: { bg: HOW_IT_WORKS_BG, ro: "", en: "" },
};

/**
 * Връща default HTML за дадения CMS base + език с попълнени плейсхолдъри.
 * @param {string} base - "terms" | "fees" | "faq" | "contacts" | "how_it_works"
 * @param {string} lang - "bg" | "ro" | "en"
 * @param {object} ctx - { pct, min, max, brand }
 */
export function getDefaultCmsHtml(base, lang, ctx = {}) {
  const tpl = TEMPLATES[base]?.[lang] || "";
  if (!tpl) return "";
  const pct = ctx.pct ?? 2;
  const min = ctx.min ?? 150;
  const max = ctx.max ?? 4000;
  const brand = ctx.brand ?? "Auto&Bid";
  const exampleFee = Math.min(max, Math.max(min, Math.round(20000 * pct / 100)));
  return tpl
    .replace(/\{\{pct\}\}/g, pct)
    .replace(/\{\{min\}\}/g, min)
    .replace(/\{\{max\}\}/g, max)
    .replace(/\{\{brand\}\}/g, brand)
    .replace(/\{\{example_fee\}\}/g, exampleFee);
}

export const CMS_DEFAULT_BASES = ["terms", "fees", "faq", "contacts", "how_it_works"];
