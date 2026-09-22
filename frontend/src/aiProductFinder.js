const ALLOWED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const ALLOWED_EXT = /\.(jpe?g|png|webp)$/i;
const MAX_BYTES = 5_000_000;

export function isAllowedProductImage(file) {
  if (!file) return false;
  if (file.size > MAX_BYTES) return false;
  const typeOk = !file.type || ALLOWED_TYPES.has(file.type);
  const nameOk = ALLOWED_EXT.test(file.name || "");
  return typeOk && nameOk;
}

export function formatVisualSimilarity(value) {
  if (value == null || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return `${num.toFixed(1)}%`;
}
