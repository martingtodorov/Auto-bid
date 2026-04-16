import React, { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { Menu, X, User } from "lucide-react";
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
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md rule-b" data-testid="main-navigation">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10">
        <div className="flex items-center justify-between h-16">
          <Link to="/" className="flex items-center gap-2" data-testid="brand-logo">
            <span className="font-serif text-2xl tracking-tight">AutoBid<span className="text-[hsl(var(--accent))]">.bg</span></span>
          </Link>

          <nav className="hidden md:flex items-center gap-8">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  `text-sm tracking-wide ${isActive ? "text-[hsl(var(--accent))]" : "text-[hsl(var(--ink))] hover:text-[hsl(var(--accent))]"}`
                }
                data-testid={`nav-link-${l.to.slice(1)}`}
              >
                {l.label}
              </NavLink>
            ))}
          </nav>

          <div className="hidden md:flex items-center gap-3">
            {user ? (
              <>
                {user.role === "admin" && (
                  <Link to="/admin" className="text-sm text-[hsl(var(--accent))]" data-testid="nav-admin">Админ</Link>
                )}
                <Link to="/my-listings" className="text-sm" data-testid="nav-my-listings">Мои обяви</Link>
                <Link to="/watchlist" className="text-sm" data-testid="nav-watchlist">Следени</Link>
                <Link to="/dashboard" className="flex items-center gap-2 text-sm" data-testid="nav-dashboard">
                  <User size={16} />
                  {user.name}
                </Link>
                <button onClick={() => { logout(); navigate("/"); }} className="btn btn-secondary !py-2 !px-4" data-testid="nav-logout">
                  Изход
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="text-sm" data-testid="nav-login">Вход</Link>
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
            {links.map((l) => (
              <Link key={l.to} to={l.to} onClick={() => setOpen(false)} className="block py-2 text-sm" data-testid={`mobile-nav-${l.to.slice(1)}`}>
                {l.label}
              </Link>
            ))}
            <div className="rule-t pt-3 flex gap-3">
              {user ? (
                <button onClick={() => { logout(); setOpen(false); navigate("/"); }} className="btn btn-secondary flex-1">Изход</button>
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
