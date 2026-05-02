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
  <p class="mt-3 text-[hsl(var(--ink-muted))]">Върху финалната цена. Минимум €{{min}} / максимум €{{max}} на транзакция. Блокират се при всяко наддаване и се удържат само при печалба.</p>
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
<p>Регистрирайте се, добавете платежен метод за pre-authorization и натиснете „Наддай" на всяка активна обява. При всяко наддаване се блокират {{pct}}% от сумата като buyer's premium.</p>

<h3>Какво е pre-authorization?</h3>
<p>Това е временно блокиране (не плащане) на {{pct}}% от наддаваната сума върху вашата карта. Ако спечелите търга, тези {{pct}}% се прилагат като комисионна към {{brand}}. Ако не спечелите — сумата се освобождава автоматично в рамките на 5–7 работни дни.</p>

<h3>Какво става, когато наддавам в последните минути?</h3>
<p>Ако ново наддаване постъпи по-малко от 2 минути преди края, търгът автоматично се удължава с 2 минути. Така никой не губи автомобил заради мрежови забавяния.</p>

<h3>Мога ли да оттегля наддаване?</h3>
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
  <li><strong>Pre-authorization</strong> — При всяко наддаване се блокират {{pct}}% от сумата (мин. €150 / макс. €4 000).</li>
  <li><strong>Динамичен бид</strong> — Стъпката нараства спрямо текущата цена (€50 → €5 000).</li>
  <li><strong>Auto-extend</strong> — Наддавка в последните 2 минути удължава търга с още 2 минути.</li>
  <li><strong>Резервна цена</strong> (по избор) — Минимална цена, под която продавачът не е длъжен да продаде.</li>
  <li><strong>Контра-оферти</strong> — Ако резервата не е достигната, продавачът може да договори с лидера.</li>
  <li><strong>Обвързваща оферта</strong> — Подадените наддавания не могат да се оттеглят.</li>
  <li><strong>Прозрачна история</strong> — Всички наддавания и коментари остават публични за рефериране.</li>
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

// Шаблоните за всеки base+lang.
// BG = пълен mirror на текущия React default
// EN/RO = превод на същия default, за да може админът да ги редактира
//         директно през полетата без да започва от празен лист.
const TERMS_EN = `<p class="text-sm text-[hsl(var(--ink-muted))]">Last updated: 15 February 2026.</p>

<h2>1. Scope and subject</h2>
<p>These terms govern the relationship between "{{brand}}" and its users — buyers and sellers participating in online auctions for motor vehicles.</p>

<h2>2. Registration</h2>
<p>Registration is free of charge. The user warrants the accuracy of the personal data provided.</p>

<h2>3. Auctions and bidding</h2>
<p>Every active listing is contractually binding. A bid is a non-revocable offer to purchase at the stated price plus a {{pct}}% buyer's premium. A {{pct}}% pre-authorization is held on the bidder's card with each new offer.</p>

<h2>4. Sellers and listings</h2>
<p>Listings are reviewed by our editorial team within 48 hours. A reserve price (optional) is not mandatory.</p>

<h2>5. Settlement and delivery</h2>
<p>Payment between buyer and seller is direct — bank transfer or escrow. {{brand}} does not hold the transaction funds.</p>

<h2>6. Contact and disputes</h2>
<p>Questions: <a href="mailto:contact@autoandbid.com">contact@autoandbid.com</a>. The competent court is the Sofia District Court.</p>`;

