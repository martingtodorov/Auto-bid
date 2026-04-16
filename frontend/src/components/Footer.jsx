import React from "react";
import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="rule-t bg-[hsl(var(--surface))]" data-testid="site-footer">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16 grid grid-cols-2 md:grid-cols-4 gap-10">
        <div className="col-span-2 md:col-span-1">
          <div className="font-serif text-2xl tracking-tight">AutoBid<span className="text-[hsl(var(--accent))]">.bg</span></div>
          <p className="mt-4 text-sm text-[hsl(var(--ink-muted))] max-w-xs leading-relaxed">
            Първата редакционна платформа за автомобилни търгове в България. Подбрани екземпляри, прозрачни продажби.
          </p>
        </div>

        <div>
          <div className="overline text-[hsl(var(--ink-muted))]">Платформа</div>
          <ul className="mt-4 space-y-2 text-sm">
            <li><Link to="/auctions">Активни търгове</Link></li>
            <li><Link to="/sales">Архив продажби</Link></li>
            <li><Link to="/sell">Продай автомобил</Link></li>
            <li><Link to="/how-it-works">Как работи</Link></li>
          </ul>
        </div>

        <div>
          <div className="overline text-[hsl(var(--ink-muted))]">Помощ</div>
          <ul className="mt-4 space-y-2 text-sm">
            <li><a href="#">Често задавани въпроси</a></li>
            <li><a href="#">Такси и комисионни</a></li>
            <li><a href="#">Контакти</a></li>
            <li><a href="#">Общи условия</a></li>
          </ul>
        </div>

        <div>
          <div className="overline text-[hsl(var(--ink-muted))]">Общност</div>
          <ul className="mt-4 space-y-2 text-sm">
            <li><a href="#">Instagram</a></li>
            <li><a href="#">YouTube</a></li>
            <li><a href="#">Telegram канал</a></li>
            <li><a href="#">Бюлетин</a></li>
          </ul>
        </div>
      </div>

      <div className="rule-t">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <p className="text-xs text-[hsl(var(--ink-muted))]">© 2026 AutoBid.bg · София, България</p>
          <p className="text-xs text-[hsl(var(--ink-muted))] font-mono">Made in Sofia · Licensed auction platform</p>
        </div>
      </div>
    </footer>
  );
}
