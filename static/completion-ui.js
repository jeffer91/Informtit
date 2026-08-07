(() => {
  const script = document.createElement('script');
  script.src = '/completion-ui-v2.js?v=2.0';
  script.defer = true;
  script.onload = () => {
    const organization = document.createElement('script');
    organization.src = '/nuclei-organization.js?v=2.0';
    organization.defer = true;
    organization.onload = () => {
      const clarity = document.createElement('script');
      clarity.src = '/nuclei-clarity.js?v=2.0';
      clarity.defer = true;
      clarity.onload = () => {
        const workflow = document.createElement('script');
        workflow.src = '/workflow-ui.js?v=2.0';
        workflow.defer = true;
        workflow.onload = () => {
          const fixes = document.createElement('script');
          fixes.src = '/workflow-ui-fixes.js?v=2.0';
          fixes.defer = true;
          document.head.appendChild(fixes);
        };
        document.head.appendChild(workflow);
      };
      document.head.appendChild(clarity);
    };
    document.head.appendChild(organization);
  };
  document.head.appendChild(script);
})();
