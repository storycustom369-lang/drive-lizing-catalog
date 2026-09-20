(function(){
  "use strict";
  var WORKER_URL = "https://odd-meadow-4208.litaufit.workers.dev";

  // --- Галерея: свайп/стрелки/точки ---
  document.querySelectorAll(".dl-gallery").forEach(function(g){
    var track = g.querySelector(".dl-gallery__track");
    var slides = g.querySelectorAll(".dl-gallery__slide");
    var dots = g.querySelectorAll(".dl-gallery__dot");
    var countEl = g.querySelector(".dl-gallery__count");
    var idx = 0;
    function render(){
      track.style.transform = "translateX(-" + (idx * 100) + "%)";
      dots.forEach(function(d, i){ d.classList.toggle("is-active", i === idx); });
      if (countEl) countEl.textContent = (idx + 1) + " / " + slides.length;
    }
    var prev = g.querySelector(".dl-gallery__nav.is-prev");
    var next = g.querySelector(".dl-gallery__nav.is-next");
    if (prev) prev.addEventListener("click", function(){ idx = (idx - 1 + slides.length) % slides.length; render(); });
    if (next) next.addEventListener("click", function(){ idx = (idx + 1) % slides.length; render(); });
    dots.forEach(function(d, i){ d.addEventListener("click", function(){ idx = i; render(); }); });
    // свайп на тач-устройствах
    var startX = null;
    track.addEventListener("touchstart", function(e){ startX = e.touches[0].clientX; }, {passive:true});
    track.addEventListener("touchend", function(e){
      if (startX === null) return;
      var dx = e.changedTouches[0].clientX - startX;
      if (Math.abs(dx) > 40) {
        idx = dx < 0 ? Math.min(idx + 1, slides.length - 1) : Math.max(idx - 1, 0);
        render();
      }
      startX = null;
    });
  });

  // --- Калькулятор платежа ---
  document.querySelectorAll(".dl-calc").forEach(function(calc){
    var data = JSON.parse(calc.dataset.carData);
    var pvButtons = calc.querySelectorAll(".dl-seg--pv button");
    var termButtons = calc.querySelectorAll(".dl-seg--term button");
    var outDay = calc.querySelector('[data-out="day"]');
    var outWeek = calc.querySelector('[data-out="week"]');
    var outMonth = calc.querySelector('[data-out="month"]');
    var outPvSum = calc.querySelector('[data-out="pv-sum"]');

    function fmt(n){ return n.toLocaleString("ru-RU") + " ₽"; }

    function currentPv(){
      var active = calc.querySelector(".dl-seg--pv button.is-active");
      return active ? active.dataset.pv : Object.keys(data)[0];
    }
    function currentTerm(){
      var active = calc.querySelector(".dl-seg--term button.is-active");
      var pv = currentPv();
      return active ? active.dataset.term : Object.keys(data[pv].terms)[0];
    }
    function update(){
      var pv = currentPv();
      var variant = data[pv];
      var term = currentTerm();
      var terms = variant.terms[term] ? term : Object.keys(variant.terms)[0];
      var t = variant.terms[terms];
      if (outDay) outDay.textContent = fmt(t.day);
      if (outWeek) outWeek.textContent = fmt(t.week);
      if (outMonth) outMonth.textContent = fmt(t.month);
      if (outPvSum) outPvSum.textContent = variant.pv > 0 ? "Первоначальный взнос: " + fmt(variant.pv) : "Без первоначального взноса";
    }
    pvButtons.forEach(function(b){
      b.addEventListener("click", function(){
        pvButtons.forEach(function(x){ x.classList.remove("is-active"); });
        b.classList.add("is-active");
        update();
      });
    });
    termButtons.forEach(function(b){
      b.addEventListener("click", function(){
        termButtons.forEach(function(x){ x.classList.remove("is-active"); });
        b.classList.add("is-active");
        update();
      });
    });
    var ctaBtn = calc.querySelector(".dl-btn--calc-cta");
    if (ctaBtn) ctaBtn.addEventListener("click", function(){
      var form = document.querySelector(".dl-lead-form");
      if (form) form.scrollIntoView({behavior:"smooth", block:"center"});
    });
    update();
  });

  // --- Форма заявки ---
  document.querySelectorAll(".dl-lead-form").forEach(function(form){
    form.addEventListener("submit", function(e){
      e.preventDefault();
      var btn = form.querySelector("button[type=submit]");
      var originalText = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Отправляем...";
      var payload = {
        name: form.name.value,
        phone: form.phone.value,
        car: form.dataset.car,
        art: form.dataset.art,
        source: "car-page:" + location.pathname
      };
      fetch(WORKER_URL, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      }).then(function(){
        form.innerHTML = '<div class="dl-success"><div class="dl-success__title">Заявка отправлена</div><div class="dl-success__text">Менеджер свяжется с вами в ближайшее время.</div></div>';
      }).catch(function(){
        btn.disabled = false;
        btn.textContent = originalText;
        alert("Не получилось отправить, попробуйте ещё раз или напишите нам напрямую.");
      });
    });
  });
})();
