(function(){
  'use strict';
  var questions = [
    {title:'Какой автомобиль рассматриваете?', options:['Новый автомобиль','С пробегом','Пока выбираю']},
    {title:'Для чего нужен автомобиль?', options:['Для личных поездок','Для работы в такси','Для бизнеса']},
    {title:'Какой платёж в неделю вам удобен?', options:['10–15 тыс. ₽','15–20 тыс. ₽','20–25 тыс. ₽','От 25 тыс. ₽','Нужна помощь с расчётом']},
    {title:'Какой первоначальный взнос планируете?', options:['Без взноса · 0%','10%','20%','30%','Хочу сравнить варианты']},
    {title:'За какой срок хотите выкупить автомобиль?', options:['12 месяцев','24 месяца','36 месяцев','Помогите выбрать срок']}
  ];
  var answers = [], step = 0, model = '', contact = {}, opener, oldOverflow;
  var dialog = document.createElement('dialog');
  dialog.className = 'hp-quiz';
  dialog.setAttribute('aria-label','Подбор автомобиля и расчёт платежа');
  document.body.appendChild(dialog);
  function element(tag, cls, text){
    var el = document.createElement(tag); if(cls) el.className=cls; if(text) el.textContent=text; return el;
  }
  function saveContacts(){
    var wrap=dialog.querySelector('.hp-quiz-form'); if(!wrap || !wrap.querySelector('input[type=text]')) return;
    contact.name=wrap.querySelector('input[type=text]').value;
    contact.phone=wrap.querySelector('input[type=tel]').value;
    contact.consent=wrap.querySelector('input[type=checkbox]').checked;
  }
  function close(){ saveContacts(); dialog.close(); document.body.style.overflow=oldOverflow || ''; if(opener) opener.focus(); }
  dialog.addEventListener('cancel',function(e){e.preventDefault();close();});
  dialog.addEventListener('click',function(e){if(e.target===dialog){var r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom) close();}});
  function render(){
    dialog.replaceChildren();
    var head=element('div','hp-quiz-head');
    var x=element('button','hp-quiz-close','×');x.type='button';x.setAttribute('aria-label','Закрыть квиз');x.addEventListener('click',close);head.appendChild(x);dialog.appendChild(head);
    var progress=element('div','hp-quiz-progress');progress.setAttribute('role','progressbar');progress.setAttribute('aria-valuemin','1');progress.setAttribute('aria-valuemax','6');progress.setAttribute('aria-valuenow',String(step+1));progress.setAttribute('aria-label','Шаг подбора');var bar=element('span');bar.style.width=((step+1)/6*100)+'%';progress.appendChild(bar);dialog.appendChild(progress);
    dialog.appendChild(element('p','hp-quiz-step','Шаг '+(step+1)+' из 6'));
    var title=element('h2','hp-quiz-title',step<5?questions[step].title:'Куда отправить подбор и расчёт?');title.tabIndex=-1;dialog.appendChild(title);
    if(step<5){
      var options=element('div','hp-quiz-options');
      questions[step].options.forEach(function(label){
        var btn=element('button','hp-quiz-option'+(answers[step]===label?' is-selected':''),label);btn.type='button';btn.setAttribute('aria-pressed',String(answers[step]===label));
        btn.addEventListener('click',function(){answers[step]=label;options.querySelectorAll('button').forEach(function(b){var active=b===btn;b.classList.toggle('is-selected',active);b.setAttribute('aria-pressed',String(active));});next.disabled=false;});options.appendChild(btn);
      });dialog.appendChild(options);
      if(step===0){var label=element('label','hp-quiz-model-label','Марка и модель, если уже выбрали');var input=element('input','hp-quiz-model');input.placeholder='Например, Chery Tiggo 4';input.value=model;input.maxLength=120;input.addEventListener('input',function(){model=input.value;});label.appendChild(input);dialog.appendChild(label);}
      var nav=element('div','hp-quiz-nav');var back=element('button','hp-quiz-back','Назад');back.type='button';back.disabled=step===0;back.addEventListener('click',function(){step--;render();});nav.appendChild(back);
      var next=element('button','hp-quiz-next','Далее →');next.type='button';next.disabled=!answers[step];next.addEventListener('click',function(){if(!answers[step])return;step++;render();});nav.appendChild(next);dialog.appendChild(nav);
    }else{
      dialog.appendChild(element('p','hp-quiz-description','Менеджер подберёт варианты и рассчитает условия по вашим ответам.'));
      var summary=element('details','hp-quiz-summary');summary.appendChild(element('summary','','Ваши ответы'));var list=element('dl');
      questions.forEach(function(q,i){list.appendChild(element('dt','',q.title));list.appendChild(element('dd','',answers[i]));});if(model){list.appendChild(element('dt','','Автомобиль'));list.appendChild(element('dd','',model));}summary.appendChild(list);dialog.appendChild(summary);
      var form=element('div','hp-quiz-form');dialog.appendChild(form);
      if(typeof window.buildLeadForm!=='function'){form.appendChild(element('p','','Форма временно недоступна. Позвоните +7 995 052-76-83.'));return;}
      var comment='Подбор с главной страницы\n'+questions.map(function(q,i){return q.title+' '+answers[i];}).join('\n')+(model?'\nАвтомобиль: '+model:'');
      window.buildLeadForm(form,{collection:'requests',submitLabel:'Получить подбор и расчёт',extra:{type:'custom_request'},onSuccess:function(){contact={};window.renderSuccess(form,'Заявка отправлена','Менеджер свяжется с вами и обсудит варианты автомобилей и условия выкупа.');back.hidden=true;}});
      var name=form.querySelector('input[type=text]'),phone=form.querySelector('input[type=tel]'),consent=form.querySelector('input[type=checkbox]');
      name.setAttribute('aria-label','Ваше имя');name.autocomplete='name';phone.setAttribute('aria-label','Телефон');phone.autocomplete='tel';name.value=contact.name||'';phone.value=contact.phone||'';consent.checked=!!contact.consent;
      var commentInput=form.querySelector('textarea');commentInput.value=comment;commentInput.readOnly=true;commentInput.parentElement.hidden=true;
      var back=element('button','hp-quiz-back','← Изменить ответы');back.type='button';back.addEventListener('click',function(){saveContacts();step=4;render();});dialog.appendChild(back);
    }
    title.focus();
  }
  document.querySelectorAll('.hp-actions a[href="#hp-cars"], .hp-card-actions .hp-btn-white, [data-payment-quiz]').forEach(function(btn){
    btn.addEventListener('click',function(e){e.preventDefault();opener=btn;var car=btn.closest('.hp-car');if(car){model=car.querySelector('h3').textContent;answers[0]='С пробегом';}step=0;oldOverflow=document.body.style.overflow;render();dialog.showModal();document.body.style.overflow='hidden';dialog.querySelector('h2').focus();if(window.dlTrack)window.dlTrack('open_payment_quiz');});
  });
})();
