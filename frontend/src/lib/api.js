const BASE = "/api";

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    // Try to parse DRF's structured error payloads (`{field: [msg, ...]}`)
    // so callers can surface field-level messages in their UI. Falls back
    // to the raw status text if the body isn't JSON.
    let parsed = null;
    try { parsed = JSON.parse(text); } catch { /* not JSON */ }
    const err = new Error(`API ${res.status}: ${text || res.statusText}`);
    err.status = res.status;
    err.payload = parsed;
    throw err;
  }
  return res.json();
}

export const api = {
  summary: () => request("/summary/"),
  searchProfessors: ({ q = "", department = "", institution = "", sort = "score" } = {}) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (department) p.set("department", department);
    if (institution) p.set("institution", institution);
    if (sort) p.set("sort", sort);
    return request(`/professors/?${p.toString()}`);
  },
  createProfessor: ({ name, institution, department = null }) =>
    request(`/professors/`, {
      method: "POST",
      body: JSON.stringify({
        name,
        institution,
        ...(department ? { department } : {}),
      }),
    }),
  professor: (id) => request(`/professors/${id}/`),
  professorReviews: (id, { cursor = null, limit = 20 } = {}) => {
    const p = new URLSearchParams();
    if (cursor) p.set("cursor", cursor);
    if (limit) p.set("limit", String(limit));
    return request(`/professors/${id}/reviews/?${p.toString()}`);
  },
  departments: () => request("/departments/"),
  institutions: ({ q = "", limit = 15 } = {}) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (limit) p.set("limit", String(limit));
    return request(`/institutions/?${p.toString()}`);
  },
  compare: (ids) => request(`/compare/?ids=${ids.join(",")}`),
  similarProfessors: (id, { k = 5, warm, scope } = {}) => {
    const p = new URLSearchParams();
    if (k) p.set("k", String(k));
    if (warm !== undefined) p.set("warm", warm ? "1" : "0");
    if (scope) p.set("scope", scope);
    return request(`/professors/${id}/similar/?${p.toString()}`);
  },
};
