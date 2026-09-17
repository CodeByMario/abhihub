// API client helpers

export const API_BASE = "/api";

export async function fetchAPI(endpoint, options = {}) {
  const url = ${API_BASE}${endpoint};
  const init = {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...options.headers
    }
  };
  if (options.body) init.body = JSON.stringify(options.body);
  const res = await fetch(url, init);
  return res.json();
}
