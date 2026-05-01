import React from "react";
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
// Legacy /fees page removed — merged into /how-it-works. Kept redirect for inbound links.
import LandingPage from "./pages/LandingPage";
import AuctionsPage from "./pages/AuctionsPage";
import AuctionDetailPage from "./pages/AuctionDetailPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import HowItWorksPage from "./pages/HowItWorksPage";
import SalesPage from "./pages/SalesPage";
import SellPage from "./pages/SellPage";
import DashboardPage from "./pages/DashboardPage";
import AdminPage from "./pages/AdminPage";
import WatchlistPage from "./pages/WatchlistPage";
import MyListingsPage from "./pages/MyListingsPage";
import InboxPage from "./pages/InboxPage";
import ProfilePage from "./pages/ProfilePage";
import AccountSettingsPage from "./pages/AccountSettingsPage";
import FAQPage from "./pages/FAQPage";
// FeesPage merged into HowItWorksPage — redirect kept in routes.
import ContactsPage from "./pages/ContactsPage";
import TermsPage from "./pages/TermsPage";
import VerifyEmailPage from "./pages/VerifyEmailPage";
import VerifyEmailBanner from "./components/VerifyEmailBanner";
import TwoFactorPromptBanner from "./components/TwoFactorPromptBanner";

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
              <Route path="*" element={<LandingPage />} />
            </Routes>
          </div>
          <Footer />
          <CookieConsentBanner />
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
