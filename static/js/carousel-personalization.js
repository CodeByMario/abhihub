/**
 * AbhiHub Personalized Carousel
 * Dynamic slides with user context, progress tracking, and community milestones
 */

const CarouselPersonalization = {
    // Manual community stats (update these periodically)
    communityStats: {
        telegramMembers: 500,
        whatsappMembers: 250,
        topContributor: 'Aayush Gupta',
        newFilesThisWeek: 12
    },

    // Get user name from global variable (set by template)
    get userName() {
        return window.ABHIHUB_USER_NAME || '';
    },

    // Get time-based greeting
    getGreeting() {
        const hour = new Date().getHours();
        if (hour < 12) return { emoji: '🌅', text: 'Good morning' };
        if (hour < 17) return { emoji: '☀️', text: 'Good afternoon' };
        if (hour < 21) return { emoji: '🌆', text: 'Good evening' };
        return { emoji: '🌙', text: 'Good night' };
    },

    // Get last viewed files from localStorage
    getRecentActivity() {
        try {
            return JSON.parse(localStorage.getItem('abhihub_recent') || '[]');
        } catch { return []; }
    },

    // Track file view (call this when user opens a file)
    trackView(subject, fileName, fileType, filePath, recordId) {
        const recent = this.getRecentActivity();
        const entry = {
            subject,
            fileName,
            fileType: fileType || 'unknown',
            filePath: filePath || '',
            recordId: recordId || '',
            time: Date.now()
        };
        // Remove duplicates based on filePath
        const filtered = recent.filter(r => r.filePath !== filePath);
        filtered.unshift(entry);
        localStorage.setItem('abhihub_recent', JSON.stringify(filtered.slice(0, 10)));

        // Update the recently viewed section if visible
        this.populateRecentlyViewed();
    },

    // Populate the "Recently Viewed" section
    populateRecentlyViewed() {
        const section = document.getElementById('recently-viewed-section');
        const listContainer = document.getElementById('recently-viewed-list');

        if (!section || !listContainer) return;

        const recent = this.getRecentActivity();

        if (recent.length === 0) {
            section.style.display = 'none';
            return;
        }

        // Show section
        section.style.display = 'block';

        // Generate HTML for recent files
        const html = recent.slice(0, 8).map(file => {
            const iconMap = {
                'notes': 'notes.gif',
                'pyq': 'papers.gif',
                'papers': 'papers.gif',
                'practical': 'practicals.gif',
                'practicals': 'practicals.gif'
            };
            const icon = iconMap[file.fileType?.toLowerCase()] || 'default.png';
            const timeAgo = this.getTimeAgo(file.time);

            return `
                <a href="${file.recordId ? '/resource/' + encodeURIComponent(file.recordId) : '/view_pdf?pdf_name=' + encodeURIComponent(file.filePath)}" class="file-card" title="View ${file.fileType}">
                    <img src="/static/premium/icon/${icon}" alt="${file.fileType}">
                    <span class="file-card-title">${file.subject}</span>
                    <span class="file-card-meta">${file.fileName}</span>
                    <span class="file-card-date">${timeAgo}</span>
                </a>
            `;
        }).join('');

        listContainer.innerHTML = html;
    },

    // Get human-readable time ago
    getTimeAgo(timestamp) {
        const seconds = Math.floor((Date.now() - timestamp) / 1000);

        if (seconds < 60) return 'Just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
        return `${Math.floor(seconds / 604800)}w ago`;
    },

    // Generate personalized slides
    generateSlides() {
        const slides = [];
        const greeting = this.getGreeting();
        const recent = this.getRecentActivity();

        // 1. WELCOME SLIDE - Personalized greeting
        if (this.userName) {
            slides.push(`${greeting.emoji} ${greeting.text}, <strong>${this.userName}</strong>! Ready to level up your prep? 🚀`);
        } else {
            slides.push(`${greeting.emoji} ${greeting.text}, learner! Welcome to AbhiHub — your study companion 📚`);
        }

        // 2. PROGRESS SLIDE - Resume where left off
        if (recent.length > 0) {
            const last = recent[0];
            slides.push(`📖 Continue where you left off: <strong>${last.subject}</strong> — ${last.fileName} <span class="text-blue-600">→</span>`);
        }

        // 3. COMMUNITY MILESTONE SLIDE
        slides.push(`🎉 <strong>${this.communityStats.telegramMembers}+</strong> students joined our Telegram this month! 
      <a href="https://t.me/abhi_hub" target="_blank" class="text-blue-600 font-semibold hover:underline">Join now →</a>`);

        // 4. TOP CONTRIBUTOR SLIDE
        slides.push(`🏆 Top contributor: <strong>${this.communityStats.topContributor}</strong> — Check out their notes!`);

        // 5. NEW CONTENT SLIDE
        slides.push(`✨ <strong>${this.communityStats.newFilesThisWeek}</strong> new files uploaded this week! Explore the latest AIML, DBMS, and more.`);

        // 6. SOCIAL LINKS SLIDE
        slides.push(`💬 Join our community! 
      <a href="https://whatsapp.com/channel/0029VbAixWgLCoWwQwX1D91I" target="_blank" class="text-green-600 font-semibold hover:underline">WhatsApp Channel</a> • 
      <a href="https://chat.whatsapp.com/F1tnqrY0CUC8diuNiJjExz" target="_blank" class="text-green-600 font-semibold hover:underline">Group</a> • 
      <a href="https://t.me/abhi_hub" target="_blank" class="text-blue-600 font-semibold hover:underline">Telegram</a>`);

        // 7. SHARE SLIDE
        slides.push(`🤝 Love AbhiHub? Share it with your friends and enjoy free premium features!`);

        // 8. SWIPE HINT (mobile only)
        if (window.innerWidth <= 768) {
            slides.push(`👆 <em>Swipe</em> → for your personalized picks and updates!`);
        }

        return slides;
    },

    // Initialize the carousel
    init() {
        const textDiv = document.getElementById('carousel-text');
        const carousel = document.getElementById('updates-instructions-carousel');
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');

        if (!textDiv || !carousel) {
            console.log('[Carousel] Elements not found, skipping personalization');
            return;
        }

        const slides = this.generateSlides();
        let current = 0;

        const showSlide = (idx) => {
            textDiv.classList.add('opacity-0');
            setTimeout(() => {
                textDiv.innerHTML = slides[idx];
                textDiv.classList.remove('opacity-0');
            }, 300);
        };

        const nextSlide = () => {
            current = (current + 1) % slides.length;
            showSlide(current);
        };

        const prevSlide = () => {
            current = (current - 1 + slides.length) % slides.length;
            showSlide(current);
        };

        // Button handlers
        if (prevBtn) prevBtn.onclick = prevSlide;
        if (nextBtn) nextBtn.onclick = nextSlide;

        // Auto-advance every 6 seconds
        setInterval(nextSlide, 6000);

        // Touch/swipe support for mobile
        let touchStartX = 0;
        carousel.addEventListener('touchstart', e => touchStartX = e.touches[0].clientX);
        carousel.addEventListener('touchend', e => {
            const diff = touchStartX - e.changedTouches[0].clientX;
            if (Math.abs(diff) > 50) diff > 0 ? nextSlide() : prevSlide();
        });

        // Show first slide
        showSlide(current);
        console.log('[Carousel] Personalized carousel initialized with', slides.length, 'slides');

        // Populate recently viewed section
        this.populateRecentlyViewed();
    }
};

// Expose globally
window.CarouselPersonalization = CarouselPersonalization;
window.trackFileView = (subject, fileName, fileType, filePath) =>
    CarouselPersonalization.trackView(subject, fileName, fileType, filePath);

// Auto-initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => CarouselPersonalization.init());

