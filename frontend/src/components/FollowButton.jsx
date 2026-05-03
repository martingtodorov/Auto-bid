import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { UserPlus, UserCheck } from "lucide-react";
import { toast } from "sonner";

import { api } from "../lib/apiClient";
import { useAuth } from "../lib/auth";

/**
 * Follow / Unfollow button with viewer-state + count hydration.
 *
 * Reuses the existing `/api/users/:id/follow-status` endpoint, so the
 * component can live on ProfilePage AND DealerPage without re-fetching
 * through a wrapper. Anonymous users see a disabled CTA that nudges
 * them to log in instead of silently erroring.
 */
export default function FollowButton({ userId, className = "", showCount = true }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [state, setState] = useState({ loading: true, following: false, count: 0 });

  const isSelf = user && user.id === userId;

  useEffect(() => {
    let cancelled = false;
    api.get(`/users/${userId}/follow-status`)
      .then((r) => {
        if (cancelled) return;
        setState({
          loading: false,
          following: !!r.data.following,
          count: r.data.followers_count ?? 0,
        });
      })
      .catch(() => !cancelled && setState({ loading: false, following: false, count: 0 }));
    return () => { cancelled = true; };
  }, [userId]);

  const toggle = async () => {
    if (!user) {
      toast.error(t("follow.login_required", "Влезте в профила си, за да следвате."));
      return;
    }
    if (isSelf) return;
    const wasFollowing = state.following;
    // Optimistic update — rollback on failure keeps the UI honest.
    setState((p) => ({
      ...p,
      following: !wasFollowing,
      count: wasFollowing ? Math.max(0, p.count - 1) : p.count + 1,
    }));
    try {
      if (wasFollowing) {
        const r = await api.delete(`/users/${userId}/follow`);
        setState({ loading: false, following: false, count: r.data.followers_count ?? 0 });
      } else {
        const r = await api.post(`/users/${userId}/follow`);
        setState({ loading: false, following: true, count: r.data.followers_count ?? 0 });
      }
    } catch (e) {
      setState((p) => ({
        ...p,
        following: wasFollowing,
        count: wasFollowing ? p.count + 1 : Math.max(0, p.count - 1),
      }));
      toast.error(e?.response?.data?.detail || t("follow.error", "Неуспех. Опитайте отново."));
    }
  };

  if (isSelf) return null;

  return (
    <button
      onClick={toggle}
      disabled={state.loading}
      data-testid={state.following ? "unfollow-btn" : "follow-btn"}
      aria-pressed={state.following}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold border transition-all disabled:opacity-50 ${
        state.following
          ? "bg-[hsl(var(--surface))] border-[hsl(var(--line))] text-[hsl(var(--ink))] hover:bg-[hsl(var(--danger))]/10 hover:text-[hsl(var(--danger))] hover:border-[hsl(var(--danger))]/40"
          : "bg-[hsl(var(--accent))] border-transparent text-white hover:bg-[hsl(var(--accent))]/85"
      } ${className}`}
    >
      {state.following
        ? <><UserCheck size={14} /> {t("follow.following", "Следвате")}</>
        : <><UserPlus size={14} /> {t("follow.follow", "Следвай")}</>}
      {showCount && state.count > 0 && (
        <span className="ml-1 text-xs opacity-70">· {state.count}</span>
      )}
    </button>
  );
}
