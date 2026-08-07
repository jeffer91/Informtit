(() => {
  function enforceIndependentModules() {
    const nucleiRoot = document.querySelector('#tab-nuclei [data-minimal-nuclei]');
    nucleiRoot?.classList.remove('process-stack');
    document.querySelectorAll('[data-eligibility-panel], [data-complexive-eligibility-warning]').forEach(node => node.remove());
  }

  enforceIndependentModules();

  const completion = document.createElement('script');
  completion.src = '/completion-ui-v2.js?v=3.1';
  completion.defer = true;
  completion.onload = () => {
    enforceIndependentModules();
    new MutationObserver(records => {
      if (!records.some(record => record.addedNodes.length)) return;
      enforceIndependentModules();
    }).observe(document.body, { childList: true, subtree: true });
  };
  document.head.appendChild(completion);
})();
