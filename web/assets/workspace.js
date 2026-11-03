/* Keep all three workspaces in sync without interrupting a tutoring session. */
(() => {
  'use strict';
  const views = {tutor:'tutor-workspace', homework:'homework-view', learning:'learning-view', shop:'pet-store-view'};
  function show(name) {
    if (!Object.hasOwn(views, name)) return;
    for (const [key, id] of Object.entries(views)) {
      document.getElementById(id).hidden = key !== name;
      const tab = document.getElementById(key === 'shop' ? 'shop-tab' : `${key}-tab`);
      tab.classList.toggle('is-active', key === name);
      tab.setAttribute('aria-pressed', String(key === name));
    }
    const url = new URL(location.href);
    if (name === 'tutor') url.searchParams.delete('view');
    else url.searchParams.set('view', name);
    history.replaceState(null, '', url);
    window.dispatchEvent(new Event('resize'));
    window.dispatchEvent(new CustomEvent('mathguide:workspace', {detail: name}));
  }
  window.MathGuideWorkspace = {show};
  document.getElementById('shop-tab').onclick = () => {
    show('shop'); window.MathGuidePet?.openShop(); window.scrollTo(0, 0);
  };
  document.addEventListener('DOMContentLoaded', () => {
    if (new URLSearchParams(location.search).get('view') === 'shop') show('shop');
  });
})();
