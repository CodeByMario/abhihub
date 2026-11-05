// Utility functions
// dom-selector, css-manipulator, event-helper

export function $(selector) {
  return document.querySelector(selector);
}

export function on(event, selector, handler) {
  document.addEventListener(event, (e) => {
    if (e.target.matches(selector)) handler(e));
  });
}

export function ajax(options) {
  const xhr = new XMLHttpRequest();
  xhr.open(options.method || "GET", options.url);
  xhr.onload = () => options.success(xhr.responseText);
  xhr.send();
}
