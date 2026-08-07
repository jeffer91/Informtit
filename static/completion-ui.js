(() => {
  const script = document.createElement('script');
  script.src = '/completion-ui-v2.js?v=2.3';
  script.defer = true;
  script.onload = () => {
    const organization = document.createElement('script');
    organization.src = '/nuclei-organization.js?v=2.3';
    organization.defer = true;
    organization.onload = () => {
      const clarity = document.createElement('script');
      clarity.src = '/nuclei-clarity.js?v=2.3';
      clarity.defer = true;
      clarity.onload = () => {
        const workflow = document.createElement('script');
        workflow.src = '/workflow-ui.js?v=2.3';
        workflow.defer = true;
        workflow.onload = () => {
          const fixes = document.createElement('script');
          fixes.src = '/workflow-ui-fixes.js?v=2.3';
          fixes.defer = true;
          fixes.onload = () => {
            const campus = document.createElement('script');
            campus.src = '/nuclei-campus-ui.js?v=2.3';
            campus.defer = true;
            document.head.appendChild(campus);
          };
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
