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
  document.documentElement.classList.add('site-js');
})();
