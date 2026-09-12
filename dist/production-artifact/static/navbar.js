// Navbar JavaScript functionality
document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu functionality
    const mobileMenuToggle = document.getElementById('mobileMenuToggle');
    const mobileMenuOverlay = document.getElementById('mobileMenuOverlay');
    const mobileMenuClose = document.getElementById('mobileMenuClose');
    
    // Dropdown functionality
    const aboutDropdown = document.getElementById('aboutDropdown');
    const dropdownMenu = aboutDropdown?.nextElementSibling;
    
    // Mobile menu toggle
    function toggleMobileMenu() {
        const isOpen = mobileMenuOverlay.classList.contains('active');
        
        if (isOpen) {
            mobileMenuOverlay.classList.remove('active');
            mobileMenuToggle.setAttribute('aria-expanded', 'false');
            document.body.style.overflow = '';
        } else {
            mobileMenuOverlay.classList.add('active');
            mobileMenuToggle.setAttribute('aria-expanded', 'true');
            document.body.style.overflow = 'hidden';
        }
    }
    
    // Desktop dropdown toggle
    function toggleDropdown(e) {
        e.preventDefault();
        const isOpen = dropdownMenu.classList.contains('show');
        
        // Close all other dropdowns first
        document.querySelectorAll('.dropdown-menu.show').forEach(menu => {
            menu.classList.remove('show');
        });
        
        if (!isOpen) {
            dropdownMenu.classList.add('show');
            aboutDropdown.setAttribute('aria-expanded', 'true');
        } else {
            dropdownMenu.classList.remove('show');
            aboutDropdown.setAttribute('aria-expanded', 'false');
        }
    }
    
    // Event listeners
    if (mobileMenuToggle) {
        mobileMenuToggle.addEventListener('click', toggleMobileMenu);
    }
    
    if (mobileMenuClose) {
        mobileMenuClose.addEventListener('click', toggleMobileMenu);
    }
    
    if (aboutDropdown) {
        aboutDropdown.addEventListener('click', toggleDropdown);
    }
    
    // Close mobile menu when clicking on overlay
    if (mobileMenuOverlay) {
        mobileMenuOverlay.addEventListener('click', function(e) {
            if (e.target === mobileMenuOverlay) {
                toggleMobileMenu();
            }
        });
    }
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (aboutDropdown && dropdownMenu && 
            !aboutDropdown.contains(e.target) && 
            !dropdownMenu.contains(e.target)) {
            dropdownMenu.classList.remove('show');
            aboutDropdown.setAttribute('aria-expanded', 'false');
        }
    });
    
    // Handle escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            // Close mobile menu
            if (mobileMenuOverlay.classList.contains('active')) {
                toggleMobileMenu();
            }
            
            // Close dropdown
            if (dropdownMenu && dropdownMenu.classList.contains('show')) {
                dropdownMenu.classList.remove('show');
                aboutDropdown.setAttribute('aria-expanded', 'false');
            }
        }
    });
    
    // Handle window resize
    window.addEventListener('resize', function() {
        if (window.innerWidth > 768 && mobileMenuOverlay.classList.contains('active')) {
            toggleMobileMenu();
        }
    });
});