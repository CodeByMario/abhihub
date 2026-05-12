// Web Worker for handling search operations
self.onmessage = function (e) {
  const { fileData, filters } = e.data;
  const { fileName, author, type, subject, year } = filters;

  // Helper function to sanitize strings for matching
  const sanitize = (str) => {
    if (!str) return '';
    return str.toString().toLowerCase().replace(/[^a-z0-9]/g, '');
  };

  const cleanFileName = sanitize(fileName);
  const cleanAuthor = sanitize(author);

  const results = fileData.filter(f => {
    // File name matching (matches against file name, subject, and subject code)
    const matchesFileName = !cleanFileName ||
      sanitize(f["file-name"]).includes(cleanFileName) ||
      sanitize(f.subject).includes(cleanFileName) ||
      sanitize(f.subject_code).includes(cleanFileName);

    // Author matching
    const matchesAuthor = !cleanAuthor ||
      sanitize(f.author).includes(cleanAuthor);

    // Exact matches for dropdowns
    const matchesType = !type || f.type === type;
    const matchesSubject = !subject || f.subject === subject;
    const matchesYear = !year || f.year === year;

    return matchesFileName && matchesAuthor && matchesType && matchesSubject && matchesYear;
  });

  self.postMessage(results);
};