import React, { useState, useCallback, useEffect } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { Menu, X, User, Search, ChevronDown, Wallet } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/auth";
import { api, formatEUR } from "../lib/apiClient";
import LanguageSwitcher from "./LanguageSwitcher";
import ThemeToggle from "./ThemeToggle";
import NotificationBell from "./NotificationBell";
import { brandTldForLang } from "../i18n";

export default function Nav() {
  const { t, i18n } = useTranslation();
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  const closeMobile = useCallback(() => {
    if (!open || closing) return;
    setClosing(true);
    window.setTimeout(() => {
      setOpen(false);
      setClosing(false);
    }, 240);
  }, [open, closing]);

  const toggleMobile = useCallback(() => {
    if (open) closeMobile();
    else setOpen(true);
  }, [open, closeMobile]);

  // Bidding credits summary — powers the wallet counter at the bottom of
  // the profile dropdown. Refreshed on login/navigate and every 90 s so
  // the displayed available balance stays roughly in sync with bidding
  // activity without hammering Stripe. Polling stops while logged out.
  const [credits, setCredits] = useState(null);
  useEffect(() => {
    if (!user) { setCredits(null); return; }
    let mounted = true;
    const fetchCredits = async () => {
      try {
        const { data } = await api.get("/stripe/authorizations/my-credits");
        if (mounted) setCredits(data);
      } catch (e) { /* silently ignore — counter just hides */ }
    };
    fetchCredits();
    const t = setInterval(fetchCredits, 90_000);
    return () => { mounted = false; clearInterval(t); };
  }, [user]);
  const brandTld = brandTldForLang(i18n.resolvedLanguage || i18n.language);

  // Desktop primary links. `Търгове` is rendered as a dropdown
  // (current auctions + sold) and is handled inline below — it's kept
  // out of this list so we can style the trigger differently. On mobile
  // (`links` is reused further down) we still show each destination as
  // a flat link so nothing is hidden behind a hover state on touch.
  const desktopLinks = [
    { to: "/how-it-works", label: t("footer.how_it_works") },
    { to: "/leaderboard", label: t("nav.leaderboard", "Класация") },
    { to: "/sell", label: t("nav.sell") },
  ];

  const mobileLinks = [
    { to: "/auctions", label: t("nav.auctions") },
    { to: "/how-it-works", label: t("footer.how_it_works") },
    { to: "/sales", label: t("nav.sold") },
    { to: "/leaderboard", label: t("nav.leaderboard", "Класация") },
    { to: "/sell", label: t("nav.sell") },
  ];

  const doSearch = (e) => {
    e.preventDefault();
    if (!q.trim()) return;
    navigate(`/auctions?q=${encodeURIComponent(q.trim())}`);
    setQ("");
  };

  return (
    <header className="sticky top-0 z-50 bg-[hsl(var(--bg))]/85 backdrop-blur-md rule-b" data-testid="main-navigation">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10">
        <div className="flex items-center justify-between h-16 gap-6">
          <Link to="/" className="-m-3 p-3 flex items-center gap-2 shrink-0 mr-2 md:mr-6" data-testid="brand-logo">
            <span className="font-serif text-[26px] sm:text-2xl tracking-tight leading-none">Auto<span className="text-[hsl(var(--accent))]">&amp;</span>Bid<span className="text-[hsl(var(--accent))]">{brandTld}</span></span>
          </Link>

          <nav className="hidden md:flex items-center gap-5 lg:gap-7 shrink-0">
            {/* Търгове dropdown — hover (desktop) reveals Актуални/Продадени.
                The trigger itself links to `/auctions` so keyboard users and
                click-through users still land on the listings page. The
                invisible padding under the trigger keeps the menu open while
                the cursor moves down into the flyout. */}
            <div className="relative group" data-testid="nav-auctions-menu">
              <NavLink
                to="/auctions"
                className={({ isActive }) =>
                  `inline-flex items-center gap-1 text-sm tracking-wide whitespace-nowrap py-2 ${
                    isActive ? "text-[hsl(var(--accent))]" : "text-[hsl(var(--ink))] hover:text-[hsl(var(--accent))]"
                  }`
                }
                data-testid="nav-link-auctions"
              >
                {t("nav.auctions")}
                <ChevronDown size={14} className="opacity-70 group-hover:opacity-100 transition" />
              </NavLink>
              <div className="absolute left-0 top-full pt-2 hidden group-hover:block group-focus-within:block z-40">
                <div className="min-w-[200px] rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] shadow-xl py-1.5">
                  <Link
                    to="/auctions"
                    className="block px-4 py-2 text-sm hover:bg-[hsl(var(--bg))] transition-colors"
                    data-testid="nav-menu-auctions-current"
                  >
                    {t("nav.auctions_current", "Актуални търгове")}
                  </Link>
                  <Link
                    to="/sales"
                    className="block px-4 py-2 text-sm hover:bg-[hsl(var(--bg))] transition-colors"
                    data-testid="nav-menu-auctions-sold"
                  >
                    {t("nav.sold")}
                  </Link>
                </div>
              </div>
            </div>
            {desktopLinks.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  `text-sm tracking-wide whitespace-nowrap ${isActive ? "text-[hsl(var(--accent))]" : "text-[hsl(var(--ink))] hover:text-[hsl(var(--accent))]"}`
                }
                data-testid={`nav-link-${l.to.slice(1)}`}
              >
                {l.label}
              </NavLink>
            ))}
          </nav>

          <form onSubmit={doSearch} className="hidden lg:flex items-center flex-1 max-w-[220px] relative">
            <Search size={14} className="absolute left-3 text-[hsl(var(--accent))]" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("search.placeholder")}
              className="w-full border border-[hsl(var(--accent))]/60 hover:border-[hsl(var(--accent))] focus:border-[hsl(var(--accent))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--accent))]/20 h-9 pl-9 pr-3 text-sm bg-[hsl(var(--surface))] transition-colors"
              data-testid="nav-search-input"
            />
          </form>

          <div className="hidden md:flex items-center gap-3 lg:gap-4 shrink-0">
            <LanguageSwitcher className="hidden lg:inline-flex" />
            <ThemeToggle />
            {user ? (
              <>
                {(user.role === "admin" || user.role === "moderator") && (
                  <Link to="/admin" className="text-sm text-[hsl(var(--accent))] whitespace-nowrap" data-testid="nav-admin">{t("nav.admin")}</Link>
                )}
                <NotificationBell />
                {/* User account dropdown — opens on hover (desktop). The
                    invisible padding underneath the trigger keeps the menu
                    open while the cursor moves down into it. */}
                <div className="relative group" data-testid="nav-user-menu">
                  <Link
                    to="/dashboard"
                    className="flex items-center gap-1.5 text-sm whitespace-nowrap py-2"
                    data-testid="nav-dashboard"
                  >
                    <User size={16} />
                    <span className="max-w-[110px] truncate">{user.name}</span>
                  </Link>
                  <div className="absolute right-0 top-full pt-2 hidden group-hover:block group-focus-within:block z-40">
                    <div className="min-w-[200px] rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] shadow-xl py-1.5">
                      <Link to="/dashboard" className="block px-4 py-2 text-sm hover:bg-[hsl(var(--bg))] transition-colors" data-testid="nav-menu-profile">
                        {t("nav.profile", "Профил")}
                      </Link>
                      <Link to="/my-listings" className="block px-4 py-2 text-sm hover:bg-[hsl(var(--bg))] transition-colors" data-testid="nav-menu-my-listings">
                        {t("nav.my_listings")}
                      </Link>
                      <Link to="/my-bids" className="block px-4 py-2 text-sm hover:bg-[hsl(var(--bg))] transition-colors" data-testid="nav-menu-my-bids">
                        {t("nav.my_bids", "Моите наддавания")}
                      </Link>
                      <Link to="/watchlist" className="block px-4 py-2 text-sm hover:bg-[hsl(var(--bg))] transition-colors" data-testid="nav-menu-watchlist">
                        {t("nav.watchlist")}
                      </Link>
                      <Link to="/settings" className="block px-4 py-2 text-sm hover:bg-[hsl(var(--bg))] transition-colors" data-testid="nav-menu-settings">
                        {t("nav.settings")}
                      </Link>
                      {/* Preauthorization credit — always shown when the
                          endpoint succeeds, even if 0. The summary is
                          the source of truth for bidding power, so users
                          want to see "€0" just as much as a positive
                          number (it confirms they currently have no
                          holds locking up their card). */}
                      {credits && (
                        <>
                          <div className="border-t border-[hsl(var(--line))] my-1" />
                          <Link
                            to="/my-bids"
                            className="block px-4 py-2 hover:bg-[hsl(var(--bg))] transition-colors"
                            data-testid="nav-menu-credits"
                          >
                            <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-[hsl(var(--ink-muted))]">
                              <Wallet size={12} /> {t("nav.credits", "Кредити")}
                            </div>
                            <div className="mt-0.5 text-sm font-semibold tabular-nums">
                              {formatEUR(credits.total_available_eur)}
                              <span className="text-[hsl(var(--ink-muted))] font-normal"> / {formatEUR(credits.total_limit_eur)}</span>
                            </div>
                            <div className="text-[11px] text-[hsl(var(--ink-muted))] mt-0.5">
                              {credits.count > 0
                                ? t("nav.credits_hint", "{{count}} активни авторизации", { count: credits.count })
                                : t("nav.credits_none", "Няма активни авторизации")}
                            </div>
                          </Link>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <button onClick={() => { logout(); navigate("/"); }} className="btn btn-secondary !py-2 !px-3 lg:!px-4 whitespace-nowrap" data-testid="nav-logout">
                  {t("nav.logout")}
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="text-sm whitespace-nowrap" data-testid="nav-login">{t("nav.login")}</Link>
                <Link to="/register" className="btn btn-primary !py-2 !px-4" data-testid="nav-register">{t("nav.register")}</Link>
              </>
            )}
          </div>

          {/* Mobile-only group: bell + hamburger sit close together on the right */}
          <div className="md:hidden flex items-center gap-5">
            {user && <NotificationBell />}
            <button
              className="-m-2 p-2 flex items-center justify-center"
              onClick={toggleMobile}
              data-testid="mobile-menu-toggle"
              aria-label="Menu"
            >
              {open && !closing ? <X size={22} /> : <Menu size={22} />}
            </button>
          </div>
        </div>
      </div>

      {open && (
        <div
          className={`md:hidden rule-t overflow-hidden ${
            closing
              ? "animate-[mobileMenuClose_240ms_cubic-bezier(0.4,0,1,1)_both]"
              : "animate-[mobileMenuOpen_280ms_cubic-bezier(0.22,1,0.36,1)_both]"
          }`}
        >
          <div className="max-w-[1440px] mx-auto px-4 py-4 space-y-3">
            <form onSubmit={(e) => { doSearch(e); closeMobile(); }} className="relative" data-testid="mobile-search-form">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--accent))]" />
              <input
                type="text"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t("search.placeholder")}
                className="w-full border border-[hsl(var(--accent))]/60 focus:border-[hsl(var(--accent))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--accent))]/20 h-10 pl-9 pr-3 text-sm bg-[hsl(var(--surface))]"
                data-testid="mobile-search-input"
              />
            </form>

            <div className="flex items-center justify-between pb-2">
              <span className="text-xs text-[hsl(var(--ink-muted))]">Език / Limbă / Language</span>
              <div className="flex items-center gap-2">
                <ThemeToggle />
                <LanguageSwitcher />
              </div>
            </div>

            {mobileLinks.map((l) => (
              <Link key={l.to} to={l.to} onClick={closeMobile} className="block py-2 text-sm" data-testid={`mobile-nav-${l.to.slice(1)}`}>
                {l.label}
              </Link>
            ))}

            {user && (
              <div className="rule-t pt-3 space-y-2" data-testid="mobile-account-links">
                {(user.role === "admin" || user.role === "moderator") && (
                  <Link to="/admin" onClick={closeMobile} className="block py-2 text-sm text-[hsl(var(--accent))] font-semibold" data-testid="mobile-nav-admin">
                    {t("nav.admin")}
                  </Link>
                )}
                <Link to="/dashboard" onClick={closeMobile} className="flex items-center justify-between gap-3 py-2" data-testid="mobile-nav-dashboard">
                  <span className="text-sm font-medium truncate">{user.name}</span>
                </Link>
                {credits && (
                  <Link
                    to="/my-bids"
                    onClick={closeMobile}
                    className="flex items-center justify-between gap-3 py-2 -my-1 px-2 rounded-md hover:bg-[hsl(var(--surface))]"
                    data-testid="mobile-nav-user-credits"
                  >
                    <span className="text-[10px] uppercase tracking-wide text-[hsl(var(--ink-muted))]">
                      {t("nav.bidding_credit", "Наддавателен кредит")}
                    </span>
                    <span className="text-sm font-semibold tabular-nums" data-testid="mobile-nav-credits-value">
                      {formatEUR(credits.total_available_eur)}<span className="text-[hsl(var(--ink-muted))] font-normal">/{formatEUR(credits.total_limit_eur)}</span>
                    </span>
                  </Link>
                )}
                <Link to="/my-listings" onClick={closeMobile} className="block py-2 text-sm" data-testid="mobile-nav-my-listings">{t("nav.my_listings")}</Link>
                <Link to="/my-bids" onClick={closeMobile} className="block py-2 text-sm" data-testid="mobile-nav-my-bids">{t("nav.my_bids", "Моите наддавания")}</Link>
                <Link to="/watchlist" onClick={closeMobile} className="block py-2 text-sm" data-testid="mobile-nav-watchlist">{t("nav.watchlist")}</Link>
                <Link to="/inbox" onClick={closeMobile} className="block py-2 text-sm" data-testid="mobile-nav-inbox">{t("nav.notifications", t("inbox.title", "Известия"))}</Link>
                <Link to="/settings" onClick={closeMobile} className="block py-2 text-sm" data-testid="mobile-nav-settings">{t("nav.settings")}</Link>
              </div>
            )}

            <div className="rule-t pt-3 flex gap-3">
              {user ? (
                <button onClick={() => { logout(); closeMobile(); navigate("/"); }} className="btn btn-secondary flex-1" data-testid="mobile-logout">{t("nav.logout")}</button>
              ) : (
                <>
                  <Link to="/login" onClick={closeMobile} className="btn btn-secondary flex-1" data-testid="mobile-login">{t("nav.login")}</Link>
                  <Link to="/register" onClick={closeMobile} className="btn btn-primary flex-1" data-testid="mobile-register">{t("nav.register")}</Link>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
