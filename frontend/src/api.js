export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function formatDetail(detail) {
  if (!detail) return "Something went wrong";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc)
          ? item.loc.filter((part) => part !== "body").join(".")
          : "";
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join(". ");
  }
  return "Request failed";
}

async function parseResponse(response) {
  if (response.status === 204) {
    return null;
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(formatDetail(data.detail), response.status);
  }
  return data;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  return parseResponse(response);
}

export function register(body) {
  return request("/auth/register", { method: "POST", body: JSON.stringify(body) });
}

export function login(email, password) {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout() {
  return request("/auth/logout", { method: "POST" });
}

export function getMe() {
  return request("/users/me");
}

export function updateMe(body) {
  return request("/users/me", { method: "PUT", body: JSON.stringify(body) });
}

export async function uploadProfilePhoto(file) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/users/me/photo", {
    method: "POST",
    credentials: "include",
    body,
  });
  return parseResponse(response);
}

export function getCategories() {
  return request("/categories");
}

export function getRequirements() {
  return request("/requirements");
}

export function getRequirement(id) {
  return request(`/requirements/${id}`);
}

export function createRequirement(body) {
  return request("/requirements", { method: "POST", body: JSON.stringify(body) });
}

export function updateRequirement(id, body) {
  return request(`/requirements/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function cancelRequirement(id) {
  return request(`/requirements/${id}`, { method: "DELETE" });
}

export function getOfferings() {
  return request("/offerings");
}

export function getOffering(id) {
  return request(`/offerings/${id}`);
}

export function createOffering(body) {
  return request("/offerings", { method: "POST", body: JSON.stringify(body) });
}

export function updateOffering(id, body) {
  return request(`/offerings/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deactivateOffering(id) {
  return request(`/offerings/${id}`, { method: "DELETE" });
}

export function getNotifications() {
  return request("/notifications");
}

export function getAdminSummary() {
  return request("/admin/summary");
}

export function getAdminAuditLogs() {
  return request("/admin/audit-logs");
}

export function getRfqs() {
  return request("/rfqs");
}

export function createRfq(body) {
  return request("/rfqs", { method: "POST", body: JSON.stringify(body) });
}

export function getRfq(id) {
  return request(`/rfqs/${id}`);
}

export function createQuotation(rfqId, body) {
  return request(`/rfqs/${rfqId}/quotations`, { method: "POST", body: JSON.stringify(body) });
}

export function acceptRfq(id) {
  return request(`/rfqs/${id}/accept`, { method: "POST" });
}

export function rejectRfq(id) {
  return request(`/rfqs/${id}/reject`, { method: "POST" });
}

export function getRfqTracking(id) {
  return request(`/rfqs/${id}/tracking`);
}

export function markRfqPaid(id) {
  return request(`/rfqs/${id}/payment/demo`, { method: "POST" });
}

export function markRfqShipped(id) {
  return request(`/rfqs/${id}/ship`, { method: "POST" });
}

export function refreshRfqOtp(id) {
  return request(`/rfqs/${id}/otp/refresh`, { method: "POST" });
}

export function verifyRfqOtp(id, otp) {
  return request(`/rfqs/${id}/verify-otp`, { method: "POST", body: JSON.stringify({ otp }) });
}

export function getSupplierProfile(id) {
  return request(`/suppliers/${id}/profile`);
}

export function getSupplierReviews(id) {
  return request(`/suppliers/${id}/reviews`);
}

export function createRfqReview(id, body) {
  return request(`/rfqs/${id}/review`, { method: "POST", body: JSON.stringify(body) });
}

export function markNotificationRead(id) {
  return request(`/notifications/${id}/read`, { method: "POST" });
}

export async function uploadDocument(file) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/documents", {
    method: "POST",
    credentials: "include",
    body,
  });
  return parseResponse(response);
}

export async function uploadSupplierDocument(file) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/supplier-documents", {
    method: "POST",
    credentials: "include",
    body,
  });
  return parseResponse(response);
}
