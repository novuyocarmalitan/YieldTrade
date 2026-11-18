import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";
const TOKEN_KEY = "yt_token";

export const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Token ${token}`;
  return config;
});

export const auth = {
  save: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
  has: () => Boolean(localStorage.getItem(TOKEN_KEY)),
};

/** Paginated lists come back as {results}; single objects come back as-is. */
export const unwrap = (res) => res.data.results ?? res.data;

/** Turn any API failure into one readable sentence. */
export function errorText(e) {
  const d = e?.response?.data;
  if (!e?.response) return "Could not reach the server. Is the backend running?";
  if (e.response.status === 429) return "Too many attempts. Please wait a while and try again.";
  if (!d || typeof d === "string") return "Something went wrong on the server.";
  if (d.detail) return d.detail;
  return Object.entries(d)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${Array.isArray(v) ? v.join(" ") : v}`)
    .join(" | ");
}
