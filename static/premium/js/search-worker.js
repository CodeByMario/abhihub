// Web Worker for handling search operations
self.onmessage = function (e) {
  const { fileData, filters } = e.data;
  const { fileName, author, type, subject, year, college, sort } = filters;

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
    const matchesCollege = !college || f.college === college;

    return matchesFileName && matchesAuthor && matchesType && matchesSubject && matchesYear && matchesCollege;
  });

  // Sort results
  if (sort) {
    if (sort === 'views_desc') {
      results.sort((a, b) => (b.view_count || 0) - (a.view_count || 0));
    } else if (sort === 'likes_desc') {
      results.sort((a, b) => (b.like_count || 0) - (a.like_count || 0));
    } else if (sort === 'bookmarks_desc') {
      results.sort((a, b) => (b.bookmark_count || 0) - (a.bookmark_count || 0));
    } else if (sort === 'date_desc') {
      results.sort((a, b) => {
        const dA = a.date ? new Date(a.date) : new Date(0);
        const dB = b.date ? new Date(b.date) : new Date(0);
        return dB - dA;
      });
    }
  }

  self.postMessage(results);
};