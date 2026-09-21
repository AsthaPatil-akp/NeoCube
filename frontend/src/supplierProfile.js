export function formatAverageRating(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return number.toFixed(1);
}

export function supplierProfilePath(supplierId, match) {
  if (!supplierId) return null;
  const params = new URLSearchParams();
  if (match?.id && !match.rfq_id) params.set("match", String(match.id));
  const query = params.toString();
  return query ? `/suppliers/${supplierId}?${query}` : `/suppliers/${supplierId}`;
}
