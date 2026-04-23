import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { brandTldForLang } from "../i18n";

export default function Footer() {
  const { t, i18n } = useTranslation();
  const brandTld = brandTldForLang(i18n.resolvedLanguage || i18n.language);
  return (
    <footer className="rule-t bg-[hsl(var(--surface))]" data-testid="site-footer">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-16 grid grid-cols-2 md:grid-cols-4 gap-10">
        <div className="col-span-2 md:col-span-1">
          <div className="font-serif text-2xl tracking-tight">Auto<span className="text-[hsl(var(--accent))]">&amp;</span>Bid<span className="text-[hsl(var(--accent))]">{brandTld}</span></div>
          <p className="mt-4 text-sm text-[hsl(var(--ink-muted))] max-w-xs leading-relaxed">
            {t("footer.brand_tagline")}
          </p>
        </div>

        <div>
          <div className="overline text-[hsl(var(--ink-muted))]">{t("footer.col_platform")}</div>
          <ul className="mt-4 space-y-2 text-sm">
            <li><Link to="/auctions" className="hover:text-[hsl(var(--accent))]" data-testid="footer-auctions">{t("footer.active_auctions")}</Link></li>
            <li><Link to="/sales" className="hover:text-[hsl(var(--accent))]" data-testid="footer-sales">{t("footer.sales_archive")}</Link></li>
            <li><Link to="/sell" className="hover:text-[hsl(var(--accent))]" data-testid="footer-sell">{t("footer.sell_car")}</Link></li>
            <li><Link to="/how-it-works" className="hover:text-[hsl(var(--accent))]" data-testid="footer-hiw">{t("footer.how_it_works")}</Link></li>
          </ul>
        </div>

        <div>
          <div className="overline text-[hsl(var(--ink-muted))]">{t("footer.col_help")}</div>
          <ul className="mt-4 space-y-2 text-sm">
            <li><Link to="/faq" className="hover:text-[hsl(var(--accent))]" data-testid="footer-faq">{t("footer.faq")}</Link></li>
            <li><Link to="/how-it-works#fees" className="hover:text-[hsl(var(--accent))]" data-testid="footer-fees">{t("footer.fees")}</Link></li>
            <li><Link to="/contacts" className="hover:text-[hsl(var(--accent))]" data-testid="footer-contacts">{t("footer.contact")}</Link></li>
            <li><Link to="/terms" className="hover:text-[hsl(var(--accent))]" data-testid="footer-terms">{t("footer.terms")}</Link></li>
          </ul>
        </div>

        <div>
          <div className="overline text-[hsl(var(--ink-muted))]">{t("footer.col_account")}</div>
          <ul className="mt-4 space-y-2 text-sm">
            <li><Link to="/login" className="hover:text-[hsl(var(--accent))]" data-testid="footer-login">{t("footer.login")}</Link></li>
            <li><Link to="/register" className="hover:text-[hsl(var(--accent))]" data-testid="footer-register">{t("footer.register")}</Link></li>
            <li><Link to="/my-listings" className="hover:text-[hsl(var(--accent))]" data-testid="footer-my-listings">{t("footer.my_listings")}</Link></li>
            <li><Link to="/watchlist" className="hover:text-[hsl(var(--accent))]" data-testid="footer-watchlist">{t("footer.watchlist")}</Link></li>
          </ul>
        </div>
      </div>

      <div className="rule-t">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <p className="text-xs text-[hsl(var(--ink-muted))]">{t("footer.copyright")}</p>
          <p className="text-xs text-[hsl(var(--ink-muted))] font-mono">{t("footer.made_in")}</p>
        </div>
      </div>
    </footer>
  );
}
