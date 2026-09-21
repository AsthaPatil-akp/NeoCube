export function canSendMatchRequest(match) {
  if (!match) return false;
  if (match.rfq_id) return false;
  return !["RFQ_SENT", "RESPONDED", "ACCEPTED", "PAID", "SHIPPED", "RECEIVED"].includes(match.match_status);
}

export function notificationHref(item) {
  if (!item || item.related_id == null) return null;
  if (item.related_type === "rfq") return `/rfqs/${item.related_id}`;
  if (item.related_type === "requirement") return `/requirements/${item.related_id}`;
  return null;
}