const TERMS_RO = `<p class="text-sm text-[hsl(var(--ink-muted))]">Ultima actualizare: 15 februarie 2026.</p>

<h2>1. Obiect și domeniu de aplicare</h2>
<p>Prezentele condiții generale reglementează relațiile dintre „{{brand}}" și utilizatori — cumpărători și vânzători care participă la licitații online pentru autovehicule.</p>

<h2>2. Înregistrare</h2>
<p>Înregistrarea este gratuită. Utilizatorul garantează corectitudinea datelor personale furnizate.</p>

<h2>3. Licitații și ofertare</h2>
<p>Fiecare anunț activ este obligatoriu din punct de vedere contractual. Oferta reprezintă o propunere irevocabilă de cumpărare la prețul afișat plus {{pct}}% comision pentru cumpărător. Pre-autorizarea de {{pct}}% este blocată pe cardul ofertantului la fiecare nouă ofertă.</p>

<h2>4. Vânzători și anunțuri</h2>
<p>Anunțurile sunt aprobate de redacție în termen de 48 de ore. Prețul de rezervă (opțional) nu este obligatoriu.</p>

<h2>5. Tranzacție și predare</h2>
<p>Plata între cumpărător și vânzător se face direct — transfer bancar sau escrow. {{brand}} nu păstrează fondurile tranzacției.</p>

<h2>6. Contact și dispute</h2>
<p>Întrebări: <a href="mailto:contact@autoandbid.com">contact@autoandbid.com</a>. Instanța competentă este Tribunalul Districtual Sofia.</p>`;

const FEES_EN = `<p class="text-lg text-[hsl(var(--ink-muted))]">Transparent terms for everyone. No hidden fees.</p>

<h2>For buyers</h2>
<div class="rounded-card border border-[hsl(var(--line))] bg-white p-6">
  <div class="overline text-[hsl(var(--accent))]">Buyer's premium</div>
  <div class="font-serif text-4xl mt-2">{{pct}}%</div>
  <p class="mt-3 text-[hsl(var(--ink-muted))]">On the final price. Min €{{min}} / max €{{max}} per transaction. Held on every bid, charged only on a winning bid.</p>
  <p class="mt-3 text-xs text-[hsl(var(--ink-muted))]">Example: final price €20,000 → commission €{{example_fee}}.</p>
</div>

<h2>For sellers</h2>
<div class="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-6">
  <div class="overline text-[hsl(var(--accent))]">Free</div>
  <div class="font-serif text-4xl mt-2">€0</div>
  <p class="mt-3 leading-relaxed">No fees for listing, approval, promotion or finalization.</p>
</div>`;

const FEES_RO = `<p class="text-lg text-[hsl(var(--ink-muted))]">Condiții transparente pentru toți. Fără taxe ascunse.</p>

<h2>Pentru cumpărători</h2>
<div class="rounded-card border border-[hsl(var(--line))] bg-white p-6">
  <div class="overline text-[hsl(var(--accent))]">Comision cumpărător</div>
  <div class="font-serif text-4xl mt-2">{{pct}}%</div>
  <p class="mt-3 text-[hsl(var(--ink-muted))]">Asupra prețului final. Min €{{min}} / max €{{max}} pe tranzacție. Blocat la fiecare ofertă, perceput doar la câștig.</p>
  <p class="mt-3 text-xs text-[hsl(var(--ink-muted))]">Exemplu: preț final €20.000 → comision €{{example_fee}}.</p>
</div>

<h2>Pentru vânzători</h2>
<div class="rounded-card border border-[hsl(var(--accent))]/30 bg-[hsl(var(--accent-soft))] p-6">
  <div class="overline text-[hsl(var(--accent))]">Gratuit</div>
  <div class="font-serif text-4xl mt-2">€0</div>
  <p class="mt-3 leading-relaxed">Nicio taxă pentru publicare, aprobare, promovare sau finalizare a anunțului.</p>
</div>`;

