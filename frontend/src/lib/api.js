// One place for every backend call. All paths are relative, so the Vite
// proxy (dev) or VITE_API_BASE_URL (prod) decides where they go.
const BASE = import.meta.env.VITE_API_BASE_URL || "/api";

async function request(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const err = new Error(`API ${res.status}: ${text || res.statusText}`);
    err.status = res.status;
    try { err.payload = JSON.parse(text); } catch { err.payload = null; }
    throw err;
  }
  return res.json();
}

export const api = {
  summary: () => request("/summary/"),
  departments: () => request("/departments/"),
  professor: (id) => request(`/professors/${id}/`),
  professorReviews: (id, { cursor = null, limit = 10 } = {}) => {
    const p = new URLSearchParams();
    if (cursor) p.set("cursor", cursor);
    p.set("limit", String(limit));
    return request(`/professors/${id}/reviews/?${p.toString()}`);
  },
  searchProfessors: ({ q = "", department = "", sort = "score" } = {}) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (department) p.set("department", department);
    if (sort) p.set("sort", sort);
    return request(`/professors/?${p.toString()}`);
  },
};
