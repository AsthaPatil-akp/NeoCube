export function portalPath(user) {
  if (!user) return "/login";
  if (user.role === "SUPPLIER") return "/supplier";
  if (user.role === "ADMIN") return "/admin";
  return "/dashboard";
}