const FAQ_EN = `<p class="text-lg text-[hsl(var(--ink-muted))]">Answers to the most common questions about bidding, selling and transactions on {{brand}}.</p>

<h2>Bidding</h2>

<h3>How do I bid?</h3>
<p>Register, add a payment method for pre-authorization and click "Bid" on any active listing. Each bid pre-authorizes {{pct}}% of the amount as buyer's premium.</p>

<h3>What is pre-authorization?</h3>
<p>It is a temporary hold (not a charge) of {{pct}}% of the bid amount on your card. If you win the auction, the {{pct}}% is applied as a commission to {{brand}}. If you don't win — the hold is released automatically within 5–7 business days.</p>

<h3>What happens when I bid in the final minutes?</h3>
<p>If a new bid arrives less than 2 minutes before the end, the auction is automatically extended by 2 minutes. So no one loses a car due to network delays.</p>

<h3>Can I retract a bid?</h3>
<p>No, bids are binding. Place a bid only if you're ready to pay the stated amount.</p>

<h2>Selling</h2>

<h3>How much does it cost to list a car?</h3>
<p>Listing, promotion and finalization of a listing are completely free for sellers — no fees, no subscriptions and no hidden commissions, regardless of the auction outcome.</p>

<h3>How long does it take to approve my listing?</h3>
<p>Our editorial team reviews new submissions within 48 hours.</p>

<h3>What if the reserve price isn't met?</h3>
<p>You can choose to accept the highest offer or send a counter-offer to the leading bidder.</p>`;

const FAQ_RO = `<p class="text-lg text-[hsl(var(--ink-muted))]">Răspunsuri la cele mai frecvente întrebări despre licitare, vânzare și tranzacții pe {{brand}}.</p>

<h2>Licitare</h2>

<h3>Cum licitez?</h3>
<p>Înregistrează-te, adaugă o metodă de plată pentru pre-autorizare și apasă „Licitează" pe orice anunț activ. La fiecare ofertă se blochează {{pct}}% din sumă drept comision pentru cumpărător.</p>

<h3>Ce este pre-autorizarea?</h3>
<p>Este o blocare temporară (nu o plată) de {{pct}}% din suma ofertată pe cardul tău. Dacă câștigi licitația, acel {{pct}}% se aplică drept comision către {{brand}}. Dacă nu câștigi — suma este eliberată automat în 5–7 zile lucrătoare.</p>

<h3>Ce se întâmplă când licitez în ultimele minute?</h3>
<p>Dacă o ofertă nouă apare cu mai puțin de 2 minute înainte de final, licitația se extinde automat cu încă 2 minute. Astfel, nimeni nu pierde o mașină din cauza întârzierilor de rețea.</p>

<h3>Pot retrage o ofertă?</h3>
<p>Nu, ofertele sunt obligatorii. Plasează o ofertă doar dacă ești pregătit să plătești suma respectivă.</p>

<h2>Vânzare</h2>

<h3>Cât costă să listez un autovehicul?</h3>
<p>Listarea, promovarea și finalizarea unui anunț sunt complet gratuite pentru vânzători — fără taxe, fără abonamente și fără comisioane ascunse, indiferent de rezultatul licitației.</p>

<h3>Cât durează aprobarea anunțului?</h3>
<p>Echipa noastră editorială revizuiește anunțurile noi în termen de 48 de ore.</p>

<h3>Ce se întâmplă dacă prețul de rezervă nu este atins?</h3>
<p>Poți alege să accepți cea mai mare ofertă sau să trimiți o contra-ofertă ofertantului de top.</p>`;

