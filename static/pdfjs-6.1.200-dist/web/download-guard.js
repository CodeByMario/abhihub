// Anti-piracy: hide download/print buttons when ?download=false
(function() {
  if (new URLSearchParams(location.search).get('download') === 'false') {
    document.documentElement.setAttribute('data-no-download', 'true');
  }
})();