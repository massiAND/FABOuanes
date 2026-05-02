(function(){
  const token=window.fabApi?.csrfToken||document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')||'';
  if(token){
    document.querySelectorAll('form[method="post"],form[method="POST"]').forEach(function(form){
      if(form.querySelector('input[name="csrf_token"]')) return;
      const input=document.createElement('input');
      input.type='hidden';
      input.name='csrf_token';
      input.value=token;
      form.appendChild(input);
    });
    window.fabCsrfToken=token;
  }

  document.addEventListener('submit',function(event){
    const form=event.target;
    if(!form || form.dataset.noSpinner) return;
    if((form.method||'').toLowerCase()==='get') return;
    const button=form.querySelector('button[type="submit"],button:not([type])');
    if(!button || button.dataset.spinning) return;
    button.dataset.spinning='1';
    button.disabled=true;
    const original=button.innerHTML;
    button.innerHTML='<span class="spinner-border spinner-border-sm me-1"></span>En cours...';
    setTimeout(function(){
      button.disabled=false;
      button.innerHTML=original;
      delete button.dataset.spinning;
    },8000);
  });

  const today=(new Date()).toISOString().slice(0,10);
  document.querySelectorAll('input[type="date"]').forEach(function(input){
    if(input.value || input.dataset.noAutoDate==='1') return;
    const form=input.closest('form');
    if(form && (form.method||'get').toLowerCase()==='get') return;
    input.value=today;
  });
})();
