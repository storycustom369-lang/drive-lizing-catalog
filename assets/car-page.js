(function(){
  "use strict";
  var WORKER_URL = "https://odd-meadow-4208.litaufit.workers.dev";

  // --- Модалка бронирования (тот же функционал, что в каталоге) ---
  var backdrop = document.getElementById("dlModalBackdrop");
  var modal = document.getElementById("dlModal");

  function closeBookingModal(){
    if (backdrop) backdrop.hidden = true;
    document.body.style.overflow = "";
  }
  if (backdrop) {
    backdrop.addEventListener("click", function(e){ if (e.target === backdrop) closeBookingModal(); });
  }
  document.addEventListener("keydown", function(e){ if (e.key === "Escape") closeBookingModal(); });

  function formatPhone(digits){
    digits = digits.slice(0, 10);
    var out = "+7";
    if (digits.length > 0) out += " " + digits.slice(0, 3);
    if (digits.length >= 4) out += " " + digits.slice(3, 6);
    if (digits.length >= 7) out += "-" + digits.slice(6, 8);
    if (digits.length >= 9) out += "-" + digits.slice(8, 10);
    return out;
  }

  function openBookingModal(opts){
    if (!modal || !backdrop) return;
    modal.innerHTML = "";

    var head = document.createElement("div");
    head.className = "dl-modal__head";
    var titleWrap = document.createElement("div");
    var titleEl = document.createElement("div");
    titleEl.className = "dl-modal__title";
    titleEl.textContent = "Бронирование: " + opts.carTitle;
    var sub = document.createElement("div");
    sub.style.cssText = "font-size:12px;color:var(--muted);margin-top:4px;";
    sub.textContent = "Артикул " + opts.art;
    titleWrap.appendChild(titleEl);
    titleWrap.appendChild(sub);
    var closeBtn = document.createElement("button");
    closeBtn.className = "dl-modal__close";
    closeBtn.setAttribute("aria-label", "Закрыть");
    closeBtn.innerHTML = "&times;";
    closeBtn.addEventListener("click", closeBookingModal);
    head.appendChild(titleWrap);
    head.appendChild(closeBtn);
    modal.appendChild(head);

    var nameField = document.createElement("div");
    nameField.className = "dl-form-field";
    var nameInput = document.createElement("input");
    nameInput.className = "dl-form-input";
    nameInput.type = "text";
    nameInput.placeholder = "Ваше имя";
    nameField.appendChild(nameInput);

    var phoneField = document.createElement("div");
    phoneField.className = "dl-form-field";
    var phoneInput = document.createElement("input");
    phoneInput.className = "dl-form-input";
    phoneInput.type = "tel";
    phoneInput.inputMode = "tel";
    phoneInput.placeholder = "+7 995 052-76-83";
    phoneInput.addEventListener("focus", function(){ if (!phoneInput.value) phoneInput.value = "+7 "; });
    phoneInput.addEventListener("input", function(){
      var digits = phoneInput.value.replace(/\D/g, "");
      if (digits.charAt(0) === "7" || digits.charAt(0) === "8") digits = digits.slice(1);
      phoneInput.value = formatPhone(digits);
    });
    phoneInput.addEventListener("keydown", function(e){
      if ((e.key === "Backspace" || e.key === "Delete") && phoneInput.selectionStart <= 3 && phoneInput.selectionEnd <= 3) e.preventDefault();
    });
    phoneField.appendChild(phoneInput);

    var commentField = document.createElement("div");
    commentField.className = "dl-form-field";
    var commentInput = document.createElement("textarea");
    commentInput.className = "dl-form-textarea";
    commentInput.placeholder = "Удобное время для звонка, вопросы по авто (необязательно)";
    commentField.appendChild(commentInput);

    var consentField = document.createElement("label");
    consentField.className = "dl-form-consent";
    var consentInput = document.createElement("input");
    consentInput.type = "checkbox";
    var consentText = document.createElement("span");
    consentText.innerHTML = 'Согласен на <a href="../../privacy.html" target="_blank" rel="noopener">обработку персональных данных</a>';
    consentField.appendChild(consentInput);
    consentField.appendChild(consentText);
    consentInput.addEventListener("change", function(){ consentField.classList.remove("is-error"); });

    var errorMsg = document.createElement("div");
    errorMsg.className = "dl-form-hint";
    errorMsg.style.color = "#D14343";
    errorMsg.hidden = true;

    var submitBtn = document.createElement("button");
    submitBtn.className = "dl-btn";
    submitBtn.type = "button";
    submitBtn.textContent = "Забронировать автомобиль";

    modal.appendChild(nameField);
    modal.appendChild(phoneField);
    modal.appendChild(commentField);
    modal.appendChild(consentField);
    modal.appendChild(errorMsg);
    modal.appendChild(submitBtn);

    submitBtn.addEventListener("click", function(){
      var name = nameInput.value.trim();
      var phone = phoneInput.value.trim();
      var phoneDigits = phone.replace(/\D/g, "");
      if (phoneDigits.length < 11) {
        errorMsg.textContent = "Укажите полный номер телефона, чтобы мы могли связаться с вами.";
        errorMsg.hidden = false;
        phoneInput.focus();
        return;
      }
      if (!consentInput.checked) {
        errorMsg.textContent = "Нужно согласие на обработку персональных данных.";
        errorMsg.hidden = false;
        consentField.classList.add("is-error");
        return;
      }
      errorMsg.hidden = true;
      submitBtn.disabled = true;
      submitBtn.textContent = "Отправляем…";

      var payload = {
        type: "booking",
        name: name,
        phone: phone,
        comment: commentInput.value.trim(),
        createdAt: new Date().toISOString(),
        carArt: opts.art,
        carTitle: opts.carTitle,
        pv: opts.pv,
        term: opts.term,
        weekPayment: opts.weekPayment,
        monthPayment: opts.monthPayment,
        source: "car-page:" + location.pathname
      };
      fetch(WORKER_URL, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      }).then(function(r){
        if (!r.ok) return Promise.reject(new Error("webhook_failed"));
        modal.innerHTML = "";
        modal.appendChild(head);
        var box = document.createElement("div");
        box.className = "dl-success";
        box.innerHTML = '<svg viewBox="0 0 24 24" fill="none"><path d="M12 2L4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
          '<div class="dl-success__title">Заявка принята</div>' +
          '<div class="dl-success__text">Мы получили бронь на ' + opts.carTitle + '. Менеджер свяжется с вами в ближайшее время, чтобы подтвердить условия.</div>';
        modal.appendChild(box);
      }).catch(function(){
        submitBtn.disabled = false;
        submitBtn.textContent = "Забронировать автомобиль";
        errorMsg.textContent = "Не получилось отправить. Попробуйте ещё раз или напишите нам в Telegram.";
        errorMsg.hidden = false;
      });
    });

    backdrop.hidden = false;
    document.body.style.overflow = "hidden";
  }

  // --- Лайтбокс на весь экран ---
  var lightbox = document.getElementById("dlLightbox");
  var lightboxImg = document.getElementById("dlLightboxImg");
  var lightboxCount = document.getElementById("dlLightboxCount");
  var lightboxClose = document.getElementById("dlLightboxClose");
  var lightboxPrev = document.getElementById("dlLightboxPrev");
  var lightboxNext = document.getElementById("dlLightboxNext");
  var lbSrcs = [];
  var lbIdx = 0;
  var lbOnChange = null;
  function lbRender(){
    lightboxImg.src = lbSrcs[lbIdx];
    if (lightboxCount) lightboxCount.textContent = (lbIdx + 1) + " / " + lbSrcs.length;
  }
  function openLightbox(srcs, startIdx, onChange){
    if (!lightbox) return;
    lbSrcs = srcs; lbIdx = startIdx; lbOnChange = onChange || null;
    lbRender();
    lightbox.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeLightbox(){
    if (!lightbox) return;
    lightbox.hidden = true;
    document.body.style.overflow = "";
  }
  if (lightboxClose) lightboxClose.addEventListener("click", closeLightbox);
  if (lightbox) lightbox.addEventListener("click", function(e){ if (e.target === lightbox) closeLightbox(); });
  if (lightboxPrev) lightboxPrev.addEventListener("click", function(){ lbIdx = (lbIdx - 1 + lbSrcs.length) % lbSrcs.length; lbRender(); if (lbOnChange) lbOnChange(lbIdx); });
  if (lightboxNext) lightboxNext.addEventListener("click", function(){ lbIdx = (lbIdx + 1) % lbSrcs.length; lbRender(); if (lbOnChange) lbOnChange(lbIdx); });
  document.addEventListener("keydown", function(e){
    if (lightbox && !lightbox.hidden) {
      if (e.key === "Escape") closeLightbox();
      if (e.key === "ArrowLeft" && lightboxPrev) lightboxPrev.click();
      if (e.key === "ArrowRight" && lightboxNext) lightboxNext.click();
    }
  });

  // --- Галерея: свайп/стрелки/точки/миниатюры ---
  document.querySelectorAll(".dl-gallery").forEach(function(g){
    var track = g.querySelector(".dl-gallery__track");
    var slides = g.querySelectorAll(".dl-gallery__slide");
    var dots = g.querySelectorAll(".dl-gallery__dot");
    var countEl = g.querySelector(".dl-gallery__count");
    var thumbsWrap = g.parentElement ? g.parentElement.parentElement.querySelector(".dl-thumbs") : null;
    var thumbs = thumbsWrap ? thumbsWrap.querySelectorAll(".dl-thumb") : [];
    var idx = 0;
    function render(){
      track.style.transform = "translateX(-" + (idx * 100) + "%)";
      dots.forEach(function(d, i){ d.classList.toggle("is-active", i === idx); });
      thumbs.forEach(function(t, i){ t.classList.toggle("is-active", i === idx); });
      if (countEl) countEl.textContent = (idx + 1) + " / " + slides.length;
    }
    var prev = g.querySelector(".dl-gallery__nav.is-prev");
    var next = g.querySelector(".dl-gallery__nav.is-next");
    if (prev) prev.addEventListener("click", function(){ idx = (idx - 1 + slides.length) % slides.length; render(); });
    if (next) next.addEventListener("click", function(){ idx = (idx + 1) % slides.length; render(); });
    dots.forEach(function(d, i){ d.addEventListener("click", function(){ idx = i; render(); }); });
    thumbs.forEach(function(t, i){ t.addEventListener("click", function(){ idx = i; render(); }); });
    var expandBtn = g.querySelector(".dl-gallery__expand");
    if (expandBtn) expandBtn.addEventListener("click", function(){
      var srcs = Array.prototype.map.call(slides, function(s){ var img = s.querySelector("img"); return img ? img.src : ""; });
      openLightbox(srcs, idx, function(newIdx){ idx = newIdx; render(); });
    });
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
    var outDay = calc.querySelector('[data-out="day"]');
    var outWeek = calc.querySelector('[data-out="week"]');
    var outMonth = calc.querySelector('[data-out="month"]');
    var outPvSum = calc.querySelector('[data-out="pv-sum"]');

    calc.querySelectorAll(".dl-hint__btn").forEach(function(btn){
      btn.addEventListener("click", function(e){
        e.stopPropagation();
        var cell = btn.closest(".dl-result__cell");
        var wasOpen = cell.classList.contains("is-hint-open");
        calc.querySelectorAll(".dl-result__cell.is-hint-open").forEach(function(c){ c.classList.remove("is-hint-open"); });
        if (!wasOpen) cell.classList.add("is-hint-open");
      });
    });
    document.addEventListener("click", function(){
      calc.querySelectorAll(".dl-result__cell.is-hint-open").forEach(function(c){ c.classList.remove("is-hint-open"); });
    });

    function fmt(n){ return n.toLocaleString("ru-RU") + " ₽"; }

    function currentPv(){
      var active = calc.querySelector(".dl-slider--pv .dl-slider__label.is-active");
      return active ? active.dataset.pv : Object.keys(data)[0];
    }
    function currentTerm(){
      var active = calc.querySelector(".dl-slider--term .dl-slider__label.is-active");
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

    // Слайдер с фиксированными точками (ПВ / срок) — тянется, но встаёт только на конкретные значения
    function setupSlider(root){
      var rail = root.querySelector(".dl-slider__rail");
      var fill = root.querySelector(".dl-slider__fill");
      var thumb = root.querySelector(".dl-slider__thumb");
      var labels = Array.prototype.slice.call(root.querySelectorAll(".dl-slider__label"));
      var n = labels.length;

      function pctForIndex(i){ return n > 1 ? (i / (n - 1)) * 100 : 0; }
      function paint(i){
        var pct = pctForIndex(i);
        fill.style.width = pct + "%";
        thumb.style.left = pct + "%";
        labels.forEach(function(l, li){ l.classList.toggle("is-active", li === i); });
      }
      function activeIndex(){
        var i = n - 1;
        labels.forEach(function(l, li){ if (l.classList.contains("is-active")) i = li; });
        return i;
      }
      function setIndex(i){
        i = Math.max(0, Math.min(n - 1, i));
        var changed = i !== activeIndex();
        paint(i);
        if (changed) update();
      }
      function indexFromClientX(clientX){
        var rect = rail.getBoundingClientRect();
        var pct = rect.width ? (clientX - rect.left) / rect.width * 100 : 0;
        pct = Math.max(0, Math.min(100, pct));
        return Math.round(pct / 100 * (n - 1));
      }

      labels.forEach(function(l, i){
        l.addEventListener("click", function(){ setIndex(i); });
      });

      var dragging = false;
      function onMove(e){
        if (!dragging) return;
        var clientX = e.touches ? e.touches[0].clientX : e.clientX;
        paint(indexFromClientX(clientX));
        e.preventDefault();
      }
      function onEnd(e){
        if (!dragging) return;
        dragging = false;
        root.classList.remove("is-dragging");
        var clientX = e.changedTouches ? e.changedTouches[0].clientX : e.clientX;
        setIndex(indexFromClientX(clientX));
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onEnd);
        document.removeEventListener("touchmove", onMove);
        document.removeEventListener("touchend", onEnd);
      }
      function onStart(e){
        dragging = true;
        root.classList.add("is-dragging");
        onMove(e);
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onEnd);
        document.addEventListener("touchmove", onMove, {passive:false});
        document.addEventListener("touchend", onEnd);
        e.preventDefault();
      }
      thumb.addEventListener("mousedown", onStart);
      thumb.addEventListener("touchstart", onStart, {passive:false});
      rail.addEventListener("click", function(e){
        if (e.target === thumb) return;
        setIndex(indexFromClientX(e.clientX));
      });
    }
    calc.querySelectorAll(".dl-slider").forEach(setupSlider);
    var ctaBtn = calc.querySelector(".dl-btn--calc-cta");
    if (ctaBtn) ctaBtn.addEventListener("click", function(){
      var pv = currentPv();
      var variant = data[pv];
      var term = currentTerm();
      var t = variant.terms[term] || variant.terms[Object.keys(variant.terms)[0]];
      openBookingModal({
        art: calc.dataset.art,
        carTitle: calc.dataset.car,
        pv: variant.label,
        term: term + " мес",
        weekPayment: t ? t.week : null,
        monthPayment: t ? t.month : null
      });
    });
    update();
  });

  document.querySelectorAll(".dl-calc-unavailable .dl-btn--calc-cta").forEach(function(btn){
    btn.addEventListener("click", function(){
      openBookingModal({ art: btn.dataset.art, carTitle: btn.dataset.car, pv: null, term: null, weekPayment: null, monthPayment: null });
    });
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

  // --- Карусель "Другие автомобили" ---
  document.querySelectorAll(".dl-related2__track").forEach(function(track){
    var section = track.closest(".dl-related2");
    if (!section) return;
    section.querySelectorAll(".dl-related2__nav-btn").forEach(function(btn){
      btn.addEventListener("click", function(){
        var card = track.querySelector(".dl-related2__card");
        var step = card ? card.getBoundingClientRect().width + 18 : 280;
        track.scrollBy({ left: step * Number(btn.dataset.dir), behavior: "smooth" });
      });
    });
  });

  // --- Избранное на карточках (визуально, без сохранения) ---
  document.querySelectorAll(".dl-related2__heart").forEach(function(heart){
    function toggle(e){
      e.preventDefault();
      e.stopPropagation();
      heart.classList.toggle("is-active");
    }
    heart.addEventListener("click", toggle);
    heart.addEventListener("keydown", function(e){
      if (e.key === "Enter" || e.key === " ") toggle(e);
    });
  });
})();
