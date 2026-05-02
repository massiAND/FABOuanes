(function(){
  const themeColors={
    light:'#1a2235',
    dark:'#0d1117',
    slate:'#475569',
    sand:'#7c5a34'
  };
  const fonts={
    google:true,
    microsoft:true,
    apple:true,
    ubuntu:true,
    arial:true,
    calibri:true,
    system:true
  };
  function markSelected(selector,key,value){
    document.querySelectorAll(selector).forEach(function(button){
      const selected=button.dataset[key]===value;
      button.classList.toggle('active',selected);
      button.setAttribute('aria-pressed',selected?'true':'false');
    });
  }
  function applyTheme(theme,opts){
    const name=themeColors[theme]?theme:'light';
    if(opts&&opts.animate) document.documentElement.classList.add('theme-changing');
    document.documentElement.setAttribute('data-theme',name);
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content',themeColors[name]);
    markSelected('.js-theme','theme',name);
    window.clearTimeout(window.fabThemeTimer);
    if(opts&&opts.animate){
      window.fabThemeTimer=window.setTimeout(function(){
        document.documentElement.classList.remove('theme-changing');
      },280);
    }
  }
  function applyFont(font){
    const name=fonts[font]?font:'system';
    document.documentElement.setAttribute('data-font',name);
    markSelected('.js-font','font',name);
  }
  try{
    const params=new URLSearchParams(window.location.search);
    if(params.get('mobile_shell')==='1') localStorage.setItem('fab_mobile_shell','1');
    if(params.get('mobile_shell')==='0') localStorage.removeItem('fab_mobile_shell');
  }catch(e){}
  applyTheme(localStorage.getItem('fab_theme')||'light');
  applyFont(localStorage.getItem('fab_font')||'system');
  document.querySelectorAll('.js-theme').forEach(function(button){
    button.addEventListener('click',function(){
      const theme=this.dataset.theme;
      applyTheme(theme,{animate:true});
      localStorage.setItem('fab_theme',theme);
    });
  });
  document.querySelectorAll('.js-font').forEach(function(button){
    button.addEventListener('click',function(){
      const font=this.dataset.font;
      applyFont(font);
      localStorage.setItem('fab_font',font);
    });
  });
})();
