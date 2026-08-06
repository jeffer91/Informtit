(() => {
  const script = document.createElement('script');
  script.src = '/completion-ui-v2.js?v=1.7';
  script.defer = true;
  script.onload = () => {
    const organization = document.createElement('script');
    organization.src = '/nuclei-organization.js?v=1.7';
    organization.defer = true;
    document.head.appendChild(organization);
  };
  document.head.appendChild(script);
})();
