export function getRoleHome(user) {
  return user?.role === "admin" ? "/dashboard" : "/report";
}