(() => {
  const completion = document.createElement('script');
  completion.src = '/completion-ui-v2.js?v=2.5';
  completion.defer = true;
  completion.onload = () => {
    const workflow = document.createElement('script');
    workflow.src = '/workflow-ui.js?v=2.5';
    workflow.defer = true;
    document.head.appendChild(workflow);
  };
  document.head.appendChild(completion);
})();
