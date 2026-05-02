import React, { useEffect, useState, useCallback } from "react";
import { Navigate, Link } from "react-router-dom";
import { Check, X, Clock, AlertCircle, DollarSign, Archive, Ban, Edit3, Eye, Trash2, RotateCcw, Search, List, Users, BarChart3, Trash, RefreshCw, CreditCard, ScrollText, Tag, Pause, Play, Star, StarOff, Copy, XCircle, Gavel, Mail, Inbox, FileEdit, MessageCircle, Activity } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth, formatError } from "../lib/auth";
import { api, formatEUR, formatKM } from "../lib/apiClient";
import AdminEditModal from "../components/AdminEditModal";
import AdminUsersTab from "../components/AdminUsersTab";
import AdminDashboard from "../components/AdminDashboard";
import AdminSettingsTab from "../components/AdminSettingsTab";
import AdminStripeTab from "../components/AdminStripeTab";
import AdminAuditLogTab from "../components/AdminAuditLogTab";
import AdminMakesTab from "../components/AdminMakesTab";
import AdminBidHistoryModal from "../components/AdminBidHistoryModal";
import AdminNotificationsTab from "../components/AdminNotificationsTab";
import AdminEmailTemplatesTab from "../components/AdminEmailTemplatesTab";
import AdminSellerRequestsTab from "../components/AdminSellerRequestsTab";
import AdminArchiveTab from "../components/AdminArchiveTab";
import AdminUnsoldTab from "../components/AdminUnsoldTab";
import AdminChatPanel from "../components/AdminChatPanel";
import AdminHealthTab from "../components/AdminHealthTab";

const STATUS_LABELS = {
  pending: "Очаква",
  live: "Активен",
  ended: "Приключил",
  sold: "Продаден",
  reserve_not_met: "Резервът не е достигнат",
  withdrawn: "Оттеглен",
  removed: "Премахнат",
  rejected: "Отказан",
};

