/* Local, low-entropy platform detection. No requests or automatic downloads. */
(function (root) {
  function detect(ua, platform, mobileHint) {
    const s = String(ua || '').toLowerCase();
    const p = String(platform || '').toLowerCase();
    if (mobileHint || /android|iphone|ipad|ipod/.test(s) || (/mac/.test(p) && /mobile/.test(s))) return { label: 'RatioLab is a desktop app. Choose a desktop version below.', choice: '' };
    if (/cros|chrome os/.test(s + ' ' + p)) return { label: 'ChromeOS detected. Choose a desktop version below.', choice: '' };
    if (/windows/.test(s) || /win/.test(p)) {
      if (/arm|aarch64/.test(s)) return { label: 'Windows detected. Choose a compatible desktop version.', choice: '' };
      if (/win64|wow64|x86_64|amd64|x64/.test(s)) return { label: 'Windows detected · x64 installer', choice: 'windows' };
      return { label: 'Windows detected. Choose your desktop version.', choice: '' };
    }
    if (/macintosh|mac os|macintel/.test(s) || /mac/.test(p)) return { label: 'macOS detected. Choose Apple Silicon or Intel.', choice: '' };
    if (/linux/.test(s) || /linux/.test(p)) {
      if (/arm|aarch64/.test(s + ' ' + p)) return { label: 'Linux detected. The listed Linux builds require x64.', choice: '' };
      if (/x86_64|amd64|x64/.test(s + ' ' + p)) return { label: 'Linux detected · x64 installer', choice: 'linux_run' };
      return { label: 'Linux detected. The listed Linux builds require x64.', choice: '' };
    }
    return { label: 'Choose a desktop version to get started.', choice: '' };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { detect };
  if (!root.document) return;
  const panel = document.getElementById('smart-download');
  if (!panel) return;
  const label = document.getElementById('detected-label');
  const select = document.getElementById('download-choice');
  const action = document.getElementById('selected-download');
  const versions = document.getElementById('other-versions');
  const result = detect(navigator.userAgent, navigator.userAgentData && navigator.userAgentData.platform || navigator.platform, navigator.userAgentData && navigator.userAgentData.mobile);
  label.textContent = result.label;
  select.value = result.choice;
  function update() {
    const source = document.querySelector('[data-download="' + select.value + '"]');
    if (source) { action.href = source.href; action.removeAttribute('aria-disabled'); action.innerHTML = 'Download ' + select.options[select.selectedIndex].textContent + ' <span aria-hidden="true">↓</span>'; }
    else { action.href = '#other-versions'; action.removeAttribute('aria-disabled'); action.innerHTML = 'Choose desktop versions <span aria-hidden="true">↓</span>'; }
  }
  action.addEventListener('click', () => { if (!select.value) versions.open = true; });
  select.addEventListener('change', update); update(); panel.hidden = false; versions.open = false;
})(typeof window === 'undefined' ? globalThis : window);
