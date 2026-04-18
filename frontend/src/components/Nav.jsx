import React, { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { Menu, X, User, Search } from "lucide-react";
import { useAuth } from "../lib/auth";

const links = [
  { to: "/auctions", label: "Търгове" },
  { to: "/how-it-works", label: "Как работи" },
  { to: "/sales", label: "Продадени" },
  { to: "/sell", label: "Продай автомобил" },
];

export default function Nav() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  const doSearch = (e) => {
    e.preventDefault();
    if (!q.trim()) return;
    navigate(`/auctions?q=${encodeURIComponent(q.trim())}`);
    setQ("");
  };

  return (
    <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md rule-b" data-testid="main-navigation">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10">
        <div className="flex items-center justify-between h-16 gap-6">
          <Link to="/" className="flex items-center gap-2 shrink-0 mr-2 md:mr-6" data-testid="brand-logo">
            <span className="font-serif text-2xl tracking-tight">AutoBid<span className="text-[hsl(var(--accent))]">.bg</span></span>
          </Link>

          <nav className="hidden md:flex items-center gap-5 lg:gap-7 shrink-0">
            {links.map((l) => (
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
            <Search size={14} className="absolute left-3 text-[hsl(var(--ink-muted))]" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Търси автомобил…"
              className="w-full border border-[hsl(var(--line))] h-9 pl-9 pr-3 text-sm bg-[hsl(var(--surface))]"
              data-testid="nav-search-input"
            />
          </form>

          <div className="hidden md:flex items-center gap-3 lg:gap-4 shrink-0">
            {user ? (
              <>
                {user.role === "admin" && (
                  <Link to="/admin" className="text-sm text-[hsl(var(--accent))] whitespace-nowrap" data-testid="nav-admin">Админ</Link>
                )}
                <Link to="/my-listings" className="text-sm whitespace-nowrap hidden xl:inline" data-testid="nav-my-listings">Мои обяви</Link>
                <Link to="/watchlist" className="text-sm whitespace-nowrap hidden xl:inline" data-testid="nav-watchlist">Любими</Link>
                <Link to="/settings" className="text-sm whitespace-nowrap hidden xl:inline" data-testid="nav-settings">Настройки</Link>
                <Link to="/dashboard" className="flex items-center gap-1.5 text-sm whitespace-nowrap" data-testid="nav-dashboard">
                  <User size={16} />
                  <span className="max-w-[110px] truncate">{user.name}</span>
                </Link>
                <button onClick={() => { logout(); navigate("/"); }} className="btn btn-secondary !py-2 !px-3 lg:!px-4 whitespace-nowrap" data-testid="nav-logout">
                  Изход
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="text-sm whitespace-nowrap" data-testid="nav-login">Вход</Link>
                <Link to="/register" className="btn btn-primary !py-2 !px-4" data-testid="nav-register">Регистрация</Link>
              </>
            )}
          </div>

          <button className="md:hidden" onClick={() => setOpen(!open)} data-testid="mobile-menu-toggle">
            {open ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </div>

      {open && (
        <div className="md:hidden rule-t">
          <div className="max-w-[1440px] mx-auto px-4 py-4 space-y-3">
            <form onSubmit={(e) => { doSearch(e); setOpen(false); }} className="relative" data-testid="mobile-search-form">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
              <input
                type="text"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Търси автомобил…"
                className="w-full border border-[hsl(var(--line))] h-10 pl-9 pr-3 text-sm bg-[hsl(var(--surface))]"
                data-testid="mobile-search-input"
              />
            </form>

            {links.map((l) => (
              <Link key={l.to} to={l.to} onClick={() => setOpen(false)} className="block py-2 text-sm" data-testid={`mobile-nav-${l.to.slice(1)}`}>
                {l.label}
              </Link>
            ))}

            {user && (
              <div className="rule-t pt-3 space-y-2" data-testid="mobile-account-links">
                {user.role === "admin" && (
                  <Link to="/admin" onClick={() => setOpen(false)} className="block py-2 text-sm text-[hsl(var(--accent))] font-semibold" data-testid="mobile-nav-admin">
                    Админ панел
                  </Link>
                )}
                <Link to="/dashboard" onClick={() => setOpen(false)} className="block py-2 text-sm" data-testid="mobile-nav-dashboard">
                  {user.name}
                </Link>
                <Link to="/my-listings" onClick={() => setOpen(false)} className="block py-2 text-sm" data-testid="mobile-nav-my-listings">Мои обяви</Link>
                <Link to="/watchlist" onClick={() => setOpen(false)} className="block py-2 text-sm" data-testid="mobile-nav-watchlist">Любими</Link>
                <Link to="/settings" onClick={() => setOpen(false)} className="block py-2 text-sm" data-testid="mobile-nav-settings">Настройки</Link>
              </div>
            )}

            <div className="rule-t pt-3 flex gap-3">
              {user ? (
                <button onClick={() => { logout(); setOpen(false); navigate("/"); }} className="btn btn-secondary flex-1" data-testid="mobile-logout">Изход</button>
              ) : (
                <>
                  <Link to="/login" onClick={() => setOpen(false)} className="btn btn-secondary flex-1" data-testid="mobile-login">Вход</Link>
                  <Link to="/register" onClick={() => setOpen(false)} className="btn btn-primary flex-1" data-testid="mobile-register">Регистрация</Link>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
