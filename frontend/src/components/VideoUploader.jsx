import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Video, X, Play, Loader2 } from "lucide-react";
import { api } from "../lib/apiClient";

/**
 * Sell-flow video uploader. One video per listing, ≤60 s, ≤100 MB.
 *
 * Flow:
 *  1. User picks a file (`<input type=file accept=video/*>`).
 *  2. We probe duration client-side via a hidden `<video>` element.
 *     If > 60 s → reject locally so no network bytes are wasted.
 *  3. Upload as multipart to `/api/sell/video-upload`. Backend re-probes
 *     with ffprobe (defense-in-depth) and starts an async AV1 transcode
 *     that swaps `video_url` on the auction doc once ready.
 *  4. Successful response → call `onUpload({video_url, poster_url, ...})`.
 *
 * Preview shows a play button overlay on top of the poster JPG so the
 * user can confirm what was uploaded before submitting.
 */
export default function VideoUploader({ value, onChange, onError }) {
  const { t } = useTranslation();
  const inputRef = useRef(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [localPreview, setLocalPreview] = useState(null);

  const MAX_BYTES = 100 * 1024 * 1024;
  const MAX_DURATION = 60;

  const probeDurationLocal = (file) =>
    new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const v = document.createElement("video");
      v.preload = "metadata";
      v.muted = true;
      v.onloadedmetadata = () => {
        const d = v.duration;
        URL.revokeObjectURL(url);
        resolve(d);
      };
      v.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("Cannot read video metadata"));
      };
      v.src = url;
    });

  const pick = () => inputRef.current?.click();

  const onPick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = ""; // allow re-pick of same file
    if (file.size > MAX_BYTES) {
      onError?.(t("sell.video_err_too_large", "Видеото е по-голямо от 100 MB."));
      return;
    }
    let dur = null;
    try {
      dur = await probeDurationLocal(file);
    } catch {
      onError?.(t("sell.video_err_unreadable", "Не може да се прочете видеото. Опитайте друг формат (MP4)."));
      return;
    }
    if (dur > MAX_DURATION + 0.5) {
      onError?.(
        t("sell.video_err_too_long", "Видеото е {{d}} сек. Максимумът е 60 сек.", {
          d: Math.ceil(dur),
        })
      );
      return;
    }
    setLocalPreview(URL.createObjectURL(file));
    setUploading(true);
    setProgress(0);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/sell/video-upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (!e.total) return;
          setProgress(Math.round((e.loaded * 100) / e.total));
        },
      });
      onChange({
        video_url: data.video_url,
        video_poster_url: data.video_poster_url,
        video_duration_seconds: data.video_duration_seconds,
      });
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || "Upload failed";
      onError?.(detail);
      setLocalPreview(null);
    } finally {
      setUploading(false);
    }
  };

  const remove = () => {
    setLocalPreview(null);
    setProgress(0);
    onChange({ video_url: null, video_poster_url: null, video_duration_seconds: null });
  };

  const hasVideo = !!value?.video_url || !!localPreview;

  return (
    <div className="rounded-card border border-[hsl(var(--line))] bg-[hsl(var(--surface))] p-4" data-testid="video-uploader">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-sm font-medium flex items-center gap-2">
            <Video size={16} />
            {t("sell.video_label", "Видео на колата (по желание)")}
          </div>
          <div className="text-xs text-[hsl(var(--ink-muted))] mt-0.5">
            {t("sell.video_helper", "Едно видео до 60 секунди · MP4 / MOV / WebM · до 100 MB")}
          </div>
        </div>
        {hasVideo && !uploading && (
          <button
            type="button"
            onClick={remove}
            className="text-xs text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--danger))] flex items-center gap-1"
            data-testid="video-remove-btn"
          >
            <X size={14} /> {t("forms.remove", "Премахни")}
          </button>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="video/mp4,video/quicktime,video/webm,video/x-m4v,video/*"
        className="hidden"
        onChange={onPick}
        data-testid="video-file-input"
      />

      {!hasVideo && !uploading && (
        <button
          type="button"
          onClick={pick}
          className="w-full py-8 rounded-card border-2 border-dashed border-[hsl(var(--line))] hover:border-[hsl(var(--accent))] text-sm text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))] transition-colors flex flex-col items-center gap-2"
          data-testid="video-pick-btn"
        >
          <Video size={28} />
          <span>{t("sell.video_pick_cta", "Избери видео")}</span>
        </button>
      )}

      {uploading && (
        <div className="text-center py-6" data-testid="video-uploading">
          <Loader2 className="animate-spin mx-auto mb-2" size={20} />
          <div className="text-sm text-[hsl(var(--ink-muted))]">
            {t("sell.video_uploading", "Качване... {{p}}%", { p: progress })}
          </div>
          <div className="mt-3 h-1.5 bg-[hsl(var(--line))] rounded-full overflow-hidden max-w-xs mx-auto">
            <div
              className="h-full bg-[hsl(var(--accent))] transition-[width] duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {hasVideo && !uploading && (
        <div className="relative aspect-video rounded-card overflow-hidden bg-black" data-testid="video-preview">
          {value?.video_poster_url ? (
            <img
              src={value.video_poster_url}
              alt="video poster"
              className="absolute inset-0 w-full h-full object-cover"
            />
          ) : (
            <video src={localPreview} className="absolute inset-0 w-full h-full object-cover" muted />
          )}
          <div className="absolute inset-0 flex items-center justify-center bg-black/30">
            <div className="w-16 h-16 rounded-full bg-white/95 flex items-center justify-center shadow-lg">
              <Play size={28} className="text-black ml-1" fill="currentColor" />
            </div>
          </div>
          {value?.video_duration_seconds && (
            <div className="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-2 py-0.5 rounded">
              {Math.round(value.video_duration_seconds)}s
            </div>
          )}
        </div>
      )}
    </div>
  );
}
