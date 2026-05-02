(function(){
  function queueGridTask(fn){
    if('requestIdleCallback' in window){
      window.requestIdleCallback(fn,{timeout:250});
      return;
    }
    window.setTimeout(fn,0);
  }
  function hiddenPanel(el){return !!el.closest('[hidden]');}
  function externalFilter(table){
    const card=table.closest('.card');
    if(!card) return false;
    return Array.from(card.querySelectorAll('form')).some(function(form){
      return (form.method||'get').toLowerCase()==='get' && !!(form.compareDocumentPosition(table)&Node.DOCUMENT_POSITION_FOLLOWING);
    });
  }
  function parseCell(text){
    const clean=(text||'').trim().replace(/\s+/g,' ');
    const num=Number(clean.replace(/[\s,]/g,'').replace(/DA/gi,'').replace('%',''));
    if(!isNaN(num)&&/\d/.test(clean)) return num;
    const date=Date.parse(clean);
    if(!isNaN(date)&&/\d{4}-\d{2}-\d{2}/.test(clean)) return date;
    return clean.toLowerCase();
  }
  function setupGrid(table){
    if(table.dataset.enhanced||table.classList.contains('no-grid')) return;
    table.dataset.enhanced='1';
    const tbody=table.tBodies[0]; if(!tbody) return;
    const rows=Array.from(tbody.querySelectorAll('tr')).filter(function(row){return !row.querySelector('td[colspan]');});
    rows.forEach(function(row){row.dataset.searchText=row.dataset.searchText||(row.innerText||'').toLowerCase();});
    const wrap=document.createElement('div');
    wrap.className='table-shell';
    const showSearch=!externalFilter(table);
    const bar=document.createElement('div');
    bar.className='table-search';
    bar.innerHTML='<input class="form-control form-control-sm" placeholder="Rechercher...">';
    const existing=table.parentElement&&table.parentElement.classList.contains('table-responsive')?table.parentElement:null;
    const scroller=existing||document.createElement('div');
    scroller.classList.add('table-scroll','table-responsive');
    table.classList.add('table-sticky','table-row-hover');
    if(existing){
      existing.parentNode.insertBefore(wrap,existing);
      if(showSearch) wrap.appendChild(bar);
      wrap.appendChild(existing);
    }else{
      table.parentNode.insertBefore(wrap,table);
      if(showSearch) wrap.appendChild(bar);
      wrap.appendChild(scroller);
      scroller.appendChild(table);
    }
    const input=showSearch?bar.querySelector('input'):null;
    let currentRows=[...rows];
    function applyFilter(){
      const q=input?(input.value||'').toLowerCase():'';
      currentRows.forEach(function(row){row.style.display=!q||(row.dataset.searchText||'').includes(q)?'':'none';});
    }
    if(input) input.addEventListener('input',applyFilter);
    Array.from(table.querySelectorAll('thead th')).forEach(function(th,index){
      if(th.colSpan>1 || th.querySelector('a')) return;
      th.dataset.sortable='1';
      th.setAttribute('aria-sort','none');
      th.title='Trier';
      th.addEventListener('click',function(){
        const next=th.dataset.sortDir==='asc'?'desc':'asc';
        table.querySelectorAll('thead th[data-sortable="1"]').forEach(function(header){
          delete header.dataset.sortDir;
          header.setAttribute('aria-sort','none');
        });
        th.dataset.sortDir=next;
        th.setAttribute('aria-sort',next==='asc'?'ascending':'descending');
        currentRows.sort(function(a,b){
          const av=parseCell(a.cells[index]?.innerText||'');
          const bv=parseCell(b.cells[index]?.innerText||'');
          const cmp=av>bv?1:av<bv?-1:0;
          return next==='asc'?cmp:-cmp;
        });
        currentRows.forEach(function(row){tbody.appendChild(row);});
        applyFilter();
      });
    });
    applyFilter();
  }
  function initDataGrids(root){
    (root||document).querySelectorAll('table.js-datagrid').forEach(function(table){
      if(table.dataset.enhanced||table.classList.contains('no-grid')||hiddenPanel(table)) return;
      queueGridTask(function(){setupGrid(table);});
    });
  }
  document.addEventListener('fab:panel-open',function(event){
    if(event.detail&&event.detail.panel) initDataGrids(event.detail.panel);
  });
  queueGridTask(function(){initDataGrids(document);});

})();