export default function AdminPage() {
  const { t } = useTranslation();
  const { user, loading } = useAuth();
  const [tab, setTab] = useState("dashboard");
  const [pending, setPending] = useState([]);
  const [sold, setSold] = useState([]);
  const [allListings, setAllListings] = useState([]);
  const [allQuery, setAllQuery] = useState("");
  const [allStatusFilter, setAllStatusFilter] = useState("");
  const [rejectingId, setRejectingId] = useState(null);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [bidsForAuction, setBidsForAuction] = useState(null); // {id, title}
  // Tab counters — one aggregate request drives every badge. Auto-refreshes
  // on mount and after any admin action via loadCounters().
  const [counters, setCounters] = useState({});

  const loadCounters = useCallback(async () => {
    try { const { data } = await api.get("/admin/counters"); setCounters(data || {}); }
    catch (e) { /* non-fatal — badges just stay empty */ }
  }, []);

  const loadPending = useCallback(async () => {
    try { const { data } = await api.get("/admin/pending"); setPending(data); }
    catch (e) { setErr(formatError(e)); }
  }, []);
  const loadSold = useCallback(async () => {
    try { const { data } = await api.get("/admin/sold"); setSold(data); }
    catch (e) { setErr(formatError(e)); }
  }, []);
  const [allOffset, setAllOffset] = useState(0);
  const [allTotal, setAllTotal] = useState(0);
  const ALL_PAGE_SIZE = 25;

  const loadAll = useCallback(async () => {
    try {
      const params = { paginated: 1, limit: ALL_PAGE_SIZE, offset: allOffset };
      if (allQuery) params.q = allQuery;
      if (allStatusFilter) params.status = allStatusFilter;
      const { data } = await api.get("/admin/auctions", { params });
      const items = Array.isArray(data) ? data : (data?.items || []);
      setAllListings(items);
      setAllTotal(Array.isArray(data) ? items.length : Number(data?.total || items.length));
    } catch (e) { setErr(formatError(e)); }
  }, [allQuery, allStatusFilter, allOffset]);

  // Reset offset when query/status changes (avoid pagination "stuck" after filter change)
  useEffect(() => { setAllOffset(0); }, [allQuery, allStatusFilter]);

  useEffect(() => {
    if (user?.role === "admin" || user?.role === "moderator") {
      loadCounters();
    }
  }, [user, loadCounters]);

  useEffect(() => {
    if (user?.role === "admin") {
      loadPending();
      loadSold();
      loadAll();
    }
  }, [user, loadPending, loadSold, loadAll]);

  if (loading) return <div className="py-24 text-center">Зареждане…</div>;
  if (!user) return <Navigate to="/login?next=/admin" replace />;
  if (user.role !== "admin" && user.role !== "moderator") {
    return (
      <main className="py-24" data-testid="admin-denied">
        <div className="max-w-md mx-auto text-center px-6">
          <AlertCircle size={32} className="mx-auto text-[hsl(var(--danger))]" />
          <h1 className="font-serif text-3xl mt-4">Достъпът е ограничен</h1>
          <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">Тази страница е достъпна само за администратори и модератори.</p>
          <Link to="/" className="btn btn-primary mt-6 inline-flex">Към началото</Link>
        </div>
      </main>
    );
  }

  const approve = async (id) => {
    setErr(""); setBusy(id);
    try { await api.post(`/admin/auctions/${id}/approve`); await Promise.all([loadPending(), loadAll()]); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const reject = async (id) => {
    setErr(""); setBusy(id);
    try {
      await api.post(`/admin/auctions/${id}/reject`, { reason });
      setRejectingId(null); setReason("");
      await Promise.all([loadPending(), loadAll()]);
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const capturePremium = async (id) => {
    setErr(""); setBusy(id);
    try { await api.post(`/admin/auctions/${id}/capture-premium`); await loadSold(); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const releaseAll = async (id) => {
    setErr(""); setBusy(id);
    try { await api.post(`/admin/auctions/${id}/finalize`); await loadSold(); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const removeListing = async (id) => {
    if (!window.confirm('Сигурни ли сте, че искате да свалите тази обява от публичния сайт? Тя ще остане в базата със статус „Премахната“.')) return;
    setErr(""); setBusy(id);
    try { await api.post(`/admin/auctions/${id}/remove`); await Promise.all([loadAll(), loadPending()]); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const restoreListing = async (id) => {
    setErr(""); setBusy(id);
    try { await api.post(`/admin/auctions/${id}/restore`); await Promise.all([loadAll(), loadPending()]); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const hardDeleteListing = async (id, title) => {
    const confirm1 = window.prompt(`Архивиране на обявата "${title || id}".\n\nОбявата се скрива от публичните листинги, но ВСИЧКО се запазва (снимки, наддавания, коментари) и може да се възстанови по всяко време.\n\nЗа потвърждение напишете АРХИВ:`);
    if (confirm1 !== "АРХИВ") return;
    setErr(""); setBusy(id);
    try {
      const { data } = await api.delete(`/admin/auctions/${id}`);
      if (data?.hard_deleted) {
        const d = data.deleted || {};
        alert(`Изтрити: ${d.auction || 0} обява, ${d.bids || 0} наддавания, ${d.comments || 0} коментари, ${d.watches || 0} watchers.`);
      } else {
        alert(`Обявата е архивирана. Може да я възстановите от секция "Архивирани" или да я премахнете окончателно само при законова необходимост.`);
      }
      await Promise.all([loadAll(), loadPending(), loadSold()]);
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  const extendListing = async (id, title) => {
    const daysStr = window.prompt(`Подновяване на обявата "${title || id}".\n\nВъведете брой дни (1-60):`, "10");
    if (!daysStr) return;
    const days = parseInt(daysStr, 10);
    if (!Number.isInteger(days) || days < 1 || days > 60) {
      alert("Невалиден брой дни (1-60).");
      return;
    }
    setErr(""); setBusy(id);
    try {
      const { data } = await api.post(`/admin/auctions/${id}/extend`, null, { params: { days } });
      alert(`Обявата е подновена. Нов край: ${new Date(data.ends_at).toLocaleString("bg-BG")}`);
      await Promise.all([loadAll(), loadSold()]);
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  const reactivateListing = async (id, title) => {
    const daysStr = window.prompt(`Реактивиране на продадена обява "${title || id}" — тя ще стане отново активна.\n\nВъведете колко дни да е отворена (1-60):`, "7");
    if (!daysStr) return;
    const days = parseInt(daysStr, 10);
    if (!Number.isInteger(days) || days < 1 || days > 60) {
      alert("Невалиден брой дни (1-60).");
      return;
    }
    if (!window.confirm("Сигурни ли сте? Обявата ще се върне в списъка с активни търгове. История на бидовете се запазва.")) return;
    setErr(""); setBusy(id);
    try {
      const { data } = await api.post(`/admin/auctions/${id}/reactivate`, null, { params: { days } });
      alert(`Обявата е реактивирана. Нов край: ${new Date(data.ends_at).toLocaleString("bg-BG")}`);
      await Promise.all([loadAll(), loadSold()]);
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  const resetTimer = async (id, title) => {
    const choice = window.prompt(
      `Reset на таймера за „${title || id}".\n\nВъведете часове (напр. 24 за +24 часа, 0.5 за +30 мин).\nИли въведете например „d:7" за 7 дни.`,
      "24"
    );
    if (!choice) return;
    let params;
    if (choice.startsWith("d:")) {
      const days = parseInt(choice.slice(2), 10);
      if (!Number.isInteger(days) || days < 1 || days > 60) {
        alert("Невалиден брой дни (1–60).");
        return;
      }
      params = { days };
    } else {
      const hours = Number(choice);
      if (!Number.isFinite(hours) || hours < 0.5 || hours > 720) {
        alert("Невалиден брой часове (0.5–720).");
        return;
      }
      params = { hours };
    }
    setErr(""); setBusy(id);
    try {
      const { data } = await api.post(`/admin/auctions/${id}/reset-timer`, null, { params });
      alert(`Таймерът е reset-нат. Нов край: ${new Date(data.ends_at).toLocaleString("bg-BG")}`);
      await loadAll();
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  // ---- Phase 2 lifecycle actions ----
  const toggleFeatured = async (id) => {
    setBusy(id);
    try { await api.post(`/admin/auctions/${id}/featured`); await loadAll(); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const pauseAuction = async (id) => {
    if (!window.confirm("Паузирай търга? Оставащото време ще се запази до възобновяване.")) return;
    setBusy(id);
    try { await api.post(`/admin/auctions/${id}/pause`); await loadAll(); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const unpauseAuction = async (id) => {
    setBusy(id);
    try { await api.post(`/admin/auctions/${id}/unpause`); await loadAll(); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const cancelAuction = async (id, title) => {
    const reason = window.prompt(`Причина за отказване на "${title || id}" (мин. 3 символа):`);
    if (!reason || reason.trim().length < 3) return;
    if (!window.confirm("Сигурни ли сте? Обявата ще бъде маркирана като отказана.")) return;
    setBusy(id);
    try { await api.post(`/admin/auctions/${id}/cancel`, { reason: reason.trim() }); await loadAll(); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const closeNow = async (id, title) => {
    if (!window.confirm(`Затваряне на "${title || id}" сега? Обявата ще премине към финализиране в рамките на 60 секунди.`)) return;
    setBusy(id);
    try { await api.post(`/admin/auctions/${id}/close-now`); await loadAll(); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const archiveAuction = async (id) => {
    setBusy(id);
    try { await api.post(`/admin/auctions/${id}/archive`); await Promise.all([loadAll(), loadSold()]); }
    catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };
  const duplicateAuction = async (id) => {
    setBusy(id);
    try {
      const { data } = await api.post(`/auctions/${id}/duplicate`);
      alert(`Създаден е нов draft: ${data.id}. Ще го намерите в "Очакващи".`);
      await Promise.all([loadAll(), loadPending()]);
    } catch (e) { setErr(formatError(e)); }
    finally { setBusy(null); }
  };

  const tabs = [
    { k: "dashboard", label: t("admin.tabs.dashboard"), icon: BarChart3 },
    { k: "pending", label: t("admin.tabs.pending"), icon: Clock, count: counters.pending ?? pending.length },
    { k: "all", label: t("admin.tabs.all_listings"), icon: List, count: counters.all ?? allListings.length },
    { k: "requests", label: t("admin.tabs.requests"), icon: Inbox, count: counters.requests },
    { k: "users", label: t("admin.tabs.users"), icon: Users, count: counters.users },
    { k: "sold", label: t("admin.tabs.sold"), icon: Archive, count: counters.sold ?? sold.length },
    { k: "unsold", label: "Непродадени", icon: XCircle, count: counters.unsold },
    { k: "archive", label: t("admin.tabs.archive"), icon: Archive, adminOnly: true, count: counters.archive },
    { k: "makes", label: t("admin.tabs.makes"), icon: Tag, adminOnly: true },
    { k: "stripe", label: t("admin.tabs.stripe"), icon: CreditCard, adminOnly: true },
    { k: "notifications", label: t("admin.tabs.notifications"), icon: Mail, count: counters.notifications },
    { k: "chat", label: "Чат", icon: MessageCircle, count: counters.chat },
    { k: "health", label: "Здраве", icon: Activity, adminOnly: true },
    { k: "templates", label: t("admin.tabs.templates"), icon: FileEdit, adminOnly: true },
    { k: "audit", label: t("admin.tabs.audit"), icon: ScrollText },
    { k: "settings", label: t("admin.tabs.settings"), icon: Edit3, adminOnly: true },
  ].filter((t) => !t.adminOnly || user?.role === "admin");

  return (
    <main data-testid="admin-page">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-10 py-16">
        <div className="overline text-[hsl(var(--accent))]">{t("admin.overline")}</div>
        <h1 className="font-serif text-4xl lg:text-5xl mt-3 tracking-tight">{t("admin.title")}</h1>

        <div className="mt-8 inline-flex rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white flex-wrap">
          {tabs.map((t, i) => {
            const Icon = t.icon;
            const n = typeof t.count === "number" ? t.count : null;
            return (
              <button
                key={t.k}
                onClick={() => setTab(t.k)}
                className={`px-5 py-2.5 text-sm font-medium flex items-center gap-2 ${tab === t.k ? "bg-[hsl(var(--ink))] text-white" : ""} ${i > 0 ? "border-l border-[hsl(var(--line))]" : ""}`}
                data-testid={`tab-${t.k}`}
              >
                <Icon size={14} /> {t.label}
                {n !== null && n > 0 && (
                  <span
                    className={`ml-1 inline-flex items-center justify-center min-w-[22px] h-[20px] px-1.5 rounded-full text-[11px] font-semibold leading-none ${
                      tab === t.k
                        ? "bg-white/20 text-white"
                        : "bg-[hsl(var(--accent))] text-black"
                    }`}
                    data-testid={`tab-${t.k}-count`}
                  >
                    {n > 999 ? "999+" : n}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {err && <p className="mt-4 text-sm text-[hsl(var(--danger))]">{err}</p>}

        {tab === "dashboard" && <AdminDashboard />}

        {tab === "pending" && (
          <div className="mt-10">
            {pending.length === 0 ? (
              <EmptyState icon={Clock} title="Няма очакващи обяви" sub="Всичко е подредено." />
            ) : (
              <div className="space-y-5" data-testid="pending-list">
                {pending.map((a) => (
                  <div key={a.id} className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid={`pending-${a.id}`}>
                    <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-0">
                      <div className="aspect-[4/3] md:aspect-auto bg-[hsl(var(--surface))]">
                        {a.images?.[0] ? (
                          <img src={a.images[0]} alt={a.title} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-[hsl(var(--ink-muted))] text-xs">Без снимка</div>
                        )}
                      </div>
                      <div className="p-6">
                        <div className="overline text-[hsl(var(--ink-muted))]">{a.make} · {a.body_type} · {a.city}</div>
                        <h3 className="font-serif text-2xl mt-2">{a.title}</h3>
                        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-sm text-[hsl(var(--ink-muted))]">
                          <span>{a.year} г.</span>
                          <span>{formatKM(a.mileage_km)}</span>
                          <span>{a.fuel} · {a.transmission}</span>
                          <span>{a.power_hp} к.с.</span>
                        </div>
                        <p className="mt-4 text-sm leading-relaxed line-clamp-3">{a.description}</p>
                        <div className="mt-4 flex items-center justify-between">
                          <div>
                            <div className="overline text-[hsl(var(--ink-muted))]">Начална цена</div>
                            <div className="font-serif text-xl">{formatEUR(a.starting_bid_eur)}</div>
                          </div>
                          <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">От {a.seller_name}</div>
                        </div>

                        {(a.contact_email || a.contact_phone) && (
                          <div className="mt-4 p-3 rounded-md bg-[hsl(var(--surface))] border border-[hsl(var(--line))]" data-testid={`contact-info-${a.id}`}>
                            <div className="overline text-[hsl(var(--accent))] mb-1.5">Контакт с продавача</div>
                            <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
                              {a.contact_email && <a href={`mailto:${a.contact_email}`} className="text-[hsl(var(--ink))] hover:text-[hsl(var(--accent))]" data-testid={`contact-email-${a.id}`}>{a.contact_email}</a>}
                              {a.contact_phone && <a href={`tel:${a.contact_phone}`} className="text-[hsl(var(--ink))] hover:text-[hsl(var(--accent))] font-mono" data-testid={`contact-phone-${a.id}`}>{a.contact_phone}</a>}
                            </div>
                          </div>
                        )}

                        {rejectingId === a.id ? (
                          <div className="mt-5 rounded-card border border-[hsl(var(--line))] p-4 bg-[hsl(var(--surface))]">
                            <label className="overline text-[hsl(var(--ink-muted))] block mb-2">Причина за отказ</label>
                            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className="w-full border border-[hsl(var(--line))] p-3 text-sm" data-testid={`reject-reason-${a.id}`} />
                            <div className="mt-3 flex gap-2 justify-end">
                              <button onClick={() => { setRejectingId(null); setReason(""); }} className="btn btn-secondary !py-2 !px-4">Отказ</button>
                              <button onClick={() => reject(a.id)} disabled={busy === a.id} className="btn btn-primary !py-2 !px-4" data-testid={`reject-confirm-${a.id}`}>Изпрати отказ</button>
                            </div>
                          </div>
                        ) : (
                          <div className="mt-5 flex gap-2 flex-wrap">
                            <button onClick={() => approve(a.id)} disabled={busy === a.id} className="btn btn-accent !py-2 !px-4 flex items-center gap-2" data-testid={`approve-${a.id}`}>
                              <Check size={14} /> Одобри и стартирай
                            </button>
                            <button onClick={() => setEditingId(a.id)} className="btn btn-secondary !py-2 !px-4 flex items-center gap-2" data-testid={`edit-pending-${a.id}`}>
                              <Edit3 size={14} /> Редактирай
                            </button>
                            <button onClick={() => setRejectingId(a.id)} className="btn btn-secondary !py-2 !px-4 flex items-center gap-2" data-testid={`reject-${a.id}`}>
                              <X size={14} /> Откажи
                            </button>
                            <button onClick={() => hardDeleteListing(a.id, a.title)} disabled={busy === a.id} className="btn btn-secondary !py-2 !px-4 flex items-center gap-2 !text-[hsl(var(--danger))] !border-[hsl(var(--danger))]/40 hover:!bg-[hsl(var(--danger))] hover:!text-white" data-testid={`delete-pending-${a.id}`}>
                              <Trash size={14} /> Изтрий
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "all" && (
          <div className="mt-10">
            <div className="flex flex-wrap gap-3 items-end mb-5">
              <div className="flex-1 min-w-[220px] relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[hsl(var(--ink-muted))]" />
                <input
                  type="text"
                  value={allQuery}
                  onChange={(e) => setAllQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && loadAll()}
                  placeholder="Търсене по заглавие, марка, модел, продавач..."
                  className="input pl-9"
                  data-testid="admin-all-search"
                />
              </div>
              <select value={allStatusFilter} onChange={(e) => setAllStatusFilter(e.target.value)} className="input !w-auto" data-testid="admin-all-status-filter">
                <option value="">Всички статуси</option>
                {Object.entries(STATUS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <button onClick={loadAll} className="btn btn-primary !py-2 !px-4" data-testid="admin-all-refresh">Търси</button>
            </div>

            {allListings.length === 0 ? (
              <EmptyState icon={List} title="Няма обяви" sub="Опитайте с различно търсене." />
            ) : (
              <div className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid="all-listings">
                <div className="hidden md:grid grid-cols-[1.8fr_0.7fr_0.9fr_0.7fr_1.3fr] gap-3 px-5 py-3 rule-b bg-[hsl(var(--surface))] overline text-[hsl(var(--ink-muted))]">
                  <span>Обява</span>
                  <span>Статус</span>
                  <span>Текуща цена</span>
                  <span>Продавач</span>
                  <span>Действия</span>
                </div>
                {allListings.map((a) => (
                  <div key={a.id} className="grid grid-cols-1 md:grid-cols-[1.8fr_0.7fr_0.9fr_0.7fr_1.3fr] gap-3 items-center p-4 rule-b last:border-b-0" data-testid={`listing-row-${a.id}`}>
                    <div className="flex items-center gap-3 min-w-0">
                      {a.images?.[0] ? <img src={a.images[0]} className="w-14 h-10 object-cover rounded-md shrink-0" alt="" /> : <div className="w-14 h-10 bg-[hsl(var(--surface))] rounded-md shrink-0" />}
                      <div className="min-w-0">
                        <div className="font-semibold text-sm truncate">{a.title}</div>
                        <div className="text-xs text-[hsl(var(--ink-muted))]">{a.make} · {a.year} · {a.city}</div>
                      </div>
                    </div>
                    <div>
                      <span className={`pill text-xs ${a.status === "live" ? "pill-live" : ""}`} data-testid={`status-${a.id}`}>{STATUS_LABELS[a.status] || a.status}</span>
                    </div>
                    <div className="font-serif text-base">{formatEUR(a.current_bid_eur || 0)}</div>
                    <div className="text-xs truncate">{a.seller_name || "—"}</div>
                    <div className="flex gap-2 flex-wrap justify-end md:justify-start">
                      <button onClick={() => setEditingId(a.id)} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`edit-${a.id}`}>
                        <Edit3 size={12} /> Редактирай
                      </button>
                      <a href={`/auctions/${a.id}`} target="_blank" rel="noopener noreferrer" className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`preview-${a.id}`} title="Отвори обявата в нов раздел">
                        <Eye size={12} /> Преглед
                      </a>
                      {a.status === "pending" && (
                        <button onClick={() => approve(a.id)} disabled={busy === a.id} className="btn btn-accent !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`quick-approve-${a.id}`}>
                          <Check size={12} /> Одобри
                        </button>
                      )}
                      {(a.status === "live" || a.status === "paused") && (
                        <button onClick={() => resetTimer(a.id, a.title)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1 !border-[hsl(var(--accent))] !text-[hsl(var(--accent))]" data-testid={`reset-timer-${a.id}`} title="Reset на таймера">
                          <Clock size={12} /> Reset таймер
                        </button>
                      )}
                      {(a.status === "ended" || a.status === "reserve_not_met" || a.status === "withdrawn") && (
                        <button onClick={() => extendListing(a.id, a.title)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1 !border-[hsl(var(--accent))] !text-[hsl(var(--accent))]" data-testid={`extend-${a.id}`} title="Поднови търга за нов период">
                          <RefreshCw size={12} /> Поднови
                        </button>
                      )}
                      <button onClick={() => setBidsForAuction({ id: a.id, title: a.title })} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`bids-${a.id}`} title="История на бидовете">
                        <Gavel size={12} /> Бидове ({a.bid_count || 0})
                      </button>
                      {/* Phase 2 lifecycle */}
                      <button onClick={() => toggleFeatured(a.id)} disabled={busy === a.id} className={`btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1 ${a.featured ? "!border-amber-500 !text-amber-600" : ""}`} data-testid={`featured-${a.id}`} title={a.featured ? "Премахни от препоръчани" : "Добави към препоръчани"}>
                        {a.featured ? <><StarOff size={12} /> Без промо</> : <><Star size={12} /> Промо</>}
                      </button>
                      {a.status === "live" && !a.paused && (
                        <button onClick={() => pauseAuction(a.id)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`pause-${a.id}`}>
                          <Pause size={12} /> Пауза
                        </button>
                      )}
                      {a.status === "paused" && (
                        <button onClick={() => unpauseAuction(a.id)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1 !border-[hsl(var(--accent))] !text-[hsl(var(--accent))]" data-testid={`unpause-${a.id}`}>
                          <Play size={12} /> Продължи
                        </button>
                      )}
                      {a.status === "live" && (
                        <button onClick={() => closeNow(a.id, a.title)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`close-now-${a.id}`} title="Затвори веднага">
                          <XCircle size={12} /> Затвори сега
                        </button>
                      )}
                      {!["sold", "cancelled", "withdrawn"].includes(a.status) && (
                        <button onClick={() => cancelAuction(a.id, a.title)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1 !border-[hsl(var(--danger))] !text-[hsl(var(--danger))]" data-testid={`cancel-${a.id}`} title="Отказ с причина">
                          <Ban size={12} /> Отказ
                        </button>
                      )}
                      <button onClick={() => duplicateAuction(a.id)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`duplicate-${a.id}`} title="Дублирай като draft">
                        <Copy size={12} /> Дублирай
                      </button>
                      {(a.status === "sold" || a.status === "ended" || a.status === "cancelled") && !a.is_archived && (
                        <button onClick={() => archiveAuction(a.id)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`archive-${a.id}`} title="Архивирай (скрий от публични списъци)">
                          <Archive size={12} /> Архив
                        </button>
                      )}
                      {a.status === "removed" || a.status === "withdrawn" ? (
                        <button onClick={() => restoreListing(a.id)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`restore-${a.id}`}>
                          <RotateCcw size={12} /> Възстанови
                        </button>
                      ) : a.status !== "sold" ? (
                        <button onClick={() => removeListing(a.id)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1 !border-[hsl(var(--danger))] !text-[hsl(var(--danger))]" data-testid={`remove-${a.id}`}>
                          <Trash2 size={12} /> Свали
                        </button>
                      ) : null}
                      <button
                        onClick={() => hardDeleteListing(a.id, a.title)}
                        disabled={busy === a.id}
                        className="btn !py-1.5 !px-3 text-xs flex items-center gap-1 !bg-[hsl(var(--danger))] !text-white !border-[hsl(var(--danger))] hover:opacity-90"
                        data-testid={`hard-delete-${a.id}`}
                        title="Изтрий ИЗЦЯЛО (безвъзвратно)"
                      >
                        <Trash size={12} /> Изтрий
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Pagination — visible only when total exceeds one page */}
            {allTotal > ALL_PAGE_SIZE && (
              <div className="mt-6 flex items-center justify-between gap-3 flex-wrap" data-testid="admin-all-pagination">
                <div className="text-xs text-[hsl(var(--ink-muted))] font-mono">
                  {allOffset + 1}–{Math.min(allOffset + allListings.length, allTotal)} {t("forms.of", "от")} {allTotal}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setAllOffset(Math.max(0, allOffset - ALL_PAGE_SIZE))}
                    disabled={allOffset === 0}
                    className="btn btn-secondary !py-1.5 !px-4 text-xs disabled:opacity-40"
                    data-testid="admin-all-prev"
                  >
                    {t("forms.prev", "← Предишна")}
                  </button>
                  <span className="text-xs font-mono px-2">
                    {Math.floor(allOffset / ALL_PAGE_SIZE) + 1} / {Math.max(1, Math.ceil(allTotal / ALL_PAGE_SIZE))}
                  </span>
                  <button
                    onClick={() => setAllOffset(allOffset + ALL_PAGE_SIZE)}
                    disabled={allOffset + ALL_PAGE_SIZE >= allTotal}
                    className="btn btn-secondary !py-1.5 !px-4 text-xs disabled:opacity-40"
                    data-testid="admin-all-next"
                  >
                    {t("forms.next", "Следваща →")}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "users" && <AdminUsersTab currentUserId={user?.id} />}
        {tab === "settings" && <AdminSettingsTab />}
        {tab === "stripe" && <AdminStripeTab />}
        {tab === "audit" && <AdminAuditLogTab />}
        {tab === "makes" && <AdminMakesTab />}
        {tab === "notifications" && <AdminNotificationsTab />}
        {tab === "chat" && <AdminChatPanel />}
        {tab === "health" && <AdminHealthTab />}
        {tab === "templates" && <AdminEmailTemplatesTab />}
        {tab === "requests" && <AdminSellerRequestsTab />}
        {tab === "archive" && <AdminArchiveTab />}
        {tab === "unsold" && <AdminUnsoldTab />}

        {tab === "sold" && (
          <div className="mt-10">
            {sold.length === 0 ? (
              <EmptyState icon={Archive} title="Няма продадени търгове" sub="Когато търгове бъдат финализирани, ще се появят тук." />
            ) : (
              <div className="rounded-card border border-[hsl(var(--line))] overflow-hidden bg-white" data-testid="sold-list">
                <div className="hidden md:grid grid-cols-[1.6fr_1fr_0.9fr_0.8fr_1.2fr] gap-4 px-5 py-3 rule-b bg-[hsl(var(--surface))] overline text-[hsl(var(--ink-muted))]">
                  <span>Обява</span>
                  <span>Купувач</span>
                  <span>Финална цена</span>
                  <span>Комисионна 2%</span>
                  <span>Действие</span>
                </div>
                {sold.map((a) => {
                  const captured = a.premium_captured;
                  const status = a.winning_bid_preauth_status;
                  const commission = a.commission_eur || 0;
                  return (
                    <div key={a.id} className="grid grid-cols-1 md:grid-cols-[1.6fr_1fr_0.9fr_0.8fr_1.2fr] gap-4 items-center p-5 rule-b last:border-b-0" data-testid={`sold-${a.id}`}>
                      <div className="flex items-center gap-3 min-w-0">
                        {a.images?.[0] && <img src={a.images[0]} className="w-14 h-10 object-cover rounded-md shrink-0" alt="" />}
                        <div className="min-w-0">
                          <div className="font-semibold text-sm truncate">{a.title}</div>
                          <div className="text-xs text-[hsl(var(--ink-muted))]">{a.make} · {a.year}</div>
                        </div>
                      </div>
                      <div className="text-sm">
                        <div>{a.winner_name || "—"}</div>
                        <div className="text-xs text-[hsl(var(--ink-muted))] font-mono truncate">{a.winner_email || "—"}</div>
                      </div>
                      <div className="font-serif text-lg">{formatEUR(a.current_bid_eur)}</div>
                      <div>
                        <div className="font-serif text-lg">{formatEUR(commission)}</div>
                        <div className="text-[11px] text-[hsl(var(--ink-muted))] font-mono">
                          preauth: {status || "—"}
                        </div>
                      </div>
                      <div className="flex flex-col md:items-end gap-2">
                        {captured ? (
                          <span className="pill pill-live" data-testid={`captured-${a.id}`}><Check size={12} /> Преведено</span>
                        ) : status === "authorized" ? (
                          <div className="flex gap-2 flex-wrap">
                            <button onClick={() => capturePremium(a.id)} disabled={busy === a.id} className="btn btn-accent !py-2 !px-3 text-xs flex items-center gap-1" data-testid={`capture-${a.id}`}>
                              <DollarSign size={12} /> Capture {formatEUR(commission)}
                            </button>
                            <button onClick={() => releaseAll(a.id)} disabled={busy === a.id} className="btn btn-secondary !py-2 !px-3 text-xs flex items-center gap-1" data-testid={`release-${a.id}`}>
                              <Ban size={12} /> Освободи
                            </button>
                          </div>
                        ) : (
                          <span className="text-xs text-[hsl(var(--ink-muted))]">Preauth: {status || "—"}</span>
                        )}
                        <button onClick={() => setEditingId(a.id)} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`edit-sold-${a.id}`}>
                          <Edit3 size={12} /> Редактирай
                        </button>
                        <button onClick={() => reactivateListing(a.id, a.title)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1" data-testid={`reactivate-sold-${a.id}`}>
                          <RotateCcw size={12} /> Реактивирай
                        </button>
                        <button onClick={() => hardDeleteListing(a.id, a.title)} disabled={busy === a.id} className="btn btn-secondary !py-1.5 !px-3 text-xs flex items-center gap-1 !text-[hsl(var(--danger))] !border-[hsl(var(--danger))]/40 hover:!bg-[hsl(var(--danger))] hover:!text-white" data-testid={`delete-sold-${a.id}`}>
                          <Trash size={12} /> Изтрий
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {editingId && (
        <AdminEditModal
          auctionId={editingId}
          onClose={() => setEditingId(null)}
          onSaved={() => { loadPending(); loadSold(); loadAll(); }}
        />
      )}
      {bidsForAuction && (
        <AdminBidHistoryModal
          auctionId={bidsForAuction.id}
          auctionTitle={bidsForAuction.title}
          onClose={() => setBidsForAuction(null)}
        />
      )}
    </main>
  );
}

function EmptyState({ icon: Icon, title, sub }) {
  return (
    <div className="py-24 text-center rounded-card border border-[hsl(var(--line))]">
      <Icon size={32} className="mx-auto text-[hsl(var(--ink-muted))]" />
      <p className="mt-4 font-serif text-2xl">{title}</p>
      <p className="mt-2 text-sm text-[hsl(var(--ink-muted))]">{sub}</p>
    </div>
  );
}
