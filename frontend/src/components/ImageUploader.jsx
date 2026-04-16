import React, { useRef } from "react";
import { Upload, X, Image as ImageIcon } from "lucide-react";

const MAX = 8;
const MAX_SIZE = 2 * 1024 * 1024; // 2MB per image

export default function ImageUploader({ images = [], onChange }) {
  const ref = useRef(null);

  const compress = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement("canvas");
          const maxDim = 1600;
          let w = img.width, h = img.height;
          if (w > maxDim || h > maxDim) {
            if (w > h) { h = (h / w) * maxDim; w = maxDim; }
            else { w = (w / h) * maxDim; h = maxDim; }
          }
          canvas.width = w; canvas.height = h;
          const ctx = canvas.getContext("2d");
          ctx.drawImage(img, 0, 0, w, h);
          resolve(canvas.toDataURL("image/jpeg", 0.82));
        };
        img.onerror = reject;
        img.src = e.target.result;
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  const handleFiles = async (files) => {
    const arr = Array.from(files).slice(0, MAX - images.length);
    const compressed = [];
    for (const f of arr) {
      if (f.size > MAX_SIZE * 3) continue;
      try {
        const dataUrl = await compress(f);
        compressed.push(dataUrl);
      } catch (e) {}
    }
    onChange([...images, ...compressed]);
  };

  const remove = (idx) => onChange(images.filter((_, i) => i !== idx));

  return (
    <div data-testid="image-uploader">
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {images.map((src, i) => (
          <div key={i} className="relative aspect-[4/3] rounded-card border border-[hsl(var(--line))] overflow-hidden bg-[hsl(var(--surface))]">
            <img src={src} alt="" className="w-full h-full object-cover" />
            <button
              type="button"
              onClick={() => remove(i)}
              className="absolute top-2 right-2 bg-white/90 rounded-full p-1 border border-[hsl(var(--line))] hover:bg-[hsl(var(--ink))] hover:text-white transition"
              data-testid={`remove-image-${i}`}
            ><X size={12} /></button>
            {i === 0 && <span className="absolute bottom-2 left-2 pill">Корица</span>}
          </div>
        ))}
        {images.length < MAX && (
          <button
            type="button"
            onClick={() => ref.current?.click()}
            className="aspect-[4/3] rounded-card border-2 border-dashed border-[hsl(var(--line))] hover:border-[hsl(var(--ink))] transition flex flex-col items-center justify-center gap-2 text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]"
            data-testid="add-image-btn"
          >
            <Upload size={22} />
            <span className="text-xs">Добави снимки</span>
          </button>
        )}
      </div>
      <input ref={ref} type="file" accept="image/*" multiple className="hidden" onChange={(e) => handleFiles(e.target.files)} data-testid="image-file-input" />
      <p className="mt-2 text-xs text-[hsl(var(--ink-muted))] flex items-center gap-1.5">
        <ImageIcon size={11} /> JPEG/PNG · автоматично се оптимизират до 1600px · първата е корица
      </p>
    </div>
  );
}
