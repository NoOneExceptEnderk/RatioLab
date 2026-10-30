(() => {
  const menu = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#main-nav');
  if (menu && nav) {
    menu.addEventListener('click', () => {
      const open = menu.getAttribute('aria-expanded') !== 'true';
      menu.setAttribute('aria-expanded', String(open));
      nav.classList.toggle('is-open', open);
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') {
        menu.setAttribute('aria-expanded', 'false'); nav.classList.remove('is-open'); menu.focus();
      }
    });
    nav.addEventListener('click', event => {
      if (event.target.closest('a')) { menu.setAttribute('aria-expanded', 'false'); nav.classList.remove('is-open'); }
    });
  }
  const dialog = document.querySelector('.screen-dialog');
  const open = document.querySelector('[data-open-screen]');
  if (dialog && open && typeof dialog.showModal === 'function') {
    open.disabled = false;
    open.addEventListener('click', () => dialog.showModal());
    dialog.querySelector('[data-close-screen]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  } else if (open) { open.disabled = true; open.style.cursor = 'default'; }
  const sidebarButton = document.querySelector('[data-docs-toggle]');
  const sidebar = document.querySelector('.docs-sidebar');
  if (sidebarButton && sidebar) sidebarButton.addEventListener('click', () => {
    const expanded = sidebarButton.getAttribute('aria-expanded') !== 'true';
    sidebarButton.setAttribute('aria-expanded', String(expanded));
    sidebar.classList.toggle('is-open', expanded);
  });
  // A quiet reading-position indicator; content stays visible without JavaScript.
  if (document.body.classList.contains('home-page') && window.matchMedia && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const progress = document.createElement('div');
    progress.className = 'reading-progress'; progress.setAttribute('aria-hidden', 'true');
    document.body.append(progress);
    let frame = 0;
    const draw = () => { frame = 0; const distance = document.documentElement.scrollHeight - window.innerHeight; const fraction = distance > 0 ? Math.max(0, Math.min(1, window.scrollY / distance)) : 0; progress.style.transform = `scaleX(${fraction})`; };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(draw); };
    window.addEventListener('scroll', schedule, {passive: true}); window.addEventListener('resize', schedule); schedule();
    window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', event => { if (event.matches) progress.hidden = true; else { progress.hidden = false; schedule(); } });
  }
  // Reveal already visible content once. Observer/API failures never hide the page.
  if (document.body.classList.contains('home-page') && 'IntersectionObserver' in window && Element.prototype.animate && window.matchMedia) {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const animations = new Set();
    try {
      const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (!entry.isIntersecting) return;
          observer.unobserve(entry.target);
          if (motion.matches) return;
          const animation = entry.target.animate([
            { transform: 'translateY(16px)', opacity: .7 },
            { transform: 'translateY(0)', opacity: 1 }
          ], { duration: 650, easing: 'cubic-bezier(.2,.6,.3,1)' });
          animations.add(animation);
          animation.addEventListener('finish', () => animations.delete(animation), { once: true });
        });
      }, { threshold: .12 });
      document.querySelectorAll('.section-heading, .capability-card, .workspace-frame, .community-copy, .section-intro').forEach(element => observer.observe(element));
      motion.addEventListener('change', event => { if (event.matches) { animations.forEach(animation => animation.cancel()); animations.clear(); } });
    } catch (_) { /* Content is visible by default. */ }
  }
  document.documentElement.classList.add('site-js');
})();
