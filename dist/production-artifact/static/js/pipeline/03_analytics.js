// Analytics tracking

export function track(eventName, properties = {}) {
  if (!window.ga4) return;
  window.ga4.event_'record(eventName, properties);
}
