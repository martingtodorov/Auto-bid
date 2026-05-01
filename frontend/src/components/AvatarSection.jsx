import React, { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Camera, Trash2 } from "lucide-react";
import { api } from "../lib/apiClient";
import { useAuth, formatError } from "../lib/auth";
import Avatar from "./Avatar";

/** File → base64 data URL. */
function readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

const MAX_BYTES = 6 * 1024 * 1024;

export default function AvatarSection() {
  const { t } = useTranslation();
  const { user, refresh } = useAuth();
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  if (!user) return null;

  const onPick = () => fileRef.current?.click();

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setErr("");
    setMsg("");
    if (!/^image\//.test(file.type)) {
      setErr(t("avatar.err_not_image", "Файлът не е изображение."));
      return;
    }
    if (file.size > MAX_BYTES) {
      setErr(t("avatar.err_too_large", "Файлът е твърде голям (макс. 6 MB)."));
      return;
    }
    setBusy(true);
    try {
      const dataUrl = await readAsDataURL(file);
      await api.post("/me/avatar", { image: dataUrl });
      await refresh();
      setMsg(t("avatar.saved", "Снимката е качена"));
      setTimeout(() => setMsg(""), 2200);
    } catch (e2) {
      setErr(formatError(e2));
    } finally {
      setBusy(false);
    }
  };

  const onRemove = async () => {
    if (!window.confirm(t("avatar.confirm_remove", "Премахни снимката?"))) return;
    setErr("");
    setMsg("");
    setBusy(true);
    try {
      await api.delete("/me/avatar");
      await refresh();
      setMsg(t("avatar.removed", "Снимката е премахната"));
      setTimeout(() => setMsg(""), 2200);
    } catch (e2) {
      setErr(formatError(e2));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="mt-8 rounded-card border border-[hsl(var(--line))] bg-white p-6 lg:p-8"
      data-testid="avatar-section"
    >
      <div className="flex items-center gap-3">
        <Camera size={18} className="text-[hsl(var(--accent))]" />
        <h2 className="font-serif text-2xl">
          {t("avatar.title", "Профилна снимка")}
        </h2>
      </div>
      <p className="mt-3 text-sm text-[hsl(var(--ink-muted))]">
        {t(
          "avatar.subtitle",
          "Тази снимка ще се показва до името ви на търгове и коментари. Препоръчителен формат: квадратна, мин. 256×256 px."
        )}
      </p>

      <div className="mt-6 flex items-center gap-5">
        <Avatar
          url={user.avatar_url}
          name={user.name}
          size={88}
          testId="avatar-current"
        />
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={onPick}
            disabled={busy}
            className="btn btn-primary !py-2 !px-4 text-sm disabled:opacity-50 inline-flex items-center gap-2"
            data-testid="avatar-upload-btn"
          >
            <Camera size={14} />
            {user.avatar_url
              ? t("avatar.change", "Смени снимката")
              : t("avatar.upload", "Качи снимка")}
          </button>
          {user.avatar_url && (
            <button
              type="button"
              onClick={onRemove}
              disabled={busy}
              className="text-xs text-[hsl(var(--danger))] hover:underline inline-flex items-center gap-1 self-start"
              data-testid="avatar-remove-btn"
            >
              <Trash2 size={12} /> {t("avatar.remove", "Премахни снимката")}
            </button>
          )}
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          onChange={onFile}
          className="hidden"
          data-testid="avatar-file-input"
        />
      </div>

      {(msg || err) && (
        <div className="mt-4 text-sm">
          {msg && <span className="text-[hsl(var(--accent))]">{msg}</span>}
          {err && (
            <span
              className="text-[hsl(var(--danger))]"
              data-testid="avatar-error"
            >
              {err}
            </span>
          )}
        </div>
      )}
    </section>
  );
}
