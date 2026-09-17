// Route helpers for SPA navigation

export function navigate(path) {
  history.pushState(null, "", path);
  // Could trigger a custom event for route changes
  document.dispatchEvent(new CustomEvent("route-change", { detail: { path } }));
}
