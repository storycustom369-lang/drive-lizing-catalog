(function(){
  var wrap=document.querySelector('.hp-rotating-line');
  if(!wrap)return;
  var items=wrap.querySelectorAll('.hp-rotating-text'), index=0;
  var reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
  // Reserve the space of all phrases through the CSS grid; no layout shifts.
  function advance(){
    if(document.hidden || document.querySelector('.hp-quiz[open]'))return;
    items[index].classList.remove('is-visible');
    index=(index+1)%items.length;
    items[index].classList.add('is-visible');
  }
  if(!reduced.matches)window.setInterval(advance,3400);
})();
