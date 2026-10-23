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
            
            const submitBtn = contactForm.querySelector('button[type="submit"]');
            if (submitBtn) submitBtn.disabled = true;
            fetch('/contact', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.getElementById('contactCsrf')?.value || ''
                },
                body: JSON.stringify({ name, email, subject, message })
            })
                .then(res => res.json().catch(() => ({
                    success: false,
                    message: res.status === 429
                        ? 'Too many messages. Please try again later.'
                        : 'Something went wrong. Please try again.'
                })))
                .then(data => {
                    alert(data.message || (data.success ? 'Message sent.' : 'Could not send your message.'));
                    if (data.success) contactForm.reset();
                })
                .catch(() => alert('Could not reach the server. Please try again.'))
                .finally(() => { if (submitBtn) submitBtn.disabled = false; });
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

    // ============================================
    // HERO ANIMATION - a repair moving through the booking stages
    // ============================================
    initRepairScene();

    console.log('✅ DEVTech Home page loaded');
});

function initRepairScene() {
    const scene = document.getElementById('repairScene');
    if (!scene) return;

    // Same stages (and icons) customers see on their Monitor Device page.
    const STAGES = [
        { label: 'Requested', icon: 'fa-inbox' },
        { label: 'Technician assigned', icon: 'fa-user-check' },
        { label: 'Diagnosis', icon: 'fa-stethoscope' },
        { label: 'On repair', icon: 'fa-screwdriver-wrench' },
        { label: 'Ready for collection', icon: 'fa-box-open' },
        { label: 'Released', icon: 'fa-hand-holding-heart' }
    ];
    const label = document.getElementById('sceneStageLabel');
    const icon = document.getElementById('sceneStageIcon');
    const bar = document.getElementById('sceneProgress');
    const dots = scene.querySelectorAll('.hp-ticket-dots li');

    function show(index) {
        const stage = STAGES[index];
        scene.dataset.stage = String(index);
        label.style.opacity = '0';
        setTimeout(function () {
            label.textContent = stage.label;
            icon.className = 'fas ' + stage.icon;
            label.style.opacity = '1';
        }, 180);
        bar.style.width = (index / (STAGES.length - 1) * 100) + '%';
        dots.forEach(function (dot, i) {
            dot.classList.toggle('is-done', i < index);
            dot.classList.toggle('is-current', i === index);
        });
    }

    // Respect "reduce motion": show the finished repair, no cycling.
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        show(4);
        return;
    }

    let index = 0;
    let timer = null;
    let visible = true;
    // Linger a little longer on the outcome stages.
    const delayFor = function (i) { return i >= 4 ? 2600 : 1900; };

    function step() {
        index = (index + 1) % STAGES.length;
        show(index);
        schedule();
    }
    function schedule() {
        clearTimeout(timer);
        if (visible && !document.hidden) timer = setTimeout(step, delayFor(index));
    }
    function setPaused(paused) {
        scene.classList.toggle('is-paused', paused);
        if (paused) clearTimeout(timer); else schedule();
    }

    if ('IntersectionObserver' in window) {
        new IntersectionObserver(function (entries) {
            visible = entries[0].isIntersecting;
            setPaused(!visible);
        }, { threshold: 0.15 }).observe(scene);
    }
    document.addEventListener('visibilitychange', function () {
        setPaused(document.hidden || !visible);
    });

    show(0);
    schedule();
}