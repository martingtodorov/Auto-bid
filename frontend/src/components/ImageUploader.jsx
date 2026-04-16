import React, { useRef } from "react";
import { Upload, X, Image as ImageIcon, AlertCircle, Check } from "lucide-react";

const MAX_SIZE = 2 * 1024 * 1024; // 2MB per image

export default function ImageUploader({
  images = [],
  onChange,
  max = 8,
  min = 0,
  label,
  helper,
  testId = "image-uploader",
}) {
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
    const arr = Array.from(files).slice(0, max - images.length);
    const compressed = [];
    for (const f of arr) {
      if (f.size > MAX_SIZE * 3) continue;
      try {
        const dataUrl = await compress(f);
        compressed.push(dataUrl);
      } catch (e) { /* skip */ }
    }
    onChange([...images, ...compressed]);
  };

  const remove = (idx) => onChange(images.filter((_, i) => i !== idx));

  const meetsMin = images.length >= min;

  return (
    <div data-testid={testId} className="rounded-card border border-[hsl(var(--line))] bg-white p-4">
      {label && (
        <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
          <div>
            <div className="text-sm font-semibold">{label}</div>
            {helper && <div className="text-xs text-[hsl(var(--ink-muted))] mt-0.5">{helper}</div>}
          </div>
          <div className={`flex items-center gap-1.5 text-xs font-mono ${meetsMin ? "text-[hsl(var(--accent))]" : "text-[hsl(var(--ink-muted))]"}`}>
            {meetsMin ? <Check size={12} /> : <AlertCircle size={12} />}
            {images.length}/{max} {min > 0 && <span>· мин. {min}</span>}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5">
        {images.map((src, i) => (
          <div key={i} className="relative aspect-[4/3] rounded-md border border-[hsl(var(--line))] overflow-hidden bg-[hsl(var(--surface))]">
            <img src={src} alt="" className="w-full h-full object-cover" />
            <button
              type="button"
              onClick={() => remove(i)}
              className="absolute top-1.5 right-1.5 bg-white/90 rounded-full p-1 border border-[hsl(var(--line))] hover:bg-[hsl(var(--ink))] hover:text-white transition"
              data-testid={`${testId}-remove-${i}`}
            ><X size={12} /></button>
          </div>
        ))}
        {images.length < max && (
          <button
            type="button"
            onClick={() => ref.current?.click()}
            className="aspect-[4/3] rounded-md border-2 border-dashed border-[hsl(var(--line))] hover:border-[hsl(var(--ink))] transition flex flex-col items-center justify-center gap-1.5 text-[hsl(var(--ink-muted))] hover:text-[hsl(var(--ink))]"
            data-testid={`${testId}-add`}
          >
            <Upload size={18} />
            <span className="text-[11px]">Добави</span>
          </button>
        )}
      </div>
      <input ref={ref} type="file" accept="image/*" multiple className="hidden" onChange={(e) => handleFiles(e.target.files)} data-testid={`${testId}-input`} />
      {!label && (
        <p className="mt-2 text-xs text-[hsl(var(--ink-muted))] flex items-center gap-1.5">
          <ImageIcon size={11} /> JPEG/PNG · автоматично се оптимизират до 1600px
        </p>
      )}
    </div>
  );
}
