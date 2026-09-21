export const TRACK_STEPS = ["Accepted", "Payment", "Shipped", "Received"];

const STEP_BY_STATUS = {
  ACCEPTED: 0,
  PAYMENT_PENDING: 0,
  PAID: 1,
  PAYMENT_CONFIRMED: 1,
  SHIPPED: 2,
  RECEIVED: 3,
  COMPLETED: 3,
};

export function trackStatus(item) {
  return String(item?.tracking?.current_status || item?.status || "").toUpperCase();
}

export function trackStepIndex(status) {
  const value = String(status || "").toUpperCase();
  return Object.prototype.hasOwnProperty.call(STEP_BY_STATUS, value) ? STEP_BY_STATUS[value] : -1;
}

export function isTrackable(status) {
  return trackStepIndex(status) >= 0;
}

export function nextTrackAction(status, role) {
  const value = String(status || "").toUpperCase();
  const who = String(role || "").toUpperCase();
  if ((value === "ACCEPTED" || value === "PAYMENT_PENDING") && who === "CLIENT") {
    return { method: "pay", label: "Simulate Successful Payment" };
  }
  if ((value === "PAID" || value === "PAYMENT_CONFIRMED") && who === "SUPPLIER") {
    return { method: "ship", label: "Mark as Shipped" };
  }
  return null;
}

export function sortTrackItems(items) {
  return [...items].sort((left, right) => {
    const leftDone = trackStepIndex(trackStatus(left)) >= 3 ? 1 : 0;
    const rightDone = trackStepIndex(trackStatus(right)) >= 3 ? 1 : 0;
    if (leftDone !== rightDone) return leftDone - rightDone;
    return new Date(right.created_at || 0) - new Date(left.created_at || 0);
  });
}
