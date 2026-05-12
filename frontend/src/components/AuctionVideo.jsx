import { useRef, useState } from "react";
import { Play } from "lucide-react";
import { useTranslation } from "react-i18next";

/**
 * Auction video player.
 *
 * Renders a poster image with a centred play-button overlay until the
 * user clicks; on click we swap in a `<video>` element with native
 * controls + autoplay (muted, to satisfy mobile autoplay policy). This
 * pattern is lightweight (no JS player), accessible (the button has a
 * clear label) and makes it obvious the asset is a video, not a still.
 *
 * `<source>` MIME chain (AV1 → H.264) lets modern browsers (Chrome 90+,
 * Firefox 89+, Edge) load the ~40% smaller AV1 file while Safari and
 * older Android fall back to the original H.264 upload — no broken
 * playback for anyone.
 */
export default function AuctionVideo({ src, srcAv1, poster, duration }) {
  const { t } = useTranslation();
  const videoRef = useRef(null);
  const [playing, setPlaying] = useState(false);

  if (!src && !srcAv1) return null;

  const start = () => {
    setPlaying(true);
    // Give the <video> a tick to mount before .play()
    setTimeout(() => {
      try {
        videoRef.current?.play();
      } catch {
        /* user can press the native play control */
      }
    }, 50);
  };

  return (
    <figure
      className="relative aspect-video rounded-card overflow-hidden bg-black border border-[hsl(var(--line))]"
      data-testid="auction-video"
    >
      {!playing && (
        <button
          type="button"
          onClick={start}
          className="group absolute inset-0 w-full h-full flex items-center justify-center cursor-pointer"
          aria-label={t("auction.play_video", "Пусни видеото")}
          data-testid="auction-video-play-btn"
        >
          {poster && (
            <img
              src={poster}
              alt={t("auction.video_poster_alt", "Видео визуализация")}
              className="absolute inset-0 w-full h-full object-cover"
              loading="lazy"
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-transparent to-black/40" />
          <div className="relative w-20 h-20 rounded-full bg-white/95 flex items-center justify-center shadow-2xl transition-transform duration-200 group-hover:scale-110">
            <Play size={36} className="text-black ml-1.5" fill="currentColor" />
          </div>
          {duration ? (
            <div className="absolute bottom-3 right-3 bg-black/70 text-white text-xs px-2.5 py-1 rounded font-mono tabular-nums">
              {Math.round(duration)}s
            </div>
          ) : null}
          <div className="absolute top-3 left-3 bg-black/70 text-white text-xs px-2.5 py-1 rounded uppercase tracking-wider">
            {t("auction.video_badge", "Видео")}
          </div>
        </button>
      )}
      {playing && (
        <video
          ref={videoRef}
          poster={poster || undefined}
          controls
          playsInline
          muted
          className="absolute inset-0 w-full h-full"
        >
          {/* Browsers pick the first <source> they can decode. AV1 first
              (modern + smaller); H.264 fallback for Safari / older. */}
          {srcAv1 && <source src={srcAv1} type='video/mp4; codecs="av01.0.05M.08"' />}
          {src && <source src={src} type="video/mp4" />}
        </video>
      )}
    </figure>
  );
}
