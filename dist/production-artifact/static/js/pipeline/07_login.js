// Authentication helpers

export function checkAuth() {
  // Check if user session is valid
  return !!document.cookie.match(/^session=/);
}

export function login(username, password) {
  // Login implementation
  return fetchAPI("/login", {method: "POST", body: {username, password}});
}
