(() => {
  'use strict';
  const script = document.getElementById('docs-search-script');
  const root = script?.dataset.root || '';
  const dialog = document.getElementById('search-dialog');
  const input = document.getElementById('docs-search');
  const results = document.getElementById('search-results');
  const entries = window.RATIOLAB_SEARCH_INDEX || [];
  const normalize = text => String(text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  const searchable = entries.map(entry => ({entry, title: normalize(entry.title + ' ' + entry.page), content: normalize(entry.text)}));
  let opener;

  function message(text) {
    const paragraph = document.createElement('p');
    paragraph.textContent = text;
    results.append(paragraph);
  }

  function search() {
    results.replaceChildren();
    const query = normalize(input.value.trim());
    if (query.length < 2) {
      message('Enter at least two characters to search titles and content. Try “STEP”, “workspace” or “bearings”.');
      return;
    }
    const terms = query.split(/\s+/).filter(Boolean);
    const matches = searchable.filter(item => terms.every(term => item.title.includes(term) || item.content.includes(term)))
      .map(item => ({...item, score: (item.title.includes(query) ? 20 : 0) + terms.reduce((sum, term) => sum + (item.title.includes(term) ? 5 : 0) + (item.content.includes(term) ? 1 : 0), 0)}))
      .sort((a, b) => b.score - a.score || a.entry.url.localeCompare(b.entry.url));
    if (!matches.length) {
      message('No results. Try a different word or a shorter query.');
      return;
    }
    message(`${matches.length} result${matches.length === 1 ? '' : 's'}${matches.length > 24 ? ' · showing the first 24' : ''}`);
    for (const {entry, content} of matches.slice(0, 24)) {
      const link = document.createElement('a');
      link.href = root + entry.url;
      const title = document.createElement('strong');
      title.textContent = entry.title;
      const meta = document.createElement('small');
      meta.textContent = `${entry.page} · ${entry.language === 'en' ? 'EN' : 'IT'}`;
      const snippet = document.createElement('span');
      const position = Math.max(0, content.indexOf(terms[0]) - 55);
      snippet.textContent = `${position ? '…' : ''}${entry.text.slice(position, position + 170)}${entry.text.length > position + 170 ? '…' : ''}`;
      title.style.display = meta.style.display = snippet.style.display = 'block';
      meta.style.opacity = '.7';
      link.append(title, meta, snippet);
      link.addEventListener('click', () => dialog.close());
      results.append(link);
    }
  }

  function openSearch(event) {
    opener = event?.currentTarget || document.activeElement;
    if (!dialog.open) dialog.showModal();
    search();
    input.focus();
  }

  if (dialog && input && results) {
    document.querySelectorAll('[data-search-open]').forEach(button => button.addEventListener('click', openSearch));
    document.querySelectorAll('[data-search-close]').forEach(button => button.addEventListener('click', () => dialog.close()));
    dialog.addEventListener('close', () => { if (opener?.isConnected) opener.focus(); });
    dialog.addEventListener('click', event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close(); } });
    input.addEventListener('input', search);
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); dialog.close(); return; }
      if (event.key === 'ArrowDown') { const first = results.querySelector('a'); if (first) { event.preventDefault(); first.focus(); } }
      if (event.key === 'Enter') results.querySelector('a')?.click();
    });
    results.addEventListener('keydown', event => {
      const links = [...results.querySelectorAll('a')];
      const index = links.indexOf(document.activeElement);
      if (event.key === 'ArrowDown') { event.preventDefault(); links[Math.min(index + 1, links.length - 1)]?.focus(); }
      if (event.key === 'ArrowUp') { event.preventDefault(); if (index > 0) links[index - 1].focus(); else input.focus(); }
    });
    document.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openSearch(); }
    });
  }

  async function copyCode(text) {
    if (navigator.clipboard?.writeText) {
      try { await navigator.clipboard.writeText(text); return; } catch (_) { /* Use the file:// compatible fallback below. */ }
    }
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    const copied = document.execCommand('copy');
    area.remove();
    if (!copied) throw new Error('Clipboard unavailable');
  }
  document.querySelectorAll('[data-copy-target]').forEach(button => {
    button.addEventListener('click', async () => {
      const code = document.getElementById(button.dataset.copyTarget);
      if (!code) return;
      try { await copyCode(code.textContent); button.textContent = 'Copied'; }
      catch (_) { button.textContent = 'Select the code'; const selection = window.getSelection(); const range = document.createRange(); range.selectNodeContents(code); selection.removeAllRanges(); selection.addRange(range); }
      button.focus();
      window.setTimeout(() => { button.textContent = 'Copy'; }, 2200);
    });
  });
  document.documentElement.classList.add('docs-js');
})();
