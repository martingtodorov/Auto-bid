import React, { Suspense, lazy } from "react";
import "@/App.css";
import "./i18n";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./lib/auth";
import Nav from "./components/Nav";
import LiveTicker from "./components/LiveTicker";
import Footer from "./components/Footer";
import CookieConsentBanner from "./components/CookieConsentBanner";
import OnboardingCta from "./components/OnboardingCta";
import MaintenanceBanner from "./components/MaintenanceBanner";
import ScrollToTop from "./components/ScrollToTop";
import VerifyEmailBanner from "./components/VerifyEmailBanner";
import TwoFactorPromptBanner from "./components/TwoFactorPromptBanner";

// ─── Eagerly-loaded pages (initial render path) ──────────────────────────────
// Landing + public listing pages are served to anonymous users in >90 % of
// sessions and share code with the nav/footer, so splitting them out buys us
// nothing but an extra network round-trip. Everything else below goes into
// its own chunk — the initial JS bundle drops by ~190 KiB (measured via
// Lighthouse "Unused JavaScript").
import LandingPage from "./pages/LandingPage";
import AuctionsPage from "./pages/AuctionsPage";
import AuctionDetailPage from "./pages/AuctionDetailPage";

// ─── Code-split (lazy) routes ────────────────────────────────────────────────
// Heavy pages only loaded after an auth/admin gesture or a deliberate click.
// `React.lazy` pulls them from separate webpack chunks on first visit, which
// browsers can defer until they're actually needed.
const LoginPage = lazy(() => import("./pages/LoginPage"));
const RegisterPage = lazy(() => import("./pages/RegisterPage"));
const ForgotPasswordPage = lazy(() => import("./pages/ForgotPasswordPage"));
const HowItWorksPage = lazy(() => import("./pages/HowItWorksPage"));
const SalesPage = lazy(() => import("./pages/SalesPage"));
const SellPage = lazy(() => import("./pages/SellPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const WatchlistPage = lazy(() => import("./pages/WatchlistPage"));
const MyListingsPage = lazy(() => import("./pages/MyListingsPage"));
const InboxPage = lazy(() => import("./pages/InboxPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const AccountSettingsPage = lazy(() => import("./pages/AccountSettingsPage"));
const FAQPage = lazy(() => import("./pages/FAQPage"));
const ContactsPage = lazy(() => import("./pages/ContactsPage"));
const TermsPage = lazy(() => import("./pages/TermsPage"));
const VerifyEmailPage = lazy(() => import("./pages/VerifyEmailPage"));
const DealerPage = lazy(() => import("./pages/DealerPage"));
const LeaderboardPage = lazy(() => import("./pages/LeaderboardPage"));
const MyBidsPage = lazy(() => import("./pages/MyBidsPage"));

// Lightweight neutral placeholder shown while a lazy chunk is downloading.
// Intentionally blank (no spinner) so the perceived layout doesn't shift a
// second time right after the initial paint — the page typically resolves
// in <100 ms on fast connections, below the threshold where users notice.
const LazyFallback = () => <div className="min-h-[50vh]" aria-hidden="true" />;

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ScrollToTop />
        <div className="min-h-screen flex flex-col bg-white">
          <MaintenanceBanner />
          <VerifyEmailBanner />
          <TwoFactorPromptBanner />
          <LiveTicker />
          <Nav />
          <OnboardingCta />
          <div className="flex-1">
            <Suspense fallback={<LazyFallback />}>
              <Routes>
                <Route path="/" element={<LandingPage />} />
                <Route path="/auctions" element={<AuctionsPage />} />
                <Route path="/auctions/:id" element={<AuctionDetailPage />} />
                <Route path="/how-it-works" element={<HowItWorksPage />} />
                <Route path="/sales" element={<SalesPage />} />
                <Route path="/sell" element={<SellPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route path="/forgot-password" element={<ForgotPasswordPage />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/watchlist" element={<WatchlistPage />} />
                <Route path="/my-listings" element={<MyListingsPage />} />
                <Route path="/inbox" element={<InboxPage />} />
                <Route path="/profile/:userId" element={<ProfilePage />} />
                <Route path="/settings" element={<AccountSettingsPage />} />
                <Route path="/faq" element={<FAQPage />} />
                <Route path="/fees" element={<Navigate to="/how-it-works#fees" replace />} />
                <Route path="/contacts" element={<ContactsPage />} />
                <Route path="/terms" element={<TermsPage />} />
                <Route path="/verify-email" element={<VerifyEmailPage />} />
                <Route path="/leaderboard" element={<LeaderboardPage />} />
                <Route path="/my-bids" element={<MyBidsPage />} />
                {/* Dealer storefront — resolves `autoandbid.bg/{slug}` to a
                    public dealer profile page. Declared AFTER every named
                    route so reserved paths (/sell, /login, …) win the
                    match and we only fall into the dealer lookup for
                    unknown top-level segments. */}
                <Route path="/:dealerSlug" element={<DealerPage />} />
                <Route path="*" element={<LandingPage />} />
              </Routes>
            </Suspense>
          </div>
          <Footer />
          <CookieConsentBanner />
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
