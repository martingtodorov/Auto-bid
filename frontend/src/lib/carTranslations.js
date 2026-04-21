/**
 * Static translations for short vehicle-data enum values stored in the database
 * in Bulgarian. We don't migrate the DB — instead we translate on the fly when
 * rendering, falling back to the raw value if a term isn't in the dictionary.
 *
 * Covers: fuels, transmissions, body_types, colours, regions.
 * Extend the maps when new raw values appear in /api/auctions/facets.
 */

const FUELS = {
  "Бензин":        { ro: "Benzină",     en: "Petrol" },
  "Дизел":         { ro: "Diesel",      en: "Diesel" },
  "Хибрид":        { ro: "Hibrid",      en: "Hybrid" },
  "Plug-in хибрид": { ro: "Plug-in hibrid", en: "Plug-in hybrid" },
  "Електричество": { ro: "Electric",    en: "Electric" },
  "Електрически":  { ro: "Electric",    en: "Electric" },
  "Газ/Бензин":    { ro: "GPL/Benzină", en: "LPG/Petrol" },
  "Метан":         { ro: "Metan",       en: "CNG" },
};

const TRANSMISSIONS = {
  "Автоматик":    { ro: "Automată",   en: "Automatic" },
  "Автоматична":  { ro: "Automată",   en: "Automatic" },
  "Ръчна":        { ro: "Manuală",    en: "Manual" },
  "Полуавтоматична": { ro: "Semi-automată", en: "Semi-automatic" },
  "Tiptronic":    { ro: "Tiptronic",  en: "Tiptronic" },
  "Робот":        { ro: "Robotizată", en: "Automated" },
  "Вариатор":     { ro: "Variator CVT", en: "CVT" },
};

const BODY_TYPES = {
  "Седан":      { ro: "Sedan",      en: "Sedan" },
  "Комби":      { ro: "Break",      en: "Estate" },
  "Хечбек":     { ro: "Hatchback",  en: "Hatchback" },
  "Купе":       { ro: "Coupe",      en: "Coupe" },
  "Кабрио":     { ro: "Cabrio",     en: "Convertible" },
  "Кабриолет":  { ro: "Cabrio",     en: "Convertible" },
  "Джип":       { ro: "SUV",        en: "SUV" },
  "SUV":        { ro: "SUV",        en: "SUV" },
  "Офроуд":     { ro: "Off-road",   en: "Off-road" },
  "Ван":        { ro: "Van",        en: "Van" },
  "Миниван":    { ro: "Monovolum",  en: "Minivan" },
  "Пикап":      { ro: "Pick-up",    en: "Pickup" },
  "Лимузина":   { ro: "Limuzină",   en: "Limousine" },
  "Родстер":    { ro: "Roadster",   en: "Roadster" },
};

const COLOURS = {
  "Бял": { ro: "Alb", en: "White" },
  "Черен": { ro: "Negru", en: "Black" },
  "Сив": { ro: "Gri", en: "Grey" },
  "Сребрист": { ro: "Argintiu", en: "Silver" },
  "Червен": { ro: "Roșu", en: "Red" },
  "Син": { ro: "Albastru", en: "Blue" },
  "Зелен": { ro: "Verde", en: "Green" },
  "Жълт": { ro: "Galben", en: "Yellow" },
  "Оранжев": { ro: "Portocaliu", en: "Orange" },
  "Кафяв": { ro: "Maro", en: "Brown" },
  "Бежов": { ro: "Bej", en: "Beige" },
  "Златист": { ro: "Auriu", en: "Gold" },
  "Графит": { ro: "Grafit", en: "Graphite" },
  "Тъмно син": { ro: "Albastru închis", en: "Dark blue" },
  "Тъмно сив": { ro: "Gri închis", en: "Dark grey" },
};

// Bulgarian administrative regions / oblasti.
const REGIONS = {
  "София": { ro: "Sofia", en: "Sofia" },
  "София (град)": { ro: "Sofia (oraș)", en: "Sofia (city)" },
  "Пловдив": { ro: "Plovdiv", en: "Plovdiv" },
  "Варна": { ro: "Varna", en: "Varna" },
  "Бургас": { ro: "Burgas", en: "Burgas" },
  "Русе": { ro: "Ruse", en: "Ruse" },
  "Стара Загора": { ro: "Stara Zagora", en: "Stara Zagora" },
  "Плевен": { ro: "Pleven", en: "Pleven" },
  "Сливен": { ro: "Sliven", en: "Sliven" },
  "Добрич": { ro: "Dobrici", en: "Dobrich" },
  "Шумен": { ro: "Shumen", en: "Shumen" },
  "Перник": { ro: "Pernik", en: "Pernik" },
  "Хасково": { ro: "Haskovo", en: "Haskovo" },
  "Ямбол": { ro: "Yambol", en: "Yambol" },
  "Пазарджик": { ro: "Pazardjik", en: "Pazardzhik" },
  "Благоевград": { ro: "Blagoevgrad", en: "Blagoevgrad" },
  "Велико Търново": { ro: "Veliko Tarnovo", en: "Veliko Tarnovo" },
  "Враца": { ro: "Vratsa", en: "Vratsa" },
  "Габрово": { ro: "Gabrovo", en: "Gabrovo" },
  "Кърджали": { ro: "Kardjali", en: "Kardzhali" },
  "Кюстендил": { ro: "Kyustendil", en: "Kyustendil" },
  "Ловеч": { ro: "Lovech", en: "Lovech" },
  "Монтана": { ro: "Montana", en: "Montana" },
  "Разград": { ro: "Razgrad", en: "Razgrad" },
  "Силистра": { ro: "Silistra", en: "Silistra" },
  "Смолян": { ro: "Smolyan", en: "Smolyan" },
  "Търговище": { ro: "Targovishte", en: "Targovishte" },
};

const DICTIONARIES = {
  fuel: FUELS,
  transmission: TRANSMISSIONS,
  body_type: BODY_TYPES,
  colour: COLOURS,
  color: COLOURS,
  region: REGIONS,
  city: REGIONS,
};

/** Translate a single enum value. Returns the raw value when no mapping exists. */
export function translateEnum(value, kind, lng = "bg") {
  if (!value) return "";
  const lang = (lng || "bg").slice(0, 2);
  if (lang === "bg") return value;
  const dict = DICTIONARIES[kind];
  const entry = dict ? dict[value] : null;
  return (entry && entry[lang]) || value;
}
