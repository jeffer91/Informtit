(() => {
  const script = document.createElement('script');
  script.src = '/completion-ui-v2.js?v=1.8';
  script.defer = true;
  script.onload = () => {
    const organization = document.createElement('script');
    organization.src = '/nuclei-organization.js?v=1.8';
    organization.defer = true;
    organization.onload = () => {
      const clarity = document.createElement('script');
      clarity.src = '/nuclei-clarity.js?v=1.8';
      clarity.defer = true;
      document.head.appendChild(clarity);
    };
    document.head.appendChild(organization);
  };
  document.head.appendChild(script);
})();
