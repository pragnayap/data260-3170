/**
 * HW4 + HW5 - the axios layer.
 *
 * This file is unchanged from HW4 except for routesApi.list(), which now
 * unwraps the paginated envelope. The Redux thunks in store/incidentsSlice.js
 * call these functions; keeping the HTTP details here means the slice has no
 * axios knowledge and the API has no Redux knowledge.
 */

import axios from "axios";

// withCredentials is what makes the browser send the s3170_db_session cookie
// cross-origin (React on 8471, FastAPI on 8470); forgetting it fails silently
// as a 401 instead of an obvious network error.
const client = axios.create({
  baseURL: "http://localhost:8470",
  withCredentials: true,
});

export const authApi = {
  signup: (name, email, password) =>
    client.post("/api/auth/signup", { name, email, password }).then((r) => r.data),
  login: (email, password) =>
    client.post("/api/auth/login", { email, password }).then((r) => r.data),
  logout: () => client.post("/api/auth/logout"),
  me: () => client.get("/api/auth/me").then((r) => r.data),
};

export const incidentsApi = {
  list: (page = 1, pageSize = 20, impl = "fixed") =>
    client
      .get("/api/incidents", { params: { page, page_size: pageSize, impl } })
      .then((r) => r.data),
  get: (id) => client.get(`/api/incidents/${id}`).then((r) => r.data),
  create: (incident) => client.post("/api/incidents", incident).then((r) => r.data),
  update: (id, incident) => client.put(`/api/incidents/${id}`, incident).then((r) => r.data),
  remove: (id) => client.delete(`/api/incidents/${id}`),
};

export const routesApi = {
  // HW5: GET /api/routes is paginated now -- {items, total, page, page_size}.
  // The dropdown only wants the rows, so unwrap here rather than in every caller.
  list: () => client.get("/api/routes").then((r) => r.data.items),

  // HW5 Part 1.II additions, available for the relationship-query demo.
  get: (id) => client.get(`/api/routes/${id}`).then((r) => r.data),
  create: (route) => client.post("/api/routes", route).then((r) => r.data),
  update: (id, route) => client.put(`/api/routes/${id}`, route).then((r) => r.data),
  remove: (id) => client.delete(`/api/routes/${id}`),
  incidents: (id, page = 1, pageSize = 20) =>
    client
      .get(`/api/routes/${id}/incidents`, { params: { page, page_size: pageSize } })
      .then((r) => r.data),
};

export default client;