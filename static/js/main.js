

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const header = document.querySelector('[data-header]');
const menuToggle = document.querySelector('[data-menu-toggle]');
const navPanel = document.querySelector('[data-nav-panel]');
const navLinks = [...document.querySelectorAll('.nav-link')];
const backTop = document.querySelector('[data-back-top]');

const setHeaderState = () => {
    header?.classList.toggle('is-scrolled', window.scrollY > 16);
    backTop?.classList.toggle('is-visible', window.scrollY > 650);
};

window.addEventListener('scroll', setHeaderState, { passive: true });
setHeaderState();

menuToggle?.addEventListener('click', () => {
    const isOpen = navPanel?.classList.toggle('is-open');
    menuToggle.setAttribute('aria-expanded', String(Boolean(isOpen)));
});

document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener('click', (event) => {
        const href = link.getAttribute('href');
        if (href === '#') return;
        const target = document.querySelector(href);
        if (!target) return;

        event.preventDefault();
        target.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'start' });
        navPanel?.classList.remove('is-open');
        menuToggle?.setAttribute('aria-expanded', 'false');
    });
});

const sectionObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const id = entry.target.getAttribute('id');
        navLinks.forEach((link) => link.classList.toggle('active', link.getAttribute('href') === `#${id}`));
    });
}, { rootMargin: '-45% 0px -45% 0px', threshold: 0 });

document.querySelectorAll('main section[id]').forEach((section) => sectionObserver.observe(section));

const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
        if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
        } else {
            entry.target.classList.remove('is-visible');
        }
    });
}, { rootMargin: '-8% 0px -8% 0px', threshold: 0.12 });

document.querySelectorAll('.reveal').forEach((element) => {
    if (prefersReducedMotion) {
        element.classList.add('is-visible');
    } else {
        revealObserver.observe(element);
    }
});

document.querySelectorAll('.expertise-list').forEach((ticker) => {
    if (prefersReducedMotion || ticker.dataset.cloned === 'true') return;

    [...ticker.children].forEach((item) => {
        const clone = item.cloneNode(true);
        clone.setAttribute('aria-hidden', 'true');
        ticker.appendChild(clone);
    });

    ticker.dataset.cloned = 'true';
});

const countersSection = document.querySelector('[data-counters]');
const animateCounter = (counter) => {
    const target = Number(counter.dataset.count || 0);
    const duration = 1200;
    const start = performance.now();

    const tick = (now) => {
        const progress = Math.min((now - start) / duration, 1);
        counter.textContent = Math.floor(target * progress).toLocaleString('ar-SA');
        if (progress < 1) requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
};

if (countersSection) {
    const counterObserver = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
            countersSection.querySelectorAll('[data-count]').forEach(animateCounter);
            counterObserver.disconnect();
        }
    }, { threshold: 0.35 });

    counterObserver.observe(countersSection);
}

document.querySelectorAll('.faq-item button').forEach((button) => {
    button.addEventListener('click', () => {
        const item = button.closest('.faq-item');
        const isOpen = item.classList.toggle('is-open');
        button.setAttribute('aria-expanded', String(isOpen));
        button.querySelector('b').textContent = isOpen ? '-' : '+';
    });
});

const track = document.querySelector('[data-testimonial-track]');
const next = document.querySelector('[data-slider-next]');
const prev = document.querySelector('[data-slider-prev]');
let slideIndex = 0;

const moveSlider = (direction) => {
    if (!track) return;
    const total = track.children.length;
    slideIndex = (slideIndex + direction + total) % total;
    track.scrollTo({ left: (getComputedStyle(track).direction === 'rtl' ? -1 : 1) * slideIndex * track.clientWidth, behavior: prefersReducedMotion ? 'auto' : 'smooth' });
};

next?.addEventListener('click', () => moveSlider(1));
prev?.addEventListener('click', () => moveSlider(-1));

if (track && track.children.length > 1 && !prefersReducedMotion) {
    window.setInterval(() => moveSlider(1), 6500);
}

backTop?.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: prefersReducedMotion ? 'auto' : 'smooth' });
});

document.querySelectorAll('[data-client-form]').forEach((form) => {
    form.addEventListener('submit', (event) => {
        const invalid = [...form.querySelectorAll('[required]')].find((field) => !field.value.trim());
        if (!invalid) return;

        event.preventDefault();
        invalid.focus();
        invalid.setAttribute('aria-invalid', 'true');
    });
});

const errors = document.querySelector("form .form-alert:not(.success)");
if (errors) errors.closest("section")?.scrollIntoView({block: "start"});