const CONTACTS_EN = `<p class="text-lg text-[hsl(var(--ink-muted))]">Our team replies within 1 business day.</p>

<div class="grid grid-cols-1 md:grid-cols-2 gap-5">
  <a href="mailto:contact@autoandbid.com" class="block rounded-card border border-[hsl(var(--line))] bg-white p-5 transition hover:border-[hsl(var(--accent))]">
    <div class="overline text-[hsl(var(--ink-muted))]">Email</div>
    <div class="mt-3 font-serif text-xl">contact@autoandbid.com</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">For general inquiries and support</div>
  </a>
  <a href="tel:+359878279269" class="block rounded-card border border-[hsl(var(--line))] bg-white p-5 transition hover:border-[hsl(var(--accent))]">
    <div class="overline text-[hsl(var(--ink-muted))]">Phone</div>
    <div class="mt-3 font-serif text-xl">+359 87 827 9269</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">Monday–Friday · 10:00–17:00</div>
  </a>
  <a href="https://www.google.com/maps/search/?api=1&amp;query=11A+Carnegie+St,+Sofia" target="_blank" rel="noopener noreferrer" class="block rounded-card border border-[hsl(var(--line))] bg-white p-5 transition hover:border-[hsl(var(--accent))]">
    <div class="overline text-[hsl(var(--ink-muted))]">Address</div>
    <div class="mt-3 font-serif text-xl">11A Carnegie St, Sofia, Bulgaria</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">Open in Google Maps · meetings by appointment</div>
  </a>
  <div class="block rounded-card border border-[hsl(var(--line))] bg-white p-5">
    <div class="overline text-[hsl(var(--ink-muted))]">Working hours</div>
    <div class="mt-3 font-serif text-xl">Mon–Fri: 10:00–17:00</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">Saturday and Sunday — closed</div>
  </div>
</div>

<h2>Specialised inquiries</h2>
<div class="grid grid-cols-1 md:grid-cols-2 gap-5">
  <div class="rounded-card border border-[hsl(var(--line))] bg-white p-5">
    <div class="overline text-[hsl(var(--accent))]">Partnerships and dealers</div>
    <p class="mt-2 text-sm">Interested in "Verified dealer" status or bulk sales?</p>
    <a href="mailto:contact@autoandbid.com" class="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))]">contact@autoandbid.com →</a>
  </div>
  <div class="rounded-card border border-[hsl(var(--line))] bg-white p-5">
    <div class="overline text-[hsl(var(--accent))]">Press and media</div>
    <p class="mt-2 text-sm">For interviews, reports and statistics.</p>
    <a href="mailto:contact@autoandbid.com" class="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))]">contact@autoandbid.com →</a>
  </div>
</div>`;

const CONTACTS_RO = `<p class="text-lg text-[hsl(var(--ink-muted))]">Echipa noastră răspunde în termen de 1 zi lucrătoare.</p>

<div class="grid grid-cols-1 md:grid-cols-2 gap-5">
  <a href="mailto:contact@autoandbid.com" class="block rounded-card border border-[hsl(var(--line))] bg-white p-5 transition hover:border-[hsl(var(--accent))]">
    <div class="overline text-[hsl(var(--ink-muted))]">Email</div>
    <div class="mt-3 font-serif text-xl">contact@autoandbid.com</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">Pentru întrebări generale și suport</div>
  </a>
  <a href="tel:+359878279269" class="block rounded-card border border-[hsl(var(--line))] bg-white p-5 transition hover:border-[hsl(var(--accent))]">
    <div class="overline text-[hsl(var(--ink-muted))]">Telefon</div>
    <div class="mt-3 font-serif text-xl">+359 87 827 9269</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">Luni–Vineri · 10:00–17:00</div>
  </a>
  <a href="https://www.google.com/maps/search/?api=1&amp;query=str.+Carnegie+11A,+Sofia" target="_blank" rel="noopener noreferrer" class="block rounded-card border border-[hsl(var(--line))] bg-white p-5 transition hover:border-[hsl(var(--accent))]">
    <div class="overline text-[hsl(var(--ink-muted))]">Adresă</div>
    <div class="mt-3 font-serif text-xl">str. Carnegie 11A, Sofia, Bulgaria</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">Deschide în Google Maps · întâlniri pe bază de programare</div>
  </a>
  <div class="block rounded-card border border-[hsl(var(--line))] bg-white p-5">
    <div class="overline text-[hsl(var(--ink-muted))]">Program</div>
    <div class="mt-3 font-serif text-xl">Lu–Vi: 10:00–17:00</div>
    <div class="mt-1 text-xs text-[hsl(var(--ink-muted))]">Sâmbătă și Duminică — închis</div>
  </div>
</div>

<h2>Întrebări specializate</h2>
<div class="grid grid-cols-1 md:grid-cols-2 gap-5">
  <div class="rounded-card border border-[hsl(var(--line))] bg-white p-5">
    <div class="overline text-[hsl(var(--accent))]">Parteneriate și dealeri</div>
    <p class="mt-2 text-sm">Interesat de statutul „Dealer verificat" sau vânzări în volum?</p>
    <a href="mailto:contact@autoandbid.com" class="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))]">contact@autoandbid.com →</a>
  </div>
  <div class="rounded-card border border-[hsl(var(--line))] bg-white p-5">
    <div class="overline text-[hsl(var(--accent))]">Presă și media</div>
    <p class="mt-2 text-sm">Pentru interviuri, rapoarte și statistici.</p>
    <a href="mailto:contact@autoandbid.com" class="mt-3 inline-block text-sm font-semibold text-[hsl(var(--accent))]">contact@autoandbid.com →</a>
  </div>
</div>`;

