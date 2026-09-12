function toggleFileAction(btn, action) {
    // action is 'like' or 'bookmark'
    const documentId = btn.getAttribute('data-id');
    if (!documentId) return;

    // Prevent default anchor click if inside an anchor
    event.preventDefault();
    event.stopPropagation();

    fetch(`/api/${action}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ document_id: documentId })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                // Update UI
                const countSpan = btn.querySelector('.count');
                const svgIcon = btn.querySelector('svg');

                if (action === 'like') {
                    countSpan.textContent = data.like_count > 0 ? data.like_count : '';
                    if (data.is_liked) {
                        btn.classList.add('active');
                        btn.style.color = '#ef4444';
                        svgIcon.setAttribute('fill', 'currentColor');
                    } else {
                        btn.classList.remove('active');
                        btn.style.color = '#6b7280';
                        svgIcon.setAttribute('fill', 'none');
                    }
                } else if (action === 'bookmark') {
                    countSpan.textContent = data.bookmark_count > 0 ? data.bookmark_count : '';
                    if (data.is_bookmarked) {
                        btn.classList.add('active');
                        btn.style.color = '#3b82f6';
                        svgIcon.setAttribute('fill', 'currentColor');
                    } else {
                        btn.classList.remove('active');
                        btn.style.color = '#6b7280';
                        svgIcon.setAttribute('fill', 'none');
                    }
                }
            } else if (data.message === 'Unauthorized' || data.message.includes('No API key')) {
                alert('Please login to use this feature.');
            } else {
                console.error('Error:', data.message);
                // Ignore UI if fails or redirect to login
                if (data.message.includes('auth')) {
                    alert('Please login to use this feature.');
                }
            }
        })
        .catch(err => {
            console.error('Network Error:', err);
        });
}

function openComments(eventOrId, documentIdStr) {
    let documentId = documentIdStr || eventOrId;
    if (typeof eventOrId === 'object' && eventOrId.preventDefault) {
        eventOrId.preventDefault();
        eventOrId.stopPropagation();
    } else if (window.event) {
        window.event.preventDefault();
        window.event.stopPropagation();
    }
    // Modal logic for comments
    const modal = document.createElement('div');
    modal.className = 'comment-modal-overlay';
    modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;justify-content:center;align-items:center;';

    const content = document.createElement('div');
    content.style.cssText = 'background:white;width:90%;max-width:500px;border-radius:12px;padding:20px;max-height:80vh;display:flex;flex-direction:column;';

    const header = document.createElement('div');
    header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #e5e7eb;padding-bottom:10px;margin-bottom:15px;';
    header.innerHTML = '<h3 style="margin:0;font-size:1.2rem;color:#1f2937;">Comments</h3><button onclick="this.closest(\'.comment-modal-overlay\').remove()" style="background:none;border:none;font-size:1.5rem;cursor:pointer;">&times;</button>';

    const commentsList = document.createElement('div');
    commentsList.className = 'comments-list';
    commentsList.style.cssText = 'flex:1;overflow-y:auto;margin-bottom:15px;display:flex;flex-direction:column;gap:10px;';
    commentsList.innerHTML = '<div style="text-align:center;color:#6b7280;padding:20px;">Loading comments...</div>';

    const form = document.createElement('form');
    form.style.cssText = 'display:flex;gap:10px;border-top:1px solid #e5e7eb;padding-top:15px;';
    form.innerHTML = `
        <input type="text" placeholder="Add a comment..." style="flex:1;padding:10px;border:1px solid #e5e7eb;border-radius:6px;outline:none;" required>
        <button type="submit" style="background:#2563eb;color:white;border:none;padding:10px 15px;border-radius:6px;cursor:pointer;">Post</button>
    `;

    form.onsubmit = function (e) {
        e.preventDefault();
        const input = form.querySelector('input');
        const text = input.value.trim();
        if (!text) return;

        fetch(`/api/interactions/comments/${documentId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: text })
        }).then(res => res.json()).then(data => {
            if (data.success) {
                input.value = '';
                loadComments(documentId, commentsList);
                // Dispatch event or update UI count
                const cardBtns = document.querySelectorAll(`button.comment-btn[data-id="${documentId}"] .count`);
                cardBtns.forEach(span => {
                    const newCount = parseInt(span.textContent || '0') + 1;
                    span.textContent = newCount > 0 ? newCount : '';
                });
            } else {
                alert('Failed to post comment. Please login.');
            }
        });
    };

    content.appendChild(header);
    content.appendChild(commentsList);
    content.appendChild(form);
    modal.appendChild(content);

    // Close on overlay click
    modal.onclick = function (e) {
        if (e.target === modal) modal.remove();
    };

    document.body.appendChild(modal);

    // Fetch comments
    loadComments(documentId, commentsList);
}

function loadComments(documentId, container) {
    fetch(`/api/interactions/comments/${documentId}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                container.innerHTML = '';
                const comments = data.comments || [];
                if (comments.length === 0) {
                    container.innerHTML = '<div style="text-align:center;color:#6b7280;padding:20px;">No comments yet. Be the first!</div>';
                    return;
                }
                comments.forEach(c => {
                    const div = document.createElement('div');
                    div.style.cssText = 'background:#f9fafb;padding:10px;border-radius:8px;';
                    const authorStr = (c.profiles && c.profiles.full_name) ? c.profiles.full_name : 'User';
                    div.innerHTML = `
                    <div style="font-weight:600;font-size:0.9rem;color:#374151;margin-bottom:4px;">${authorStr}</div>
                    <div style="color:#4b5563;font-size:0.95rem;">${c.content}</div>
                `;
                    container.appendChild(div);
                });
            }
        });
}
