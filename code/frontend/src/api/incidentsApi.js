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
  list: () => client.get("/api/routes").then((r) => r.data),
};

export default client;