const HOW_IT_WORKS_EN = `<p class="text-lg text-[hsl(var(--ink-muted))]">A transparent and fair process from listing to handover of the keys.</p>

<h2>How the auction works</h2>
<ol>
  <li><strong>Submission</strong> — Sellers fill out a detailed form with at least 60 photos, technical specs and history. Submission is free.</li>
  <li><strong>Editorial review</strong> — Our team approves the listing within 48 hours, verifying documents and photos.</li>
  <li><strong>Live auction</strong> — Listings run for 7 days. Buyers bid with a {{pct}}% pre-authorization on every offer.</li>
  <li><strong>The deal</strong> — Winner and seller connect directly. Payment and delivery are arranged between them.</li>
</ol>

<h2>Bidding logic</h2>
<p>{{brand}} follows the principles of fair and transparent bidding:</p>
<ul>
  <li><strong>Verified bidders</strong> — Every bidder undergoes KYC (email + phone + card).</li>
  <li><strong>Pre-authorization</strong> — Each bid pre-authorizes {{pct}}% of the amount (min €150 / max €4,000).</li>
  <li><strong>Dynamic step</strong> — Bid increment scales with current price (€50 → €5,000).</li>
  <li><strong>Auto-extend</strong> — A bid in the last 2 minutes extends the auction by another 2 minutes.</li>
  <li><strong>Reserve price</strong> (optional) — Minimum price below which the seller is not obligated to sell.</li>
  <li><strong>Counter-offers</strong> — If the reserve isn't met, the seller can negotiate with the leader.</li>
  <li><strong>Binding offer</strong> — Bids cannot be retracted.</li>
  <li><strong>Transparent history</strong> — All bids and comments remain public for reference.</li>
</ul>

<h2>Fees</h2>
<table class="w-full border border-[hsl(var(--line))]">
  <thead>
    <tr>
      <th class="p-3 text-left">Party</th>
      <th class="p-3 text-left">Fee</th>
      <th class="p-3 text-left">Notes</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="p-3 border-t border-[hsl(var(--line))]">Buyers</td>
      <td class="p-3 border-t border-[hsl(var(--line))]"><strong>{{pct}}%</strong></td>
      <td class="p-3 border-t border-[hsl(var(--line))]">Buyer's premium on the final price.</td>
    </tr>
    <tr>
      <td class="p-3 border-t border-[hsl(var(--line))]">Sellers</td>
      <td class="p-3 border-t border-[hsl(var(--line))]"><strong>€0</strong></td>
      <td class="p-3 border-t border-[hsl(var(--line))]">Free — listing, approval and finalization.</td>
    </tr>
    <tr>
      <td class="p-3 border-t border-[hsl(var(--line))]">Failed auction</td>
      <td class="p-3 border-t border-[hsl(var(--line))]"><strong>€0</strong></td>
      <td class="p-3 border-t border-[hsl(var(--line))]">If the listing doesn't reach the reserve — no fees.</td>
    </tr>
  </tbody>
</table>`;

