/**
 * Verification System for Store Room
 * Allows users to verify labeled papers
 */

// ==========================================
// State
// ==========================================
let currentVerifyingPaper = null;
let verificationFilter = '';

// ==========================================
// Verification Modal
// ==========================================
function openVerificationModal(paper) {
    currentVerifyingPaper = paper;
    const modal = document.getElementById('verificationModal');
    
    // Populate modal with paper details
    document.getElementById('verifyPreviewImg').src = paper.url || '';
    document.getElementById('verifyCollege').textContent = paper.college_name || '-';
    document.getElementById('verifySubject').textContent = paper.subject_name || '-';
    document.getElementById('verifyExamType').textContent = paper.exam_type || '-';
    document.getElementById('verifyYear').textContent = paper.year || '-';
    document.getElementById('verifyBranch').textContent = paper.branch || '-';
    document.getElementById('verifySemesters').textContent = (paper.semesters || []).join(', ') || '-';
    document.getElementById('verificationCount').textContent = `${paper.verification_count || 0}/7`;
    
    modal.classList.add('active');
}

function closeVerificationModal() {
    const modal = document.getElementById('verificationModal');
    modal.classList.remove('active');
    currentVerifyingPaper = null;
}

async function submitVerification() {
    if (!currentVerifyingPaper) return;
    
    const btn = document.getElementById('verifyConfirmBtn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Verifying...';
    
    try {
        const response = await fetch('/store-room/api/verify', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                paper_id: currentVerifyingPaper.id
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Use store_room.js toast function
            if (typeof showToast !== 'undefined') {
                showToast('Thank you! Paper verified successfully.', 'success');
                
                if (result.verified) {
                    showToast('Paper now has 7+ verifications and moved to verified section!', 'success');
                }
            }
            
            // Update file card status
            updateFileCardAfterVerification(currentVerifyingPaper.id, result.verified);
            
            closeVerificationModal();
        } else {
            if (typeof showToast !== 'undefined') {
                showToast(result.message || 'Verification failed', 'error');
            }
        }
    } catch (error) {
        console.error('Verification error:', error);
        if (typeof showToast !== 'undefined') {
            showToast('An error occurred during verification', 'error');
        }
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

function updateFileCardAfterVerification(paperId, isVerified) {
    const fileCards = document.querySelectorAll('.file-card');
    fileCards.forEach(card => {
        const data = JSON.parse(card.getAttribute('data-file'));
        if (data.id === paperId) {
            if (isVerified) {
                card.classList.remove('pending-verification');
                card.classList.add('verified');
                let badge = card.querySelector('.label-badge');
                if (!badge) {
                    badge = document.createElement('div');
                    badge.className = 'label-badge';
                    card.appendChild(badge);
                }
                badge.textContent = '✓ Verified';
            }
        }
    });
}

// ==========================================
// Filtering
// ==========================================
function initializeVerificationFilter() {
    const filter = document.getElementById('verificationFilter');
    if (!filter) return;
    
    filter.addEventListener('change', (e) => {
        verificationFilter = e.target.value;
        applyFilters();
    });
}

function applyFilters() {
    const fileCards = document.querySelectorAll('.file-card');
    
    fileCards.forEach(card => {
        let show = true;
        
        // Apply verification filter
        if (verificationFilter) {
            if (verificationFilter === 'pending') {
                show = card.classList.contains('pending-verification');
            } else if (verificationFilter === 'verified') {
                show = card.classList.contains('verified');
            }
        }
        
        card.style.display = show ? '' : 'none';
    });
}

// Close modal when clicking outside
document.addEventListener('click', function(e) {
    const modal = document.getElementById('verificationModal');
    if (e.target === modal) {
        closeVerificationModal();
    }
});

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initializeVerificationFilter();
});
