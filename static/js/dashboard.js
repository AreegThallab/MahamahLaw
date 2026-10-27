(() => {
    const sidebar = document.querySelector('.sidebar');
    const toggle = document.querySelector('.sidebar-toggle');
    const backdrop = document.querySelector('.drawer-backdrop');
    const setDrawer = (open) => {
        document.body.classList.toggle('drawer-open', open);
        toggle?.setAttribute('aria-expanded', String(open));
        if (backdrop) backdrop.hidden = !open;
        if (sidebar && matchMedia('(max-width: 900px)').matches) sidebar.inert = !open;
        if (open) sidebar?.querySelector('a')?.focus();
    };
    const syncDrawer = () => {
        if (matchMedia('(min-width: 901px)').matches) {
            setDrawer(false);
            if (sidebar) sidebar.inert = false;
        } else if (sidebar) {
            sidebar.inert = !document.body.classList.contains('drawer-open');
        }
    };
    toggle?.addEventListener('click', () => setDrawer(!document.body.classList.contains('drawer-open')));
    backdrop?.addEventListener('click', () => { setDrawer(false); toggle?.focus(); });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && document.body.classList.contains('drawer-open')) {
            setDrawer(false); toggle?.focus();
        }
        if (event.key === 'Tab' && document.body.classList.contains('drawer-open')) {
            const controls = [...sidebar.querySelectorAll('a, button')];
            const first = controls[0], last = controls[controls.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
            if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
    });
    window.addEventListener('resize', syncDrawer);
    syncDrawer();

    const region = document.querySelector('[data-live-region]');
    const status = document.querySelector('[data-live-status]');
    if (!region || document.body.dataset.liveEnabled !== 'true') return;
    let busy = false;
    const update = async () => {
        if (busy || document.visibilityState !== 'visible') return;
        if (region.contains(document.activeElement) && document.activeElement.matches('input, select, textarea, button')) return;
        if (window.getSelection()?.toString()) return;
        busy = true;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8000);
        const url = new URL(region.dataset.liveUrl, location.origin);
        url.search = location.search;
        url.searchParams.set('mode', region.dataset.liveMode);
        try {
            const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', signal: controller.signal, headers: {'Accept': 'application/json'}});
            if (!response.ok || response.redirected) throw new Error('Session or network unavailable');
            const data = await response.json();
            if (typeof data.html !== 'string') throw new Error('Invalid response');
            const scroll = [...region.querySelectorAll('.table-scroll')].map(table => table.scrollLeft);
            region.innerHTML = data.html;
            region.querySelectorAll('.table-scroll').forEach((table, index) => { table.scrollLeft = scroll[index] || 0; });
            if (status) { status.textContent = ''; status.hidden = true; }
        } catch {
            if (status) { status.textContent = 'تعذّر التحديث التلقائي؛ يمكنك تحديث الصفحة.'; status.hidden = false; }
        } finally {
            clearTimeout(timeout);
            busy = false;
        }
    };
    const timer = setInterval(update, 15000);
    window.addEventListener('pagehide', () => clearInterval(timer), {once: true});
})();
