import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./lib/auth";
import Nav from "./components/Nav";
import LiveTicker from "./components/LiveTicker";
import Footer from "./components/Footer";
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
import ProfilePage from "./pages/ProfilePage";
import AccountSettingsPage from "./pages/AccountSettingsPage";
import FAQPage from "./pages/FAQPage";
import FeesPage from "./pages/FeesPage";
import ContactsPage from "./pages/ContactsPage";
import TermsPage from "./pages/TermsPage";

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="min-h-screen flex flex-col bg-white">
          <LiveTicker />
          <Nav />
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
              <Route path="/profile/:userId" element={<ProfilePage />} />
              <Route path="/settings" element={<AccountSettingsPage />} />
              <Route path="/faq" element={<FAQPage />} />
              <Route path="/fees" element={<FeesPage />} />
              <Route path="/contacts" element={<ContactsPage />} />
              <Route path="/terms" element={<TermsPage />} />
              <Route path="*" element={<LandingPage />} />
            </Routes>
          </div>
          <Footer />
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
