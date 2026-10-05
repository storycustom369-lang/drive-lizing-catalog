// Общая форма заявки для index.html и catalog.html (раньше была задублирована
// в обоих файлах один в один — один и тот же баг, две копии). car-page.js не
// входит сюда: у него архитектурно отдельная реализация под карточку машины.

var LEAD_WEBHOOK_URL = 'https://odd-meadow-4208.litaufit.workers.dev';
var dbPromise = (window.claude && window.claude.use) ? window.claude.use('db') : Promise.resolve(null);

function buildLeadForm(container, opts){
  opts = opts || {};
  container.innerHTML = '';

  var nameField = document.createElement('div');
  nameField.className = 'dl-form-field';
  var nameInput = document.createElement('input');
  nameInput.className = 'dl-form-input';
  nameInput.type = 'text';
  nameInput.placeholder = 'Ваше имя';
  nameField.appendChild(nameInput);

  var phoneField = document.createElement('div');
  phoneField.className = 'dl-form-field';
  var phoneInput = document.createElement('input');
  phoneInput.className = 'dl-form-input';
  phoneInput.type = 'tel';
  phoneInput.inputMode = 'tel';
  phoneInput.placeholder = '+7 995 052-76-83';
  function formatPhone(digits){
    digits = digits.slice(0, 10);
    var out = '+7';
    if (digits.length > 0) out += ' ' + digits.slice(0, 3);
    if (digits.length >= 4) out += ' ' + digits.slice(3, 6);
    if (digits.length >= 7) out += '-' + digits.slice(6, 8);
    if (digits.length >= 9) out += '-' + digits.slice(8, 10);
    return out;
  }
  phoneInput.addEventListener('focus', function(){
    if (!phoneInput.value) phoneInput.value = '+7 ';
  });
  phoneInput.addEventListener('input', function(){
    var caret = phoneInput.selectionStart;
    var rawVal = phoneInput.value;
    var digitsBeforeCaret = rawVal.slice(0, caret).replace(/\D/g, '').length;
    var digits = rawVal.replace(/\D/g, '');
    if (digits.charAt(0) === '7' || digits.charAt(0) === '8') {
      digits = digits.slice(1);
      digitsBeforeCaret = Math.max(0, digitsBeforeCaret - 1);
    }
    var formatted = formatPhone(digits);
    phoneInput.value = formatted;
    var pos = formatted.length;
    if (digitsBeforeCaret > 0) {
      var seen = 0;
      for (var i = 2; i < formatted.length; i++) {
        if (/\d/.test(formatted[i])) {
          seen++;
          if (seen === digitsBeforeCaret) { pos = i + 1; break; }
        }
      }
    } else {
      pos = Math.min(3, formatted.length);
    }
    phoneInput.setSelectionRange(pos, pos);
  });
  phoneInput.addEventListener('keydown', function(e){
    if ((e.key === 'Backspace' || e.key === 'Delete') && phoneInput.selectionStart <= 3 && phoneInput.selectionEnd <= 3) {
      e.preventDefault();
    }
  });
  phoneField.appendChild(phoneInput);

  var commentField = document.createElement('div');
  commentField.className = 'dl-form-field';
  var commentInput = document.createElement('textarea');
  commentInput.className = 'dl-form-textarea';
  commentInput.placeholder = opts.commentPlaceholder || 'Комментарий (необязательно)';
  commentField.appendChild(commentInput);

  var submitBtn = document.createElement('button');
  submitBtn.className = 'dl-btn';
  submitBtn.type = 'button';
  submitBtn.textContent = opts.submitLabel || 'Отправить';

  var errorMsg = document.createElement('div');
  errorMsg.className = 'dl-form-hint';
  errorMsg.style.color = '#D14343';
  errorMsg.hidden = true;

  var consentField = document.createElement('label');
  consentField.className = 'dl-form-consent';
  var consentInput = document.createElement('input');
  consentInput.type = 'checkbox';
  var consentText = document.createElement('span');
  consentText.innerHTML = 'Согласен на <a href="privacy.html" target="_blank" rel="noopener">обработку персональных данных</a>';
  consentField.appendChild(consentInput);
  consentField.appendChild(consentText);
  consentInput.addEventListener('change', function(){
    consentField.classList.remove('is-error');
  });

  container.appendChild(nameField);
  container.appendChild(phoneField);
  container.appendChild(commentField);
  container.appendChild(consentField);
  container.appendChild(errorMsg);
  container.appendChild(submitBtn);

  submitBtn.addEventListener('click', function(){
    var name = nameInput.value.trim();
    var phone = phoneInput.value.trim();
    var phoneDigits = phone.replace(/\D/g, '');
    if (phoneDigits.length < 11) {
      errorMsg.textContent = 'Укажите полный номер телефона, чтобы мы могли связаться с вами.';
      errorMsg.hidden = false;
      phoneInput.focus();
      return;
    }
    if (!consentInput.checked) {
      errorMsg.textContent = 'Нужно согласие на обработку персональных данных.';
      errorMsg.hidden = false;
      consentField.classList.add('is-error');
      return;
    }
    errorMsg.hidden = true;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Отправляем…';

    var record = Object.assign({
      name: name,
      phone: phone,
      comment: commentInput.value.trim(),
      createdAt: new Date().toISOString()
    }, opts.extra || {});

    // Таймаут на отправку: без него зависшая сеть держит кнопку
    // "Отправляем…" бесконечно, и человек не понимает, отправилось или нет.
    var controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var timedOut = false;
    var timeoutId = controller ? setTimeout(function(){
      timedOut = true;
      controller.abort();
    }, 15000) : null;

    dbPromise.then(function(db){
      if (db) return db.collection(opts.collection).add(record);
      if (!LEAD_WEBHOOK_URL || LEAD_WEBHOOK_URL.indexOf('REPLACE-ME') !== -1) {
        return Promise.reject(new Error('no_webhook'));
      }
      return fetch(LEAD_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(record),
        signal: controller ? controller.signal : undefined
      }).then(function(r){
        if (!r.ok) return Promise.reject(new Error('webhook_failed'));
      });
    }).then(function(){
      if (timeoutId) clearTimeout(timeoutId);
      if (window.dlTrack) dlTrack('lead_submitted', {type: opts.collection || 'unknown'});
      if (opts.onSuccess) opts.onSuccess();
    }).catch(function(){
      if (timeoutId) clearTimeout(timeoutId);
      if (window.dlTrack) dlTrack('lead_failed', {type: opts.collection || 'unknown'});
      submitBtn.disabled = false;
      submitBtn.textContent = opts.submitLabel || 'Отправить';
      errorMsg.innerHTML = timedOut
        ? 'Сервер долго не отвечает. Попробуйте ещё раз или <a href="https://t.me/avtohere38" target="_blank" rel="noopener">напишите нам в Telegram</a>.'
        : 'Не получилось отправить. Попробуйте ещё раз или <a href="https://t.me/avtohere38" target="_blank" rel="noopener">напишите нам в Telegram</a>.';
      errorMsg.hidden = false;
    });
  });
}

function renderSuccess(container, title, text){
  container.innerHTML = '';
  var box = document.createElement('div');
  box.className = 'dl-success';
  box.innerHTML = '<svg viewBox="0 0 24 24" fill="none"><path d="M12 2L4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var successTitle = document.createElement('div');
  successTitle.className = 'dl-success__title';
  successTitle.textContent = title;
  var successText = document.createElement('div');
  successText.className = 'dl-success__text';
  successText.textContent = text;
  box.appendChild(successTitle);
  box.appendChild(successText);
  container.appendChild(box);
}
