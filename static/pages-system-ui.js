(() => {
  'use strict';
  if (!/(^|\.)github\.io$/i.test(location.hostname)) return;

  function clean(value){return String(value??'').trim();}
  function removeLegacy() {
    document.querySelectorAll('#firebase-sync-btn,#firebase-publish-btn,#firebase-pages-status,#pages-backend-only-note,#informtit-web-bridge,#open-devtools-btn').forEach(node=>node.remove());
    document.querySelectorAll('.top-actions button').forEach(button=>{
      if (/sincronizar firebase|publicar notas|consola/i.test(clean(button.textContent))) button.remove();
    });
  }
  function footer(text='Google Sheets') {
    const node=document.querySelector('.sidebar-footer span:last-child');
    if(node&&node.textContent!==text)node.textContent=text;
  }
  function sourceBadge(ok=true) {
    let node=document.getElementById('sheets-source-state');
    if(!node){node=document.createElement('div');node.id='sheets-source-state';node.style.cssText='margin:0 0 12px;padding:9px 11px;border:1px solid #cfe4d7;border-radius:10px;background:#f2fbf5;color:#285d3d;font-size:12px';const dashboard=document.getElementById('view-dashboard');dashboard?.insertBefore(node,dashboard.firstChild);}
    node.textContent=ok?'Google Sheets conectado · fuente principal':'Google Sheets no respondió · revise Apps Script';
    node.style.background=ok?'#f2fbf5':'#fff4f2';node.style.borderColor=ok?'#cfe4d7':'#efc7c1';node.style.color=ok?'#285d3d':'#8b342e';
  }
  async function ping(){try{const data=await window.InformtitSheets?.ping?.();const ok=Boolean(data?.ok);footer(ok?'Google Sheets conectado':'Google Sheets');sourceBadge(ok);}catch(_){footer('Google Sheets');sourceBadge(false);}}

  const previousDashboard=window.renderDashboard;
  if(typeof previousDashboard==='function')window.renderDashboard=function(...args){const result=previousDashboard.apply(this,args);removeLegacy();const cards=[...document.querySelectorAll('#dashboard-metrics .metric')];const db=cards.find(card=>/base de datos/i.test(card.querySelector('span')?.textContent||''));if(db){const value=db.querySelector('strong');if(value)value.textContent='Google Sheets';}setTimeout(()=>void ping(),0);return result;};

  const previousReport=window.renderReport;
  if(typeof previousReport==='function')window.renderReport=function(...args){const result=previousReport.apply(this,args);removeLegacy();const report=window.state?.activeReport;if(report?.report_type==='pvc'){const modality=document.getElementById('report-modality');if(modality)modality.textContent='PVC · Artículo Académico';}return result;};

  document.addEventListener('DOMContentLoaded',()=>{removeLegacy();footer();void ping();},{once:true});
  setTimeout(()=>{removeLegacy();footer();void ping();},0);
})();
