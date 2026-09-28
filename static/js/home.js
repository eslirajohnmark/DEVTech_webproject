// ==========================================
// HOME PAGE JAVASCRIPT
// ==========================================

document.addEventListener('DOMContentLoaded', function() {

    // ============================================
    // MOBILE MENU TOGGLE
    // ============================================
    const menuToggle = document.getElementById('menuToggle');
    const navLinks = document.getElementById('navLinks');

    if (menuToggle && navLinks) {
        menuToggle.addEventListener('click', function() {
            navLinks.classList.toggle('open');
        });
    }

    // ============================================
    // SMOOTH SCROLL FOR HOME, ABOUT, CONTACT
    // ============================================
    
    // Home link - scroll to top
    const homeLink = document.getElementById('navHome');
    if (homeLink) {
        homeLink.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Close mobile menu if open
            if (navLinks && navLinks.classList.contains('open')) {
                navLinks.classList.remove('open');
            }
            
            // Scroll to top smoothly
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
            
            // Update URL without hash
            history.pushState(null, null, window.location.pathname);
        });
    }

    // About link - scroll to about section
    const aboutLink = document.getElementById('navAbout');
    if (aboutLink) {
        aboutLink.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Close mobile menu if open
            if (navLinks && navLinks.classList.contains('open')) {
                navLinks.classList.remove('open');
            }
            
            const aboutSection = document.getElementById('about');
            if (aboutSection) {
                aboutSection.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
                history.pushState(null, null, '#about');
            }
        });
    }

    // Contact link (navigation) - scroll to contact section
    const contactLink = document.getElementById('navContact');
    if (contactLink) {
        contactLink.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Close mobile menu if open
            if (navLinks && navLinks.classList.contains('open')) {
                navLinks.classList.remove('open');
            }
            
            const contactSection = document.getElementById('contact');
            if (contactSection) {
                contactSection.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
                history.pushState(null, null, '#contact');
            }
        });
    }

    // Footer Contact link - scroll to contact section
    const footerContactLink = document.getElementById('footerContactLink');
    if (footerContactLink) {
        footerContactLink.addEventListener('click', function(e) {
            e.preventDefault();
            
            const contactSection = document.getElementById('contact');
            if (contactSection) {
                contactSection.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
                history.pushState(null, null, '#contact');
            }
        });
    }

    // ============================================
    // KEYBOARD SHORTCUT: Ctrl + Shift + L
    // Admin Login - Hidden
    // ============================================
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.shiftKey && (e.key === 'l' || e.key === 'L')) {
            e.preventDefault();
            
            const currentPath = window.location.pathname;
            if (currentPath === '/admin/login' || currentPath === '/admin/login/') {
                return;
            }
            
            window.location.href = '/admin/login';
        }
    });

    // ============================================
    // NAVBAR SCROLL EFFECT
    // ============================================
    const navbar = document.getElementById('navbar');
    if (navbar) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 50) {
                navbar.style.boxShadow = '0 4px 30px rgba(0, 0, 0, 0.06)';
            } else {
                navbar.style.boxShadow = 'none';
            }
        });
    }

    // ============================================
    // CONTACT FORM HANDLING
    // ============================================
    const contactForm = document.getElementById('contactForm');
    if (contactForm) {
        contactForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const name = document.getElementById('contactName').value.trim();
            const email = document.getElementById('contactEmail').value.trim();
            const subject = document.getElementById('contactSubject').value.trim();
            const message = document.getElementById('contactMessage').value.trim();
            
            if (!name || !email || !subject || !message) {
                alert('Please fill in all fields.');
                return;
            }
            
            // Simple email validation
            if (!email.includes('@') || !email.includes('.')) {
                alert('Please enter a valid email address.');
                return;
            }
            
            // Show success message
            alert('Thank you for your message! We\'ll get back to you soon.');
            contactForm.reset();
        });
    }

    // ============================================
    // KEYWORD LIST ITEM CLICK (Troubleshoot)
    // ============================================
    const keywordItems = document.querySelectorAll('.hp-keyword-list li');
    keywordItems.forEach(item => {
        item.addEventListener('click', function() {
            const issue = this.getAttribute('data-issue');
            if (issue) {
                // Redirect to troubleshooting page with query parameter
                window.location.href = '/user/troubleshooting?issue=' + encodeURIComponent(issue);
            }
        });
    });

    // ============================================
    // SERVICE ITEM CLICK
    // ============================================
    const serviceItems = document.querySelectorAll('.hp-service-item');
    serviceItems.forEach(item => {
        item.addEventListener('click', function() {
            const serviceId = this.getAttribute('data-service');
            if (serviceId) {
                // Redirect to service request with service ID
                window.location.href = '/user/services';
            }
        });
    });

    // ============================================
    // STEP ITEM CLICK
    // ============================================
    const stepItems = document.querySelectorAll('.hp-step');
    stepItems.forEach(item => {
        item.addEventListener('click', function() {
            const step = this.getAttribute('data-step');
            if (step) {
                // Could scroll to relevant section or show more info
                console.log('Step ' + step + ' clicked');
            }
        });
    });

    console.log('✅ DEVTech Home page loaded');
});