// AJAX helpers

export function get(url, onSuccess) {
  ajax({url, method: "GET", success: onSuccess});
}

export function post(url, data, onSuccess) {
  ajax({url, method: "POST", data: JSON.stringify(data), success: onSuccess, contentType: "application/json"});
}
