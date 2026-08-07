(() => {
  const script = document.createElement('script');
  script.src = '/completion-ui-v2.js?v=1.9';
  script.defer = true;
  script.onload = () => {
    const organization = document.createElement('script');
    organization.src = '/nuclei-organization.js?v=1.9';
    organization.defer = true;
    organization.onload = () => {
      const clarity = document.createElement('script');
      clarity.src = '/nuclei-clarity.js?v=1.9';
      clarity.defer = true;
      clarity.onload = () => {
        const workflow = document.createElement('script');
        workflow.src = '/workflow-ui.js?v=1.9';
        workflow.defer = true;
        document.head.appendChild(workflow);
      };
      document.head.appendChild(clarity);
    };
    document.head.appendChild(organization);
  };
  document.head.appendChild(script);
})();
