// Reusable UI components

export function createElement(tag, props = {}, children = []) {
  const el = document.createElement(tag);
  Object.keys(props).forEach(key => {
    if (key === "style") {
      Object.assign(el.style, props.style);
    } else if (key === "className") {
      el.className = props.className;
    } else {
      el.setAttribute(key, props[key]);
    }
  });
  children.forEach(child => {
    if (typeof child === "string") {
      el.textContent = child;
    } else {
      el.appendChild(child);
    }
  });
  return el;
}