const HOW_IT_WORKS_RO = `<p class="text-lg text-[hsl(var(--ink-muted))]">Un proces transparent și echitabil de la listare până la predarea cheilor.</p>

<h2>Cum funcționează licitația</h2>
<ol>
  <li><strong>Trimitere</strong> — Vânzătorii completează un formular detaliat cu minimum 60 de fotografii, date tehnice și istoric. Trimiterea este gratuită.</li>
  <li><strong>Revizie editorială</strong> — Echipa noastră aprobă anunțul în termen de 48 de ore, verificând documentele și fotografiile.</li>
  <li><strong>Licitație activă</strong> — Anunțurile rulează 7 zile. Cumpărătorii ofertează cu pre-autorizare de {{pct}}% la fiecare ofertă.</li>
  <li><strong>Tranzacția</strong> — Câștigătorul și vânzătorul se contactează direct. Plata și livrarea se aranjează între ei.</li>
</ol>

<h2>Logica licitării</h2>
<p>{{brand}} respectă principiile unei licitări corecte și transparente:</p>
<ul>
  <li><strong>Ofertanți verificați</strong> — Fiecare ofertant trece prin KYC (email + telefon + card).</li>
  <li><strong>Pre-autorizare</strong> — La fiecare ofertă se blochează {{pct}}% din sumă (min €150 / max €4.000).</li>
  <li><strong>Pas dinamic</strong> — Creșterea ofertei scalează cu prețul curent (€50 → €5.000).</li>
  <li><strong>Auto-extindere</strong> — O ofertă în ultimele 2 minute extinde licitația cu încă 2 minute.</li>
  <li><strong>Preț de rezervă</strong> (opțional) — Prețul minim sub care vânzătorul nu este obligat să vândă.</li>
  <li><strong>Contra-oferte</strong> — Dacă rezerva nu este atinsă, vânzătorul poate negocia cu liderul.</li>
  <li><strong>Ofertă obligatorie</strong> — Ofertele nu pot fi retrase.</li>
  <li><strong>Istoric transparent</strong> — Toate ofertele și comentariile rămân publice pentru referință.</li>
</ul>

<h2>Taxe</h2>
<table class="w-full border border-[hsl(var(--line))]">
  <thead>
    <tr>
      <th class="p-3 text-left">Parte</th>
      <th class="p-3 text-left">Taxă</th>
      <th class="p-3 text-left">Note</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="p-3 border-t border-[hsl(var(--line))]">Cumpărători</td>
      <td class="p-3 border-t border-[hsl(var(--line))]"><strong>{{pct}}%</strong></td>
      <td class="p-3 border-t border-[hsl(var(--line))]">Comision cumpărător asupra prețului final.</td>
    </tr>
    <tr>
      <td class="p-3 border-t border-[hsl(var(--line))]">Vânzători</td>
      <td class="p-3 border-t border-[hsl(var(--line))]"><strong>€0</strong></td>
      <td class="p-3 border-t border-[hsl(var(--line))]">Gratuit — publicare, aprobare și finalizare.</td>
    </tr>
    <tr>
      <td class="p-3 border-t border-[hsl(var(--line))]">Licitație nereușită</td>
      <td class="p-3 border-t border-[hsl(var(--line))]"><strong>€0</strong></td>
      <td class="p-3 border-t border-[hsl(var(--line))]">Dacă anunțul nu atinge rezerva — nicio taxă.</td>
    </tr>
  </tbody>
</table>`;

const TEMPLATES = {
  terms: { bg: TERMS_BG, ro: TERMS_RO, en: TERMS_EN },
  fees: { bg: FEES_BG, ro: FEES_RO, en: FEES_EN },
  faq: { bg: FAQ_BG, ro: FAQ_RO, en: FAQ_EN },
  contacts: { bg: CONTACTS_BG, ro: CONTACTS_RO, en: CONTACTS_EN },
  how_it_works: { bg: HOW_IT_WORKS_BG, ro: HOW_IT_WORKS_RO, en: HOW_IT_WORKS_EN },
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
