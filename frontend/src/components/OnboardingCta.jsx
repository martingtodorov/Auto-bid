import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../lib/auth";
import { useBrandName } from "../lib/brand";

/**
 * Compact onboarding strip shown to signed-out visitors only.
 *
 * Reads: "New to Auto&Bid.bg? Learn how it works" — with the call-to-action
 * rendered in the accent green to clearly signal it is a link to
 * /how-it-works.
 */
export default function OnboardingCta() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const brand = useBrandName();
  if (user) return null;
  return (
    <div className="rule-b bg-[hsl(var(--surface))]" data-testid="onboarding-cta">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-10 py-4 text-center text-sm">
        <span className="text-[hsl(var(--ink-muted))]">{t("onboarding_cta.intro", { brand })} </span>
        <Link
          to="/how-it-works"
          className="font-semibold text-[hsl(var(--accent))] hover:underline underline-offset-4"
          data-testid="onboarding-cta-link"
        >
          {t("onboarding_cta.link")} →
        </Link>
      </div>
    </div>
  );
}
