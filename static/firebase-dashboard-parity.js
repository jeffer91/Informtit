(() => {
  'use strict';

  let officialCount = null;
  let loading = false;

  function periodMetric() {
    return [...document.querySelectorAll('#dashboard-metrics .metric')].find(metric =>
      metric.querySelector('span')?.textContent.trim() === 'Períodos'
    ) || null;
  }

  function applyCount() {
    if (officialCount === null) return;
    const metric = periodMetric();
    const value = metric?.querySelector('strong');
    if (value && value.textContent !== String(officialCount)) {
      value.textContent = String(officialCount);
    }
  }

  async function loadOfficialCount() {
    if (loading) return;
    loading = true;
    try {
      const data = await api('/api/firebase/periods');
      officialCount = Array.isArray(data?.periods) ? data.periods.length : null;
      applyCount();
    } catch (_) {
      // Sin conexión se conserva el valor local que ya muestra Informtit.
    } finally {
      loading = false;
    }
  }

  const observer = new MutationObserver(() => {
    applyCount();
  });

  const start = () => {
    const root = document.querySelector('#dashboard-metrics');
    if (root) observer.observe(root, { childList: true, subtree: true, characterData: true });
    loadOfficialCount();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
