#!/usr/bin/env python3
"""
Генератор отдельных страниц под каждую машину из живого каталога (CARS в catalog.html).
Точка А -> Б: превращает JS-модалки внутри одной страницы в реальные краулящиеся URL.

Запуск: python3 generate_cars.py
Результат: cars/<slug>/index.html на каждую машину + обновлённый sitemap.xml (не трогает старый sitemap.xml файл напрямую, пишет sitemap_generated.xml для ручной проверки перед заменой).
"""
import re, json, os, html, hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG_HTML = os.path.join(BASE_DIR, "catalog.html")
INDEX_HTML = os.path.join(BASE_DIR, "index.html")
CARS_DIR = os.path.join(BASE_DIR, "cars")
SITE_URL = "https://driveleasing38.ru"
WORKER_URL = "https://odd-meadow-4208.litaufit.workers.dev"

# Аналитика (GA4 + Яндекс.Метрика) — раньше стояла только на index.html и catalog.html,
# страницы машин/марок/кузовов/статей (то, что реально приводит SEO-трафик) не считались
# вообще. dlTrack — общий хелпер для событий (открытие модалки, успешная/неудачная заявка),
# чтобы car-page.js мог слать одно и то же событие сразу в GA4 и в Метрику.
ANALYTICS_HEAD = '''<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-9CF3B6E9EP"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-9CF3B6E9EP');
</script>
<!-- Yandex.Metrika counter -->
<script type="text/javascript">
    (function(m,e,t,r,i,k,a){
        m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=112703003', 'ym');

    ym(112703003, 'init', {ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/112703003" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->
<script>
  window.dlTrack = function(name, params){
    try { if (typeof gtag === 'function') gtag('event', name, params || {}); } catch(e){}
    try { if (typeof ym === 'function') ym(112703003, 'reachGoal', name); } catch(e){}
  };
</script>'''

TRANSLIT = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'i',
    'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
    'х':'h','ц':'c','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
    ' ':'-','_':'-',
}

def slugify(s):
    s = s.strip().lower()
    out = []
    for ch in s:
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isalnum():
            out.append(ch)
        elif ch in ('-','.'):
            out.append('-')
    slug = re.sub(r'-+', '-', ''.join(out)).strip('-')
    return slug

def min_week_price(car):
    """Минимальный платёж в неделю: максимальный ПВ (ниже коэффициент) + максимальный срок (меньше платёж)."""
    variants = car.get('variants')
    if not variants:
        return None
    max_pv = sorted(variants.keys(), key=int)[-1]
    max_term = sorted(variants[max_pv]['terms'].keys(), key=int)[-1]
    return variants[max_pv]['terms'][max_term]['week']

def load_cars():
    text = open(CATALOG_HTML, encoding='utf-8').read()
    m = re.search(r'var CARS = (\[.*?\]);', text, re.S)
    return json.loads(m.group(1))

def write_slugs_to_catalog(cars, slugs_by_art):
    """Прописывает car.slug в CARS внутри catalog.html, чтобы карточки каталога
    могли вести на cars/<slug>/ (единственный источник правды для слага - slugify() выше)."""
    text = open(CATALOG_HTML, encoding='utf-8').read()
    for c in cars:
        c['slug'] = slugs_by_art[c['art']]
    new_blob = json.dumps(cars, ensure_ascii=False)
    new_text, n = re.subn(r'var CARS = \[.*?\];', 'var CARS = ' + new_blob + ';', text, count=1, flags=re.S)
    if n != 1:
        raise RuntimeError("Не нашёл var CARS = [...]; в catalog.html, слаги не записаны")
    if new_text != text:
        open(CATALOG_HTML, 'w', encoding='utf-8').write(new_text)
        print("catalog.html: обновлены слаги для", len(cars), "машин")

def write_catalog_grid(cars, slugs_by_art):
    """Пишет статический список карточек в <div id="dlGrid"></div> catalog.html,
    чтобы поисковые боты видели реальный контент и ссылки на карточки машин
    в исходном HTML, а не только после выполнения JS."""
    text = open(CATALOG_HTML, encoding='utf-8').read()
    grid_html = render_catalog_grid(cars, slugs_by_art)
    new_text, n = re.subn(
        r'<div class="dl-grid" id="dlGrid">.*?</div>\s*(?=<div class="dl-empty")',
        f'<div class="dl-grid" id="dlGrid">{grid_html}</div>\n  ',
        text, count=1, flags=re.S,
    )
    if n != 1:
        raise RuntimeError('Не нашёл <div class="dl-grid" id="dlGrid">...</div> в catalog.html')
    if new_text != text:
        open(CATALOG_HTML, 'w', encoding='utf-8').write(new_text)
        print("catalog.html: пререндерен статический грид,", len(cars), "карточек")

def fmt_money(n):
    return f"{n:,}".replace(",", " ") + " ₽"

def parse_spec(spec):
    """'180 600 км · белый · 1.5 (113 л.с.) · кроссовер' -> dict"""
    spec = spec or ''
    parts = [p.strip() for p in spec.split('·') if p.strip()]
    d = {'raw': spec, 'mileage': None, 'color': None, 'engine': None, 'body': None}
    for p in parts:
        if 'км' in p:
            d['mileage'] = p
        elif 'л.с.' in p or re.match(r'^\d', p):
            d['engine'] = p
        elif p in ('кроссовер','седан','хэтчбек','минивэн','универсал','внедорожник'):
            d['body'] = p
        elif d['color'] is None:
            d['color'] = p
    return d

def komplekt_items(k):
    return [x.strip() for x in (k or '').split('·') if x.strip()]

VARIANT_LABELS = {"0": "Без ПВ", "10": "ПВ 10%", "20": "ПВ 20%", "30": "ПВ 30%"}
TERM_LABELS = {"12": "12 мес", "24": "24 мес", "36": "36 мес"}

def car_title(car):
    return f"{car['marka'].strip()} {car['model'].strip()}"

def build_calculator_data(car):
    # JSON blob embedded per-page for the small vanilla-JS toggle script
    return json.dumps(car['variants'], ensure_ascii=False)

LEASE_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none"><path d="M12 2L4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 8v4M12 15.5v.01" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>'

def card_day_at_max_term(car):
    """Зеркалит cardDayAtMaxTerm() из JS каталога: карточка показывает цену на максимальном ПВ (20%) и максимальном сроке (самый низкий платёж)."""
    variants = car.get('variants') or {}
    variant = variants.get('20') or (list(variants.values())[0] if variants else None)
    if not variant or not variant.get('terms'):
        return None
    max_term = max(variant['terms'].keys(), key=int)
    t = variant['terms'][max_term]
    return t

def render_catalog_grid(cars, slugs_by_art, base=''):
    """Статический (пререндеренный) список карточек. Используется и для <div id="dlGrid">
    в catalog.html (base=''), и для страниц-лендингов по маркам/кузовам (base='../../') —
    в обоих случаях интерактивность не нужна, только валидный HTML с реальными <a href>
    на страницы машин, чтобы поисковый бот видел контент и ссылки, даже не выполняя JS."""
    cards = []
    for car in cars:
        slug = slugs_by_art.get(car['art'], '')
        title = car_title(car)
        spec = html.escape(car.get('spec') or car.get('kuzov') or '')
        photos = car.get('photos') or []
        art_html = ''
        if photos:
            count_badge = f'<span class="dl-gallery__count">1 / {len(photos)}</span>' if len(photos) > 1 else ''
            photo0 = photo_rel(photos[0]) if base else photos[0]
            art_html = f'<img src="{html.escape(photo0)}" alt="{html.escape(title)}, фото 1" loading="lazy">{count_badge}'
        lease_badge = f'<div class="dl-lease-badge">{LEASE_ICON_SVG}<span>Лизинговая программа</span></div>' if car.get('isLeaseProgram') else ''
        issued_stamp = '<div class="dl-issued-stamp">Выдана</div>' if car.get('isIssued') else ''
        lease_tag = f'<div class="dl-card__lease-tag">{LEASE_ICON_SVG}<span>Лизинговая программа</span></div>' if car.get('isLeaseProgram') else ''
        komplekt_html = f'<div class="dl-komplekt">{html.escape(car["komplekt"])}</div>' if car.get('komplekt') else ''

        t = card_day_at_max_term(car)
        if car.get('isIssued'):
            price_html = '<div class="dl-unavail-note">Автомобиль выдан клиенту, сейчас недоступен</div>'
            cta_html = '<button type="button" class="dl-btn dl-btn--disabled" disabled>Забронирован</button>'
        elif t:
            price_html = f'<div class="dl-price-row"><span class="dl-price-label">от</span><span class="dl-num">{fmt_money(t["day"])}</span><span class="dl-price-label">/день</span></div>'
            cta_html = f'<a class="dl-btn" href="{base}cars/{slug}/">Подробнее и расчёт</a>' if slug else '<span class="dl-btn dl-btn--disabled">Подробнее и расчёт</span>'
        else:
            price_html = '<div class="dl-unavail-note">Автомобиль выдан клиенту, сейчас недоступен</div>'
            cta_html = f'<a class="dl-btn" href="{base}catalog.html">Похожий автомобиль</a>'

        cards.append(
            f'<div class="dl-card">'
            f'<div class="dl-card__art">{art_html}{lease_badge}{issued_stamp}</div>'
            f'<div class="dl-card__body">{lease_tag}'
            f'<div class="dl-title">{html.escape(title)}</div>'
            f'<div class="dl-spec">{spec}</div>'
            f'{komplekt_html}{price_html}{cta_html}'
            f'</div></div>'
        )
    return ''.join(cards)

def plural_ru(n, one, few, many):
    n_abs = abs(n) % 100
    n1 = n_abs % 10
    if 10 < n_abs < 20:
        return many
    if n1 == 1:
        return one
    if 2 <= n1 <= 4:
        return few
    return many

LISTING_PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{analytics_head}
<title>{title_tag}</title>
<meta name="description" content="{meta_desc}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:locale" content="ru_RU">
<meta property="og:site_name" content="Драйв Лизинг">
<meta property="og:title" content="{title_tag}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:url" content="{canonical}">
<link rel="icon" type="image/png" href="../../favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@500;600;700;800&family=Golos+Text:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="../../assets/site.css">
<script type="application/ld+json">{breadcrumb_schema}</script>
</head>
<body>
<div class="dl-topbar">
  <div class="dl-topbar__inner">
    <a href="../../" class="dl-topbar__logo">
      <img src="../../logo-topbar.webp" alt="Драйв Лизинг" class="dl-topbar__logo-img">
      <div class="dl-topbar__logo-text">
        <div class="dl-topbar__slogan">Помогаем получить автомобиль, <em>даже если банк отказал</em></div>
        <div class="dl-topbar__caption">Работаем с физ. и юр. лицами</div>
      </div>
    </a>
  </div>
</div>
{catnav}

<div class="dl-wrap">
  <nav class="dl-breadcrumb" aria-label="Хлебные крошки">
    <a href="../../">Главная</a><span>/</span>
    <a href="../../catalog.html">Каталог</a><span>/</span>
    <span>{crumb_name}</span>
  </nav>

  <div class="dl-heading" style="margin-top:20px;">
    <h1 style="font-size:24px;font-weight:800;margin:0;color:var(--navy);font-family:'Onest',Arial,sans-serif;">{h1}</h1>
  </div>
  <p style="font-size:14px;color:var(--navy-soft);line-height:1.6;max-width:680px;margin:10px 0 28px;">{intro}</p>

  <div class="dl-grid">{grid}</div>
  {empty_block}

  <p style="margin:28px 0 0;"><a href="../../catalog.html" style="color:var(--blue);font-weight:600;text-decoration:none;font-size:14px;">← Смотреть весь каталог ({total} автомобилей)</a></p>
</div>

{footer}

{cookie_banner}
<script src="../../assets/car-page.js"></script>
</body>
</html>
'''

def render_listing_page(h1, title_tag, meta_desc, intro, crumb_name, canonical, cars_subset, slugs_by_art, total, catnav):
    grid = render_catalog_grid(cars_subset, slugs_by_art, base='../../')
    empty_block = '' if cars_subset else '<div class="dl-empty">Пока нет автомобилей в этой категории — уточните у менеджера.</div>'
    breadcrumb_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": f"{SITE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Каталог", "item": f"{SITE_URL}/catalog.html"},
            {"@type": "ListItem", "position": 3, "name": crumb_name, "item": canonical},
        ]
    }, ensure_ascii=False)
    return LISTING_PAGE_TEMPLATE.format(
        title_tag=html.escape(title_tag),
        meta_desc=html.escape(meta_desc),
        canonical=canonical,
        breadcrumb_schema=breadcrumb_schema,
        crumb_name=html.escape(crumb_name),
        h1=html.escape(h1),
        intro=html.escape(intro),
        grid=grid,
        empty_block=empty_block,
        total=total,
        footer=FOOTER_HTML,
        cookie_banner=COOKIE_BANNER_HTML,
        analytics_head=ANALYTICS_HEAD,
        catnav=catnav,
    )

CONTENT_PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{analytics_head}
<title>{title_tag}</title>
<meta name="description" content="{meta_desc}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:locale" content="ru_RU">
<meta property="og:site_name" content="Драйв Лизинг">
<meta property="og:title" content="{title_tag}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:url" content="{canonical}">
<link rel="icon" type="image/png" href="../../favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@500;600;700;800&family=Golos+Text:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="../../assets/site.css">
<script type="application/ld+json">{breadcrumb_schema}</script>
</head>
<body>
<div class="dl-topbar">
  <div class="dl-topbar__inner">
    <a href="../../" class="dl-topbar__logo">
      <img src="../../logo-topbar.webp" alt="Драйв Лизинг" class="dl-topbar__logo-img">
      <div class="dl-topbar__logo-text">
        <div class="dl-topbar__slogan">Помогаем получить автомобиль, <em>даже если банк отказал</em></div>
        <div class="dl-topbar__caption">Работаем с физ. и юр. лицами</div>
      </div>
    </a>
  </div>
</div>
{catnav}

<div class="dl-wrap">
  <nav class="dl-breadcrumb" aria-label="Хлебные крошки">
    <a href="../../">Главная</a><span>/</span>
    <span>{crumb_name}</span>
  </nav>

  <div class="dl-content-page-grid">
    <div class="dl-content-page">
      <h1>{h1}</h1>
      <div class="dl-view-counter">
        <svg class="dl-view-counter__icon" viewBox="0 0 24 24" fill="none"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.6"/></svg>
        <span id="dlViewCount">—</span> просмотров
      </div>
      <p class="dl-content-page__lead">{lead}</p>
      {body}
      <div class="dl-content-page__cta">
        <a class="dl-btn" href="../../catalog.html">Смотреть каталог автомобилей →</a>
      </div>
    </div>
    <aside class="dl-content-page__sidebar">
      <div class="dl-banner-carousel" id="dlBannerCarousel">
        {banner_slides}
      </div>
      <div class="dl-banner-dots" id="dlBannerDots"></div>
      {related_articles}
    </aside>
  </div>
</div>

<script>
(function(){{
  var el = document.getElementById('dlBannerCarousel');
  if (!el) return;
  var slides = el.querySelectorAll('.dl-banner-carousel__slide');
  if (slides.length < 2) return;
  var DURATION = 4500;
  var CIRC = 37.7;
  var dotsWrap = document.getElementById('dlBannerDots');
  var dots = [];
  if (dotsWrap) {{
    slides.forEach(function(){{
      var dot = document.createElement('span');
      dot.className = 'dl-banner-dot';
      dot.innerHTML = '<svg viewBox="0 0 16 16"><circle class="dl-banner-dot__track" cx="8" cy="8" r="6"/><circle class="dl-banner-dot__fill" cx="8" cy="8" r="6"/></svg>';
      dotsWrap.appendChild(dot);
      dots.push(dot.querySelector('.dl-banner-dot__fill'));
    }});
  }}
  function setDot(fill, state){{
    if (!fill) return;
    fill.style.transition = 'none';
    fill.style.strokeDashoffset = state === 'done' ? '0' : String(CIRC);
    if (state === 'current') {{
      void fill.getBoundingClientRect();
      fill.style.transition = 'stroke-dashoffset ' + DURATION + 'ms linear';
      fill.style.strokeDashoffset = '0';
    }}
  }}
  var i = 0;
  function activate(idx){{
    slides[i].classList.remove('is-active');
    i = idx;
    slides[i].classList.add('is-active');
    dots.forEach(function(fill, j){{
      setDot(fill, j < i ? 'done' : (j === i ? 'current' : 'pending'));
    }});
  }}
  dots.forEach(function(fill, j){{ setDot(fill, j === 0 ? 'current' : 'pending'); }});
  setInterval(function(){{ activate((i + 1) % slides.length); }}, DURATION);
}})();
</script>

<script>
(function(){{
  var countEl = document.getElementById('dlViewCount');
  if (!countEl) return;
  var slug = '{slug}';
  var api = '{worker_url}/views?slug=' + encodeURIComponent(slug);
  var sessionKey = 'dl_viewed_' + slug;
  var alreadyViewed = false;
  try {{ alreadyViewed = sessionStorage.getItem(sessionKey) === '1'; }} catch (e) {{}}
  function render(n){{ countEl.textContent = n; }}
  fetch(api, {{ method: alreadyViewed ? 'GET' : 'POST' }})
    .then(function(r){{ return r.json(); }})
    .then(function(d){{
      if (d && d.ok) {{
        render(d.views);
        try {{ sessionStorage.setItem(sessionKey, '1'); }} catch (e) {{}}
      }}
    }})
    .catch(function(){{}});
  setInterval(function(){{
    fetch(api).then(function(r){{ return r.json(); }}).then(function(d){{
      if (d && d.ok) render(d.views);
    }}).catch(function(){{}});
  }}, 8000);
}})();
</script>

{footer}

{cookie_banner}
<script src="../../assets/car-page.js"></script>
</body>
</html>
'''

# Карусель баннеров в сайдбаре статей: 1 общий имиджевый слайд (готовая картинка,
# "более 60 авто") + N слайдов под конкретные машины + слайд подписки. Машины —
# это готовые карточки клиента (фото+заголовок+характеристики+цена нарезаны один
# в один из "новый баннер.png" / "баннер 6-9.png", без кнопки — она в исходниках
# сидела на разной высоте на разных карточках, из-за чего "прыгала" при смене
# слайда). Кнопка "Посмотреть →" — обычный HTML-элемент под картинкой, одинаковый
# по размеру и месту на каждом слайде.
BANNER_CAR_ARTS = ['ДЛ-001', 'ДЛ-002', 'ДЛ-062', 'ДЛ-044', 'ДЛ-039', 'ДЛ-040', 'ДЛ-043', 'ДЛ-045']

def render_promo_car_card(car, slug):
    title = f"{car['marka'].strip()} {car['model'].strip()}"
    return f'''<div class="dl-banner-carousel__slide dl-banner-card-img">
      <div class="dl-banner-card-img__photo"><img src="../../images/promo/card-{slug}.webp" alt="{html.escape(title)}" loading="lazy"></div>
      <a class="dl-banner-card-img__cta" href="../../cars/{slug}/">Посмотреть →</a>
    </div>'''

TELEGRAM_ICON_SVG = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="12" fill="#29A9EB"/><path d="M17.53 7.2L15.4 17.6c-.16.72-.58.9-1.18.56l-3.26-2.4-1.57 1.51c-.17.18-.32.33-.66.33l.24-3.36 6.1-5.51c.27-.24-.06-.37-.41-.13l-7.54 4.75-3.25-1.02c-.7-.22-.72-.7.15-1.04l12.7-4.9c.59-.22 1.1.14.9 1.05z" fill="#fff"/></svg>'

def render_subscribe_slide():
    return f'''<div class="dl-banner-carousel__slide dl-banner-subscribe">
      <div class="dl-banner-subscribe__title">Узнавайте первыми<span>о новых предложениях</span></div>
      <p class="dl-banner-subscribe__text">В наших каналах публикуем выгодные автомобили, актуальные предложения и полезные советы.</p>
      <a class="dl-banner-subscribe__btn dl-banner-subscribe__btn--max" href="{MAX_CHANNEL_URL}" target="_blank" rel="noopener">
        <span class="dl-banner-subscribe__btn-ico"><img src="../../images/icons3d/max-badge.png" alt=""></span>
        <span>Перейти в MAX</span>
        <span class="dl-banner-subscribe__btn-arrow">→</span>
      </a>
      <a class="dl-banner-subscribe__btn dl-banner-subscribe__btn--tg" href="{TG_CHANNEL_URL}" target="_blank" rel="noopener">
        <span class="dl-banner-subscribe__btn-ico">{TELEGRAM_ICON_SVG}</span>
        <span>Перейти в Telegram</span>
        <span class="dl-banner-subscribe__btn-arrow">→</span>
      </a>
      <div class="dl-banner-subscribe__note">
        <svg viewBox="0 0 24 24" fill="none"><path d="M17 20v-1.5a3.5 3.5 0 00-3.5-3.5h-5A3.5 3.5 0 005 18.5V20M9.5 12a3 3 0 100-6 3 3 0 000 6zM19 20v-1.5a3 3 0 00-2-2.83M15 4.17a3 3 0 010 5.66" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Более 300 человек уже с нами
      </div>
    </div>'''

def render_banner_slides(cars, slugs_by_art):
    by_art = {c['art']: c for c in cars}
    generic = ('<a class="dl-banner-carousel__slide is-active" href="../../catalog.html">'
               '<img src="../../images/promo/sidebar-banner.webp" alt="Более 60 авто в наличии — без банка, взнос от 0%, по 2 документам. Смотреть каталог" loading="lazy"></a>')
    cards = "".join(
        render_promo_car_card(by_art[art], slugs_by_art[art])
        for art in BANNER_CAR_ARTS if art in by_art
    )
    return generic + cards + render_subscribe_slide()

def render_related_articles(current_slug):
    others = [a for a in BLOG_ARTICLES if a[0] != current_slug][:1]
    if not others:
        return ''
    items = ''.join(
        f'<a class="dl-related-articles__item" href="../{slug}/">'
        f'<span class="dl-related-articles__title">{html.escape(title)}</span>'
        f'<span class="dl-related-articles__excerpt">{html.escape(excerpt)}</span>'
        f'</a>'
        for slug, title, excerpt, date in others
    )
    return f'<div class="dl-related-articles"><div class="dl-related-articles__heading">Другие статьи</div>{items}</div>'

def render_content_page(h1, title_tag, meta_desc, lead, body, crumb_name, canonical, banner_slides, slug, catnav):
    breadcrumb_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": f"{SITE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": crumb_name, "item": canonical},
        ]
    }, ensure_ascii=False)
    return CONTENT_PAGE_TEMPLATE.format(
        title_tag=html.escape(title_tag),
        meta_desc=html.escape(meta_desc),
        canonical=canonical,
        breadcrumb_schema=breadcrumb_schema,
        crumb_name=html.escape(crumb_name),
        h1=html.escape(h1),
        lead=html.escape(lead),
        body=body,
        footer=FOOTER_HTML,
        cookie_banner=COOKIE_BANNER_HTML,
        analytics_head=ANALYTICS_HEAD,
        banner_slides=banner_slides,
        related_articles=render_related_articles(slug),
        slug=slug,
        catnav=catnav,
        worker_url=WORKER_URL,
    )

COEFF_TABLE = '''<table>
<tr><th>Первоначальный взнос</th><th>Коэффициент</th></tr>
<tr><td>0%</td><td>2.3</td></tr>
<tr><td>10%</td><td>2.0</td></tr>
<tr><td>20%</td><td>1.8</td></tr>
<tr><td>30%</td><td>1.6</td></tr>
</table>'''

ARENDA_VYKUP_BODY = f'''<h2>Что такое аренда с выкупом</h2>
<p>Аренда автомобиля с правом выкупа — способ получить машину без банка и без проверки кредитной истории. Вносите первоначальный взнос (можно и без него), дальше платите по графику. По окончании срока договора автомобиль переходит в вашу собственность.</p>
<p>Главное отличие от автокредита: банк не участвует в сделке, поэтому не важны официальный доход и кредитная история. Решение по заявке — за 1 день.</p>

<h2>Как считается платёж</h2>
<p>Формула: итоговая сумма = цена автомобиля × коэффициент. Коэффициент зависит от размера первоначального взноса — чем больше взнос, тем ниже коэффициент и итоговая переплата.</p>
{COEFF_TABLE}
<p>Взнос снижает коэффициент, а не прибавляется к сумме сверху — платёж считается уже с учётом скидки за взнос.</p>

<h2>Что нужно для оформления</h2>
<ul>
<li>Паспорт РФ</li>
<li>Водительское удостоверение</li>
<li>Оформление по 2 документам, без справок о доходах</li>
</ul>

<h2>Кому подходит</h2>
<p>Аренда с выкупом подходит тем, кому банк отказал в кредите, у кого нет официального трудоустройства или кредитной истории, и тем, кто хочет получить автомобиль быстро — без долгого одобрения.</p>'''

LIZING_YURLICAM_BODY = f'''<h2>Кому подходит</h2>
<p>Лизинг подходит компаниям и ИП, которым нужно обновить или расширить автопарк без разовой крупной траты. Коэффициенты те же, что и для физических лиц — разница в сроке договора и в том, что автомобиль оформляется на юридическое лицо.</p>

<h2>Условия</h2>
{COEFF_TABLE}
<p>Срок договора для юридических лиц — 48 или 60 месяцев. Без банка, взнос от 0%, оформление по 2 документам.</p>

<h2>Чем лизинг выгоднее покупки в кредит</h2>
<p>Лизинговый платёж можно относить на расходы компании, не привлекая банк и не отвлекая оборотные средства на разовую покупку. Подходит для обновления парка такси, курьерской службы, корпоративного транспорта.</p>

<h2>Как оформить</h2>
<p>Свяжитесь с менеджером через каталог или мессенджеры — подберём автомобиль и рассчитаем точные условия под ваш ОКВЭД и задачи бизнеса.</p>'''

# Страница пока не наполнена подробным содержанием (ARENDA_VYKUP_BODY/LIZING_YURLICAM_BODY
# выше уже написаны и ждут своего часа) — сознательно показываем короткую заглушку,
# чтобы URL и H1 уже жили и индексировались, не блокируя запуск ради текста.
COMING_SOON_BODY = '''<p>Мы дорабатываем эту страницу — подробности появятся здесь в ближайшее время.</p>
<p>А пока можно посмотреть весь каталог автомобилей, почитать про <a href="../kupit-ili-arenda-s-vykupom/">разницу между арендой с выкупом и автокредитом</a> или написать нам в Telegram/MAX — ответим на любые вопросы уже сейчас.</p>'''

CONTACTS_SCHEMA = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"AutoDealer","name":"Драйв Лизинг","image":"https://driveleasing38.ru/logo.png","url":"https://driveleasing38.ru/contacts/","telephone":"+79950527683","address":{"@type":"PostalAddress","streetAddress":"ул. Байкальская, 208","addressLocality":"Иркутск","addressCountry":"RU"},"areaServed":"Иркутск","priceRange":"$$","sameAs":["https://t.me/drivelizing","https://max.ru/id30954831331_biz","https://2gis.ru/irkutsk/search/драйв%20лизинг/firm/70000001099120012/104.32804%2C52.257428"],"aggregateRating":{"@type":"AggregateRating","ratingValue":"4.9","reviewCount":"400"},"openingHoursSpecification":{"@type":"OpeningHoursSpecification","dayOfWeek":["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],"opens":"09:00","closes":"21:00"}}</script>'

CONTACTS_BODY = CONTACTS_SCHEMA + '''
<ul class="dl-content-page__facts">
<li>📞 Телефон: <a href="tel:+79950527683">+7 995 052-76-83</a>, ежедневно с 9:00 до 21:00</li>
<li>📍 Адрес: г. Иркутск, ул. Байкальская, 208 (отдел продаж)</li>
<li>💬 Telegram: <a href="https://t.me/avtohere38" target="_blank" rel="noopener">написать нам</a></li>
<li>💬 MAX: <a href="https://max.ru/u/f9LHodD0cOJwdXPtIRKpSznrrNNKwx-l7-HcyIykYTEMu3kGUgp9u4vTgm8" target="_blank" rel="noopener">написать нам</a></li>
</ul>
<p>Быстрее всего отвечаем в мессенджерах — там же можно скинуть ссылку на объявление или фото машины, если ищете что-то конкретное.</p>
<p>Если уже присмотрели автомобиль, удобнее сразу открыть <a href="../catalog.html">каталог</a> и оставить заявку на расчёт из карточки — менеджер перезвонит и посчитает точные условия.</p>'''

O_KOMPANII_BODY = '''<p>Драйв Лизинг — аренда автомобилей с выкупом и лизинг в Иркутске, без банка и без кредитной истории. Работаем с физическими и юридическими лицами на одних и тех же условиях.</p>
<ul class="dl-content-page__facts">
<li>🚘 Собственный автопарк 100+ автомобилей</li>
<li>⭐ Более 400 отзывов, рейтинг 4.9</li>
<li>✅ 92% заявок получают одобрение по внутренней статистике</li>
<li>📅 На рынке Иркутска 7 лет</li>
</ul>
<p>Бизнес вырос из бренда «The Drive» — за эти годы собрали собственный парк машин с пробегом и отладили работу так, чтобы оформление не зависело от банка: без справок о доходах, по паспорту и водительскому удостоверению.</p>
<p>Отдельно работаем с новыми автомобилями под заказ у дилера — для них те же условия и тот же принцип: сначала считаем и показываем весь график платежей, потом оформляем.</p>
<p>Если банк уже отказал или кредитная история мешает получить обычный автокредит — это как раз тот случай, для которого мы работаем.</p>
<p class="dl-content-page__footnote">92% одобрений — показатель по внутренней статистике Драйв Лизинг, не является гарантией одобрения каждой заявки.</p>'''

ARENDA_ILI_KREDIT_BODY = f'''<h2>Сколько стоит аренда с выкупом</h2>
<p>Итоговая сумма считается так: цена автомобиля × коэффициент. Коэффициент зависит от первоначального взноса, чем больше взнос, тем ниже коэффициент.</p>
{COEFF_TABLE}
<p>Пример на автомобиле за 1 000 000 ₽ без первоначального взноса: итого 2 300 000 ₽, переплата за весь срок 1 300 000 ₽. При взносе 20% коэффициент падает до 1.8, итого 1 800 000 ₽.</p>

<h2>Какой это процент годовых</h2>
<p>Если пересчитать переплату в процент годовых для сравнения с кредитом, цифра зависит от срока: чем длиннее срок, тем ниже процент в годовом выражении, потому что переплата распределяется на большее число лет.</p>
<table>
<tr><th>Срок договора</th><th>Процент годовых (ориентировочно)</th></tr>
<tr><td>12 месяцев</td><td>~130%</td></tr>
<tr><td>24 месяца</td><td>~65%</td></tr>
<tr><td>36 месяцев</td><td>~43%</td></tr>
<tr><td>48 месяцев</td><td>~32%</td></tr>
<tr><td>60 месяцев</td><td>~26%</td></tr>
</table>
<p>Это выше, чем ставка по банковскому автокредиту (обычно 15-25% годовых). Разница объясняется просто: банк выдаёт кредит только тем, у кого хорошая кредитная история и подтверждённый доход, а аренда с выкупом работает без проверки банка и без справок.</p>

<h2>Когда выгоднее банк, а когда аренда с выкупом</h2>
<p>Если у вас официальный доход, хорошая кредитная история и банк готов одобрить кредит, обычный автокредит почти всегда будет дешевле по деньгам. Это честно, мы не скрываем эту разницу.</p>
<p>Аренда с выкупом подходит, если банк уже отказал, нет официального трудоустройства, испорчена кредитная история, или просто нужно оформить быстро без долгого сбора справок. Вы платите больше за скорость и доступность, а не за то, что где-то дороже без причины.</p>

<h2>Что нужно для оформления</h2>
<ul>
<li>Паспорт РФ</li>
<li>Водительское удостоверение</li>
<li>Оформление по 2 документам, без справок о доходах</li>
</ul>'''

KUPIT_ILI_ARENDA_BODY = '''<p>Когда человек выбирает автомобиль, один из первых вопросов: <strong>как выгоднее его оформить?</strong></p>
<p>Взять автокредит? Или рассмотреть аренду с последующим выкупом?</p>
<p>Мы решили не сравнивать банковскую процентную ставку с нашим коэффициентом. Это разные показатели, и такое сравнение мало что говорит клиенту.</p>
<p>Посчитаем проще: сколько денег реально уйдёт из кармана за автомобиль. Для примера возьмём машину стоимостью 1 500 000 ₽ и первоначальный взнос 300 000 ₽.</p>
<p>Сразу скажем честно: аренда с выкупом не обязательно будет дешевле хорошего банковского кредита. Но цена здесь не единственное отличие.</p>

<h3>🏦 Вариант №1. Покупаем автомобиль в кредит</h3>
<ul class="dl-content-page__facts">
<li>🚘 Стоимость автомобиля: 1 500 000 ₽</li>
<li>💳 Первоначальный взнос: 300 000 ₽</li>
<li>📅 Срок: 5 лет</li>
</ul>
<p>Для примера возьмём среднюю итоговую переплату по автокредиту <strong>67%</strong> за весь срок. Тогда автомобиль стоимостью 1 500 000 ₽ в итоге обойдётся примерно в:</p>
<p class="dl-content-page__formula">1 500 000 × 1,67 = 2 505 000 ₽</p>
<p>Но к этому могут добавляться расходы на страхование. Для нашего примера возьмём:</p>
<ul class="dl-content-page__facts">
<li>ОСАГО: около 10 000 ₽ в год</li>
<li>КАСКО: около 70 000 ₽ в год в течение первых трёх лет</li>
</ul>
<p>Получаем:</p>
<table>
<tr><th>Расход</th><th>Сумма</th></tr>
<tr><td>Стоимость автомобиля + переплата по кредиту</td><td>≈ 2 505 000 ₽</td></tr>
<tr><td>ОСАГО за 5 лет</td><td>≈ 50 000 ₽</td></tr>
<tr><td>КАСКО за 3 года</td><td>≈ 210 000 ₽</td></tr>
<tr><td>Итого</td><td>≈ 2 765 000 ₽</td></tr>
</table>
<p class="dl-content-page__formula">💰 Примерный итог: 2 765 000 ₽ за 5 лет</p>
<p>Важно понимать: <strong>67% здесь используется как средний ориентир для нашего сравнения</strong>, а не как универсальная переплата любого автокредита. Конкретный кредит может оказаться как дешевле, так и дороже. Смотрите на полную стоимость конкретного предложения банка, страховки и дополнительные услуги.</p>

<h3>🔵 Вариант №2. Аренда с выкупом через Драйв Лизинг</h3>
<p>Теперь возьмём тот же автомобиль:</p>
<ul class="dl-content-page__facts">
<li>🚘 Стоимость: 1 500 000 ₽</li>
<li>💳 Первоначальный взнос: 300 000 ₽, или 20%</li>
<li>📅 Срок: 3 года</li>
<li>📊 Коэффициент: 1,8</li>
</ul>
<p>Считаем:</p>
<p class="dl-content-page__formula">1 500 000 × 1,8 = 2 700 000 ₽</p>
<p>Это сумма платежей по договору. И здесь есть <strong>очень важный момент</strong>. Первоначальный взнос у нас <strong>не вычитается</strong> из этой суммы. Он оплачивается отдельно:</p>
<p class="dl-content-page__formula">2 700 000 + 300 000 = 3 000 000 ₽</p>
<p>Добавляем ориентировочное ОСАГО:</p>
<table>
<tr><th>Расход</th><th>Сумма</th></tr>
<tr><td>Платежи по договору</td><td>2 700 000 ₽</td></tr>
<tr><td>Первоначальный взнос</td><td>300 000 ₽</td></tr>
<tr><td>ОСАГО за 3 года</td><td>≈ 30 000 ₽</td></tr>
<tr><td>КАСКО</td><td>Не требуется</td></tr>
<tr><td>Итого</td><td>≈ 3 030 000 ₽</td></tr>
</table>
<p class="dl-content-page__formula">💰 Примерный итог: 3 030 000 ₽ за 3 года</p>

<h2>📊 Сравним цифры</h2>
<p>Получается:</p>
<ul class="dl-content-page__facts">
<li>🏦 Автокредит: ≈ 2 765 000 ₽ за 5 лет</li>
<li>🔵 Аренда с выкупом: ≈ 3 030 000 ₽ за 3 года</li>
</ul>
<p class="dl-content-page__formula">Разница: ≈ 265 000 ₽</p>
<p>То есть в нашем примере аренда с выкупом обходится примерно на 265 тысяч рублей дороже. И мы не собираемся прятать эту разницу. Но теперь возникает главный вопрос.</p>

<h2>🤔 Если кредит дешевле, зачем аренда с выкупом?</h2>
<p>Потому что сначала этот кредит нужно получить. Можно найти банк с хорошей ставкой, посчитать красивый ежемесячный платёж и подобрать автомобиль. Но если банк отвечает:</p>
<blockquote>❌ «Отказано»</blockquote>
<p>вся эта математика перестаёт иметь значение. Банки оценивают кредитную историю, долговую нагрузку, подтверждение дохода и другие параметры клиента. А у нас другая модель рассмотрения заявки.</p>

<h3>🛡 92% одобрений</h3>
<p>По внутренней статистике Драйв Лизинг <strong>92% заявок получают одобрение</strong>.* Мы рассматриваем в том числе клиентов, которым ранее отказал банк или которым сложно получить обычный автокредит.</p>
<p>Для оформления автомобиля из нашего автопарка нужны:</p>
<ul class="dl-content-page__facts">
<li>🪪 паспорт</li>
<li>🚘 водительское удостоверение</li>
</ul>
<p><strong>Банк в сделке не участвует.</strong> И в этом заключается основная ценность аренды с последующим выкупом.</p>
<p class="dl-content-page__footnote">*Одобрение не гарантируется. Решение принимается индивидуально после рассмотрения заявки.</p>

<h2>💡 За что тогда переплата в 265 000 ₽?</h2>
<p>В нашем примере разница составляет примерно 265 000 ₽ за весь срок. Если очень грубо разделить её на 36 месяцев:</p>
<p class="dl-content-page__formula">≈ 7 360 ₽ в месяц</p>
<p>За эту разницу клиент получает <strong>альтернативный способ приобретения автомобиля без автокредита</strong>, когда стандартный банковский вариант ему недоступен или не подходит. Поэтому мы не позиционируем аренду с выкупом как «кредит, только дешевле». Это было бы неправильно.</p>
<p>Мы предлагаем другой путь:</p>
<blockquote>Банк не одобрил автомобиль? Это ещё не значит, что от него нужно отказываться.</blockquote>

<h2>🗓 Почему у кредита 5 лет, а у нас 3 года?</h2>
<p>Потому что срок зависит от автомобиля и программы.</p>
<h3>🚙 Автомобили с пробегом из нашего автопарка</h3>
<p>Оформляются на срок до 3 лет.</p>
<h3>✨ Новые автомобили</h3>
<p>Новые машины можно оформить через лизинговую программу на более длительный срок, в том числе 4 или 5 лет. Поэтому условия конкретной сделки всегда нужно считать отдельно.</p>

<h2>🛡 А что с КАСКО?</h2>
<p>При автокредите требования к страхованию зависят от конкретного банка и программы. В нашем примере мы заложили КАСКО стоимостью около 70 000 ₽ в год на первые три года. Получается:</p>
<p class="dl-content-page__formula">≈ 210 000 ₽ дополнительных расходов</p>
<p>Условия конкретного банка могут отличаться, поэтому перед оформлением кредита важно смотреть не только на ставку. Смотрите на полную стоимость кредита и дополнительные обязательные расходы.</p>
<p>В рассматриваемой программе аренды с выкупом Драйв Лизинг <strong>КАСКО не требуется</strong>.</p>

<h2>🔧 А бензин, обслуживание и ремонт?</h2>
<p>Их мы специально не считаем. Потому что независимо от способа приобретения автомобиля вам придётся:</p>
<ul class="dl-content-page__facts">
<li>⛽ заправляться</li>
<li>🔧 проходить обслуживание</li>
<li>🛞 менять резину</li>
<li>🧰 ремонтировать автомобиль при необходимости</li>
</ul>
<p>Если автомобиль один и тот же, эти расходы возникают в обоих вариантах.</p>

<h2>🚘 Кому тогда выгоднее кредит?</h2>
<p>Если у вас хорошая кредитная история, стабильный подтверждаемый доход и банк предлагает действительно хорошие условия, посчитайте кредит. Вполне возможно, что он окажется дешевле. Особенно если:</p>
<ul class="dl-content-page__facts">
<li>✅ ставка действительно выгодная</li>
<li>✅ нет дорогих дополнительных услуг</li>
<li>✅ устраивает страхование</li>
<li>✅ банк одобряет нужную сумму</li>
<li>✅ ежемесячный платёж комфортен</li>
</ul>
<p>Мы не будем убеждать вас брать аренду с выкупом просто потому, что продаём этот продукт. Сначала смотрите на свою ситуацию.</p>

<h2>🔵 А кому подходит аренда с выкупом?</h2>
<p>В первую очередь тем, кому нужен автомобиль, но обычный банковский сценарий не работает. Например:</p>
<ul class="dl-content-page__facts">
<li>❌ банк уже отказал</li>
<li>❌ плохая или испорченная кредитная история</li>
<li>❌ сложно подтвердить официальный доход</li>
<li>❌ высокая кредитная нагрузка</li>
<li>❌ не хочется оформлять автокредит</li>
<li>❌ нужен другой способ получить автомобиль</li>
</ul>
<p>Именно для таких ситуаций существует аренда с последующим выкупом.</p>

<h2>🚗 Как это работает в Драйв Лизинг?</h2>
<p>Всё достаточно просто.</p>
<ol class="dl-content-page__steps">
<li><b>Выбираете автомобиль</b>Можно выбрать машину из нашего автопарка.</li>
<li><b>Оставляете заявку</b>Для рассмотрения нужны паспорт и водительское удостоверение.</li>
<li><b>Получаете решение</b>По нашей внутренней статистике 92% заявок получают одобрение.</li>
<li><b>Получаете расчёт</b>Заранее видите первоначальный взнос, срок, платежи и общую сумму.</li>
<li><b>Подписываем договор</b>Фиксируем условия.</li>
<li><b>Забираете автомобиль 🚘</b>Пользуетесь машиной и вносите платежи согласно договору.</li>
<li><b>Автомобиль становится вашим 🔑</b>После выполнения условий договора автомобиль переходит в вашу собственность.</li>
</ol>

<h2>⚖️ Так что выгоднее: кредит или аренда с выкупом?</h2>
<p>Если смотреть только на деньги, в нашем примере:</p>
<ul class="dl-content-page__facts">
<li>Кредит: ≈ 2 765 000 ₽</li>
<li>Аренда с выкупом: ≈ 3 030 000 ₽</li>
</ul>
<p>Кредит дешевле примерно на 265 000 ₽. Но есть принципиальное условие:</p>
<blockquote>банк должен вам этот кредит одобрить.</blockquote>
<p>Если у вас хорошая кредитная история и банк предлагает адекватные условия, имеет смысл рассмотреть кредит. Если же банк уже отказал или банковский вариант вам недоступен, появляется другой путь.</p>
<div class="dl-content-page__callout">
<p>🚘 <strong>Драйв Лизинг помогает получить автомобиль даже тогда, когда банк отказал.</strong></p>
<p>92% одобрений по нашей внутренней статистике. Паспорт + водительское удостоверение. Без участия банка. Автомобили с пробегом и новые авто.</p>
</div>

<h2>📲 Хотите сравнить на конкретном автомобиле?</h2>
<p>Не нужно считать всё самостоятельно. Напишите нам «РАСЧЁТ» в Telegram или MAX — покажем первоначальный взнос, срок, размер платежа и итоговую сумму по договору. Вы сможете сами решить, подходит вам такой вариант или нет.</p>

<p class="dl-content-page__footnote">Все расчёты в статье приведены для наглядного примера. Показатель переплаты по автокредиту 67% используется как расчётный ориентир для данного примера и не является предложением конкретного банка. Фактическая полная стоимость кредита, страхования и дополнительных услуг зависит от банка, автомобиля и параметров клиента. Показатель 92% одобрений основан на внутренней статистике Драйв Лизинг и не означает гарантированного одобрения каждой заявки.</p>'''

# FAQ — вопросы/ответы копятся в одном списке по мере выхода статей (сейчас только
# из статьи "когда авто станет вашим"), рендерятся аккордеоном (details/summary,
# без JS) и переиспользуются в двух местах: встроенным блоком внутри самой статьи
# и на отдельной странице /faq/ с разметкой FAQPage для поисковиков.
FAQ_ITEMS = [
    ('Автомобиль сразу оформляется на меня?',
     'Нет. Сначала автомобиль передаётся вам во владение и пользование. Право собственности оформляется после выполнения предусмотренных договором условий.'),
    ('Можно ли пользоваться автомобилем до полного выкупа?',
     'Да. Именно для этого автомобиль и передаётся вам после оформления договора и акта приёма-передачи. Вы можете пользоваться машиной в рамках установленных договором условий.'),
    ('Из чего складывается полная стоимость автомобиля?',
     'По условиям дополнительного соглашения полная стоимость автомобиля состоит из первоначального взноса и суммы еженедельных платежей за весь срок аренды автомобиля. Конкретные условия зависят от выбранного автомобиля и программы.'),
    ('Можно ли передать автомобиль другому человеку?',
     'Передавать права и обязанности по договору третьим лицам, сдавать автомобиль в субаренду или иным образом распоряжаться им до перехода права собственности нельзя, если это не предусмотрено условиями договора.'),
    ('Что нужно сделать, чтобы автомобиль стал моим?',
     'Главное — выполнить условия договора: вносить платежи по графику → соблюдать правила эксплуатации → закрыть предусмотренные обязательства → оформить переход права собственности. После этого автомобиль становится вашим. 🚘✅'),
]

def render_faq_block(items):
    parts = []
    for q, a in items:
        parts.append(
            f'<details class="dl-faq__item"><summary class="dl-faq__q">{html.escape(q)}</summary>'
            f'<div class="dl-faq__a"><p>{html.escape(a)}</p></div></details>'
        )
    return f'<div class="dl-faq">{"".join(parts)}</div>'

def render_faq_schema(items):
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in items
        ],
    }
    return f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>'

KOGDA_AVTO_VASHIM_BODY = '''<p>Один из главных вопросов клиентов аренды с выкупом:</p>
<blockquote>«Когда автомобиль окончательно станет моим?»</blockquote>
<p><strong>Короткий ответ:</strong> после выполнения условий договора и полной оплаты предусмотренных платежей автомобиль оформляется в вашу собственность.</p>
<p>Разберём весь процесс простыми словами 👇</p>

<h2>🚘 Как работает аренда автомобиля с выкупом?</h2>
<p>При обычной аренде вы пользуетесь автомобилем определённое время, а затем возвращаете его владельцу. При аренде с последующим выкупом цель другая: вы получаете автомобиль во владение и пользование, вносите платежи согласно договору, а после выполнения предусмотренных договором условий автомобиль оформляется в вашу собственность.</p>
<p>В Драйв Лизинг автомобиль передаётся клиенту по акту приёма-передачи. В нём фиксируются данные машины, её состояние, комплектация и другие характеристики.</p>
<p class="dl-content-page__formula">Выбрали автомобиль → подписали договор → получили машину → вносите платежи → выполняете условия договора → автомобиль становится вашим.</p>

<h2>🔑 Пользоваться автомобилем и быть его собственником — не одно и то же</h2>
<p>С момента передачи автомобиля вы можете пользоваться им в соответствии с условиями договора. Но юридически до полного выполнения условий договора собственником автомобиля остаётся Арендодатель. После выполнения условий выкупа оформляется переход права собственности, и автомобиль становится вашим.</p>
<p>До этого момента автомобиль нельзя самостоятельно продать, передать права по договору другому человеку, сдать машину в субаренду или использовать её в качестве залога.</p>

<h2>📅 Когда именно автомобиль станет вашим?</h2>
<p>В Драйв Лизинг условия будущего перехода автомобиля в собственность закрепляются документально. Арендодатель обязуется оформить право собственности на автомобиль на Арендатора после выполнения условий договора в полном объёме.</p>
<p>Если говорить максимально просто:</p>
<ol class="dl-content-page__steps">
<li><b>Вы выбираете автомобиль</b></li>
<li><b>Оформляете договор</b></li>
<li><b>Получаете автомобиль и начинаете им пользоваться</b></li>
<li><b>Вносите платежи согласно графику</b></li>
<li><b>Выполняете остальные обязательства по договору</b></li>
<li><b>После выполнения условий автомобиль оформляется в вашу собственность ✅</b></li>
</ol>

<h2>💰 Что необходимо выполнить для перехода автомобиля в собственность?</h2>
<p>Важно не просто дождаться окончания срока договора. Для оформления автомобиля в собственность необходимо выполнить предусмотренные договором финансовые и иные обязательства. В частности, должны быть внесены:</p>
<ul class="dl-content-page__facts">
<li>✔️ первоначальный взнос, если он предусмотрен условиями</li>
<li>✔️ еженедельные платежи за весь предусмотренный период</li>
<li>✔️ расходы по ремонту автомобиля, если такая обязанность возникла</li>
<li>✔️ расходы по послеаварийному ремонту, если они возникли</li>
<li>✔️ штрафы ГИБДД и другие предусмотренные платежи</li>
<li>✔️ предусмотренные договором штрафы и пени, если они возникли</li>
</ul>
<p>Все платежи фиксируются в платёжной ведомости. Поэтому самый простой путь к собственному автомобилю — соблюдать график платежей, следить за состоянием машины и выполнять условия договора.</p>

<h2>📄 Что происходит после последнего платежа?</h2>
<p>После того как предусмотренные договором платежи внесены и остальные обязательства выполнены, можно переходить к оформлению автомобиля в собственность. Проверяется отсутствие незакрытых обязательств по договору и оформляются необходимые документы для перехода автомобиля новому владельцу.</p>
<p>После этого автомобиль уже не просто находится у вас в пользовании — вы становитесь его собственником. 🎉 Далее необходимо выполнить предусмотренные законодательством регистрационные действия и оформить автомобиль на нового владельца.</p>

<h2>🚙 Что происходит с автомобилем во время действия договора?</h2>
<p>Вы пользуетесь автомобилем как своим повседневным транспортом, но до перехода права собственности должны соблюдать предусмотренные договором правила эксплуатации. В течение срока действия договора необходимо следить за техническим состоянием автомобиля, своевременно проводить необходимое обслуживание, соблюдать условия эксплуатации и своевременно вносить платежи.</p>
<p>При передаче автомобиля клиент получает необходимые для эксплуатации документы и ключи. Состояние автомобиля при передаче фиксируется в акте приёма-передачи.</p>

<h2>🛠 Кто обслуживает автомобиль?</h2>
<p>В течение срока действия договора Арендатор следит за состоянием автомобиля и несёт предусмотренные договором расходы, связанные с его эксплуатацией и техническим обслуживанием. Важно своевременно проходить необходимое обслуживание и сообщать Драйв Лизинг о повреждениях или неисправностях автомобиля.</p>
<p>Это важно не только для соблюдения договора, но и для того, чтобы автомобиль сохранялся в хорошем техническом состоянии на всём пути до перехода в вашу собственность.</p>

<h2>🚔 А что со штрафами ГИБДД?</h2>
<p>Если нарушение произошло в период, когда автомобилем пользовался Арендатор, соответствующие обязательства по штрафам необходимо закрыть. Поэтому перед оформлением автомобиля в собственность важно, чтобы предусмотренные договором обязательства были выполнены.</p>
<p>Самый простой вариант — своевременно оплачивать возникающие штрафы и не оставлять задолженности к окончанию срока договора.</p>

<h2>❌ Можно ли продать автомобиль до полного выкупа?</h2>
<p><strong>Нет.</strong> Пока право собственности на автомобиль не перешло к вам, самостоятельно продавать его нельзя. Также нельзя без предусмотренного договором согласования передавать права на автомобиль третьим лицам, сдавать его в субаренду или использовать в качестве залога.</p>
<p>После оформления автомобиля в вашу собственность вы уже становитесь его полноправным владельцем.</p>

<h2>⚠️ Что будет, если перестать вносить платежи?</h2>
<p>Аренда с выкупом предполагает соблюдение установленного графика. При возникновении просрочки могут применяться предусмотренные договором пени и другие последствия. Если платежи не вносятся в установленные договором сроки, договор может быть расторгнут, а автомобиль потребуется вернуть Арендодателю.</p>
<p>Поэтому, если возникли сложности с очередным платежом, лучше не игнорировать ситуацию и заранее связаться с Драйв Лизинг.</p>

<h2>🔄 Что происходит при досрочном расторжении договора?</h2>
<p>Если договор прекращается до выполнения условий выкупа, автомобиль автоматически не становится собственностью Арендатора. При прекращении договора автомобиль необходимо вернуть Арендодателю в предусмотренном договором порядке.</p>
<p>Именно поэтому перед оформлением аренды с выкупом важно заранее ознакомиться с условиями, графиком платежей и своими обязательствами.</p>

<h2>🔢 Останутся ли старые номера после перехода автомобиля в собственность?</h2>
<p><strong>Не обязательно.</strong> Условиями Драйв Лизинг предусмотрено, что Арендодатель может распоряжаться государственными регистрационными номерами автомобиля и при необходимости оставить их за собой. Поэтому при переоформлении автомобиля государственный номер может измениться.</p>

<h2>📋 Какие документы оформляются при передаче автомобиля?</h2>
<p>При начале пользования автомобилем оформляется комплект документов, предусмотренный договором. В частности:</p>
<ul class="dl-content-page__facts">
<li>✔️ договор</li>
<li>✔️ акт приёма-передачи автомобиля</li>
<li>✔️ акт передачи необходимых документов и ключей</li>
<li>✔️ платёжная ведомость</li>
<li>✔️ другие документы и дополнительные соглашения, предусмотренные конкретной сделкой</li>
</ul>
<p>Это позволяет зафиксировать условия программы, состояние автомобиля на момент передачи и порядок дальнейших платежей.</p>

<h2>❓ Частые вопросы</h2>
''' + render_faq_block(FAQ_ITEMS) + '''

<h2>От аренды до собственного автомобиля 🚗➡️🏠</h2>
<p>В Драйв Лизинг путь к своему автомобилю выглядит понятно:</p>
<p class="dl-content-page__formula">Выбираете автомобиль → оформляете договор → получаете машину → пользуетесь автомобилем → платите по графику → выполняете условия договора → автомобиль оформляется в вашу собственность.</p>
<p>Вы начинаете пользоваться автомобилем уже после его передачи, а затем постепенно проходите путь к его оформлению в собственность. Все основные условия, срок, платежи, автомобиль и обязательства сторон фиксируются документально.</p>'''

# Статьи блога: (slug, заголовок, короткое описание для карточки, дата публикации).
# Список специально отдельный от content_pages ниже — страницы аренда-с-выкупом/
# лизинг-юрлицам это сервисные лендинги, а не статьи, в блоге им не место.
BLOG_ARTICLES = [
    ('kupit-ili-arenda-s-vykupom', 'Автокредит или аренда с выкупом: что выгоднее?',
     'Не сравниваем ставку банка с нашим коэффициентом — считаем, сколько денег реально уйдёт из кармана за автомобиль в каждом варианте.',
     '28 сентября 2026'),
    ('kogda-avto-stanet-vashim', 'Когда автомобиль становится вашим при аренде с выкупом?',
     'Что нужно выполнить по договору, какие документы оформляются и что будет, если перестать платить или расторгнуть договор досрочно.',
     '1 октября 2026'),
]

def render_blog_list(articles):
    cards = ''.join(
        f'<a class="dl-blog-card" href="../{slug}/">'
        f'<span class="dl-blog-card__date">{html.escape(date)}</span>'
        f'<h2 class="dl-blog-card__title">{html.escape(title)}</h2>'
        f'<p class="dl-blog-card__excerpt">{html.escape(excerpt)}</p>'
        f'<span class="dl-blog-card__link">Читать статью →</span>'
        f'</a>'
        for slug, title, excerpt, date in articles
    )
    return f'<div class="dl-blog-list">{cards}</div><p style="margin-top:24px;">Короткие ответы без сплошного текста — в разделе <a href="../faq/">«Вопросы и ответы»</a>.</p>'

CATNAV_STYLE = '''<style>
.dl-catnav{background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:42;}
.dl-catnav__inner{max-width:1180px;margin:0 auto;padding:10px 24px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;}
.dl-catnav__item{position:relative;}
.dl-catnav__trigger{display:flex;align-items:center;gap:6px;padding:10px 18px;border:none;border-radius:999px;background:none;font-family:'Onest',Arial,sans-serif;font-size:14px;font-weight:600;color:var(--navy);cursor:pointer;transition:background .15s,color .15s;}
.dl-catnav__trigger:hover{background:var(--surface-page);color:var(--blue);}
.dl-catnav__item.is-open .dl-catnav__trigger,
.dl-catnav__item--active .dl-catnav__trigger{background:var(--blue);color:#fff;}
.dl-catnav__chevron{width:14px;height:14px;flex:none;transition:transform .15s;}
.dl-catnav__item.is-open .dl-catnav__chevron{transform:rotate(180deg);}
.dl-catnav__panel{display:none;position:absolute;top:100%;left:0;background:var(--surface);border:1px solid var(--border-strong);border-radius:12px;box-shadow:0 10px 30px rgba(15,30,59,.12);padding:14px;z-index:50;}
.dl-catnav__item.is-open .dl-catnav__panel{display:flex;}
.dl-catnav__panel--catalog{flex-direction:column;width:480px;gap:2px;}
.dl-catnav__panel-link{display:block;padding:9px 10px;border-radius:8px;color:#0F1E2E;font-size:14px;font-weight:700;text-decoration:none;}
.dl-catnav__panel-link:hover{background:var(--surface-tint);color:var(--blue);}
.dl-catnav__submenu{position:relative;}
.dl-catnav__submenu-trigger{display:flex;align-items:center;justify-content:space-between;width:100%;border:none;background:none;text-align:left;font-family:inherit;cursor:pointer;}
.dl-catnav__submenu-trigger::after{content:'';flex:none;margin-left:10px;border-style:solid;border-width:4px 0 4px 5px;border-color:transparent transparent transparent var(--muted);}
.dl-catnav__flyout{display:none;position:absolute;left:100%;top:0;margin-left:6px;background:var(--surface);border:1px solid var(--border-strong);border-radius:12px;box-shadow:0 10px 30px rgba(15,30,59,.12);padding:10px;z-index:60;}
.dl-catnav__submenu.is-open > .dl-catnav__flyout{display:block;}
.dl-catnav__flyout--menu{width:200px;}
.dl-catnav__flyout--menu > .dl-catnav__submenu{position:static;}
.dl-catnav__flyout--tags{display:flex;flex-wrap:wrap;gap:6px;width:320px;}
.dl-catnav__group-links a{display:inline-block;padding:6px 12px;border-radius:999px;background:var(--surface-page);color:var(--navy);font-size:13px;font-weight:600;text-decoration:none;white-space:nowrap;}
.dl-catnav__group-links a:hover{background:var(--blue);color:#fff;}
.dl-catnav__panel--list{flex-direction:column;width:240px;gap:2px;}
.dl-catnav__panel--list a{display:block;padding:9px 10px;border-radius:8px;color:var(--navy);font-size:13.5px;font-weight:600;text-decoration:none;white-space:nowrap;}
.dl-catnav__panel--list a:hover{background:var(--surface-tint);color:var(--blue);}
.dl-catnav__link{padding:10px 18px;border-radius:999px;font-family:'Onest',Arial,sans-serif;font-size:14px;font-weight:600;color:var(--navy);text-decoration:none;transition:background .15s,color .15s;}
.dl-catnav__link:hover{background:var(--surface-page);color:var(--blue);}
.dl-catnav__link--active{background:var(--blue);color:#fff;}
.dl-catnav__link--active:hover{background:var(--blue-dark);color:#fff;}
@media (max-width:640px){
  .dl-catnav__inner{padding:6px 16px;overflow-x:auto;scrollbar-width:none;flex-wrap:nowrap;}
  .dl-catnav__inner::-webkit-scrollbar{display:none;}
  .dl-catnav__item{flex:none;}
  .dl-catnav__trigger,.dl-catnav__link{padding:12px 10px;font-size:13px;white-space:nowrap;flex:none;}
  .dl-catnav__panel{position:fixed;left:16px;right:16px;width:auto !important;max-height:70vh;overflow-y:auto;}
  .dl-catnav__flyout{position:static;margin:6px 0 6px 14px;box-shadow:none;border:none;padding:0;width:auto!important;}
}
</style>'''

CATNAV_SCRIPT = '''<script>
(function(){
  var CLOSE_DELAY = 300;
  function armClose(el, fn){
    clearTimeout(el._dlCloseTimer);
    el._dlCloseTimer = setTimeout(fn, CLOSE_DELAY);
  }
  function cancelClose(el){
    clearTimeout(el._dlCloseTimer);
  }
  // Шапка (лого+слоган) прилипает к верху сама по себе (.dl-topbar). Чтобы
  // строка навигации ехала вместе с ней, а не уезжала под неё при скролле,
  // тоже делаем её sticky и ставим top точно под высоту шапки -- без этого
  // обе sticky-полосы встанут в одну точку top:0 и наедут друг на друга.
  function syncCatnavOffset(){
    var topbar = document.querySelector('.dl-topbar');
    var bar = document.querySelector('.dl-catnav');
    if (!topbar || !bar) return;
    bar.style.top = topbar.getBoundingClientRect().height + 'px';
  }
  syncCatnavOffset();
  window.addEventListener('resize', syncCatnavOffset);
  // На мобильной ширине панель становится position:fixed (чтобы не резаться
  // горизонтальным скроллом строки навигации), поэтому top:100% из CSS больше
  // не значит "под кнопкой", а значит "100% высоты экрана" -- панель рисуется
  // за нижним краем viewport. Ставим top явно под нижнюю границу самой панели.
  function positionMobilePanel(item){
    if (window.innerWidth > 640) return;
    var panel = item.querySelector(':scope > .dl-catnav__panel');
    var bar = item.closest('.dl-catnav');
    if (!panel || !bar) return;
    panel.style.top = bar.getBoundingClientRect().bottom + 'px';
  }
  function closeItem(item){
    item.classList.remove('is-open');
    var panel = item.querySelector(':scope > .dl-catnav__panel');
    if (panel) panel.style.top = '';
  }
  var items = document.querySelectorAll('.dl-catnav__item');
  items.forEach(function(item){
    var trigger = item.querySelector('.dl-catnav__trigger');
    if (!trigger) return;
    trigger.addEventListener('click', function(e){
      e.stopPropagation();
      var wasOpen = item.classList.contains('is-open');
      items.forEach(closeItem);
      if (!wasOpen) { item.classList.add('is-open'); positionMobilePanel(item); }
    });
    item.addEventListener('mouseenter', function(){
      cancelClose(item);
      items.forEach(function(i){ if (i !== item) closeItem(i); });
      item.classList.add('is-open');
      positionMobilePanel(item);
    });
    item.addEventListener('mouseleave', function(){
      armClose(item, function(){
        closeItem(item);
        item.querySelectorAll('.dl-catnav__submenu.is-open').forEach(function(s){ s.classList.remove('is-open'); });
      });
    });
  });
  var subs = document.querySelectorAll('.dl-catnav__submenu');
  function subFlyout(sub){
    return sub.querySelector(':scope > .dl-catnav__flyout');
  }
  function setSubOpen(sub, open){
    var flyout = subFlyout(sub);
    if (open) {
      sub.classList.add('is-open');
      if (flyout) {
        flyout.style.display = 'none';
        void flyout.offsetHeight;
        flyout.style.display = 'block';
      }
    } else {
      sub.classList.remove('is-open');
      if (flyout) flyout.style.display = 'none';
    }
  }
  function closeOthers(sub){
    subs.forEach(function(other){
      if (other === sub || other.contains(sub)) return;
      cancelClose(other);
      setSubOpen(other, false);
    });
  }
  function cancelAncestorCloses(el){
    var p = el.parentElement;
    while (p) {
      if (p.classList && (p.classList.contains('dl-catnav__submenu') || p.classList.contains('dl-catnav__item'))) {
        cancelClose(p);
      }
      p = p.parentElement;
    }
  }
  subs.forEach(function(sub){
    var trigger = sub.querySelector(':scope > .dl-catnav__submenu-trigger');
    if (!trigger) return;
    trigger.addEventListener('click', function(e){
      e.stopPropagation();
      var wasOpen = sub.classList.contains('is-open');
      closeOthers(sub);
      setSubOpen(sub, !wasOpen);
    });
    sub.addEventListener('mouseenter', function(){
      cancelClose(sub);
      cancelAncestorCloses(sub);
      closeOthers(sub);
      setSubOpen(sub, true);
    });
    sub.addEventListener('mouseleave', function(){
      armClose(sub, function(){
        setSubOpen(sub, false);
        sub.querySelectorAll('.dl-catnav__submenu.is-open').forEach(function(s){ setSubOpen(s, false); });
      });
    });
  });
  document.addEventListener('click', function(){
    items.forEach(closeItem);
    subs.forEach(function(s){ s.classList.remove('is-open'); });
  });
})();
</script>'''

def render_catnav(brand_links, kuzov_links, base, active=None):
    """base: '' на index.html (корень), '' на catalog.html тоже (сам в корне) —
    оставлен параметром на случай появления вложенных страниц с этим меню.
    active: 'home' на index.html, 'catalog' на catalog.html — подсвечивает синим
    пилюлю текущего раздела, как постоянный индикатор "вы здесь" (не только hover)."""
    chevron = '<svg class="dl-catnav__chevron" viewBox="0 0 24 24" fill="none"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    home_cls = ' dl-catnav__link--active' if active == 'home' else ''
    catalog_cls = ' dl-catnav__item--active' if active == 'catalog' else ''
    return f'''{CATNAV_STYLE}
<nav class="dl-catnav">
  <div class="dl-catnav__inner">
    <a class="dl-catnav__link{home_cls}" href="{base}index.html">Главная</a>
    <div class="dl-catnav__item{catalog_cls}">
      <button class="dl-catnav__trigger" type="button">Каталог{chevron}</button>
      <div class="dl-catnav__panel dl-catnav__panel--catalog">
        <a class="dl-catnav__panel-link" href="{base}catalog.html">Каталог автомобилей</a>
        <div class="dl-catnav__submenu">
          <button class="dl-catnav__panel-link dl-catnav__submenu-trigger" type="button">Поиск по автомобилю</button>
          <div class="dl-catnav__flyout dl-catnav__flyout--menu">
            <div class="dl-catnav__submenu">
              <button class="dl-catnav__panel-link dl-catnav__submenu-trigger" type="button">По марке</button>
              <div class="dl-catnav__flyout dl-catnav__flyout--tags dl-catnav__group-links">{brand_links}</div>
            </div>
            <div class="dl-catnav__submenu">
              <button class="dl-catnav__panel-link dl-catnav__submenu-trigger" type="button">По кузову</button>
              <div class="dl-catnav__flyout dl-catnav__flyout--tags dl-catnav__group-links">{kuzov_links}</div>
            </div>
          </div>
        </div>
        <a class="dl-catnav__panel-link" href="{base}arenda-s-vykupom/">Условия аренды авто с выкупом</a>
        <a class="dl-catnav__panel-link" href="{base}faq/">Частые вопросы</a>
      </div>
    </div>
    <div class="dl-catnav__item">
      <button class="dl-catnav__trigger" type="button">Лизинг{chevron}</button>
      <div class="dl-catnav__panel dl-catnav__panel--list">
        <a href="{base}arenda-s-vykupom/">Лизинг для физ. лиц</a>
        <a href="{base}lizing-yurlicam/">Лизинг для юр. лиц</a>
      </div>
    </div>
    <div class="dl-catnav__item">
      <button class="dl-catnav__trigger" type="button">Компания{chevron}</button>
      <div class="dl-catnav__panel dl-catnav__panel--list">
        <a href="{base}o-kompanii/">О компании</a>
        <a href="{base}blog/">Блог</a>
        <a href="#footer-reviews">Отзывы</a>
      </div>
    </div>
    <a class="dl-catnav__link" href="{base}contacts/">Контакты</a>
  </div>
</nav>
{CATNAV_SCRIPT}'''

def build_catnav_links(cars, brand_slugs, kuzov_slugs):
    """brand_links/kuzov_links (HTML <a> списки для "Поиск по автомобилю") — общие
    для index.html/catalog.html и для всех остальных страниц (машины/марки/кузова/
    статьи), поэтому считаются один раз в main() и просто передаются дальше с
    нужным base на каждой странице."""
    brands_present = sorted(brand_slugs.keys())
    kuzov_present = [k for k in KUZOV_LABELS if any((c.get('kuzov') or '').strip() == k for c in cars)]
    brand_links = ''.join(
        f'<a href="{{base}}marki/{brand_slugs[m]}/">{html.escape(m)}</a>' for m in brands_present
    )
    kuzov_links = ''.join(
        f'<a href="{{base}}kuzov/{kuzov_slugs[k]}/">{html.escape(KUZOV_LABELS[k])}</a>' for k in kuzov_present
    )
    return brand_links, kuzov_links

def write_brand_links(cars, brand_slugs, kuzov_slugs, brand_links_tpl, kuzov_links_tpl):
    """Пишет объединённое меню (Каталог/Лизинг/Компания/Контакты) между маркерами в catalog.html
    и index.html. Раскрывается по наведению (и по клику — для тачскринов). "Каталог" — вертикальный
    список (Каталог автомобилей / Поиск по автомобилю — марка+кузов / Условия аренды с выкупом /
    Частые вопросы); цены/источник (автопарк vs с салона) убраны отсюда намеренно — это дублировало
    фильтры, которые и так есть прямо на странице каталога. "Лизинг" — дропдаун на две существующие
    страницы: физ. лица (arenda-s-vykupom/) и юр. лица (lizing-yurlicam/).
    Компания → О компании/Блог (реальные страницы) и Отзывы (якорь на подвал — отдельной
    страницы с отзывами пока нет). Контакты — реальная страница /contacts/.
    Марки/кузов — чистая навигация на другие страницы, поэтому вынесены из живого
    #dlTabs (там остаются только реальные фильтры — автопарк/с салона, цена/неделю)."""
    brand_links = brand_links_tpl.format(base='')
    kuzov_links = kuzov_links_tpl.format(base='')
    index_block = render_catnav(brand_links, kuzov_links, base='', active='home')
    catalog_block = render_catnav(brand_links, kuzov_links, base='', active='catalog')

    for path, block in ((CATALOG_HTML, catalog_block), (INDEX_HTML, index_block)):
        text = open(path, encoding='utf-8').read()
        new_text, n = re.subn(
            r'<!-- BRAND_LINKS_START -->.*?<!-- BRAND_LINKS_END -->',
            f'<!-- BRAND_LINKS_START -->\n{block}\n<!-- BRAND_LINKS_END -->',
            text, count=1, flags=re.S,
        )
        if n != 1:
            raise RuntimeError(f'Не нашёл <!-- BRAND_LINKS_START/END --> в {os.path.basename(path)}')
        if new_text != text:
            open(path, 'w', encoding='utf-8').write(new_text)
            print(f"{os.path.basename(path)}: {len(brands_present)} марок и {len(kuzov_present)} типов кузова обновлено")

def photo_rel(p):
    """Путь к фото для car-page HTML (относительно cars/<slug>/). Абсолютные URL (сторонние стоковые фото) не трогаем — иначе '../../' ломает ссылку."""
    return p if p.startswith('http') else f"../../{p}"

def photo_abs(p):
    """Абсолютный URL фото для og:image / schema.org."""
    return p if p.startswith('http') else f"{SITE_URL}/{p}"

def render_gallery(photos, title):
    if not photos:
        return '<div class="dl-gallery__empty">Фото уточняйте у менеджера</div>'
    slides = "".join(
        f'<div class="dl-gallery__slide"><img src="{photo_rel(p)}" alt="{html.escape(title)}, фото {i+1}" loading="{"eager" if i==0 else "lazy"}"></div>'
        for i, p in enumerate(photos)
    )
    dots = "".join(f'<button class="dl-gallery__dot{" is-active" if i==0 else ""}" data-i="{i}" aria-label="Фото {i+1}"></button>' for i in range(len(photos)))
    return f'''<div class="dl-gallery" data-count="{len(photos)}">
    <div class="dl-gallery__track">{slides}</div>
    <button class="dl-gallery__nav is-prev" aria-label="Предыдущее фото"><svg viewBox="0 0 24 24" fill="none"><path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
    <button class="dl-gallery__nav is-next" aria-label="Следующее фото"><svg viewBox="0 0 24 24" fill="none"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
    <div class="dl-gallery__dots">{dots}</div>
    <div class="dl-gallery__count">1 / {len(photos)}</div>
    <button class="dl-gallery__expand" type="button" aria-label="Открыть на весь экран"><svg viewBox="0 0 24 24" fill="none"><path d="M9 3H5a2 2 0 00-2 2v4M15 3h4a2 2 0 012 2v4M9 21H5a2 2 0 01-2-2v-4M15 21h4a2 2 0 002-2v-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
  </div>'''

def render_thumbs(photos, title):
    if not photos or len(photos) < 2:
        return ''
    thumbs = "".join(
        f'<button class="dl-thumb{" is-active" if i==0 else ""}" data-i="{i}"><img src="{photo_rel(p)}" alt="{html.escape(title)}, миниатюра {i+1}" loading="lazy"></button>'
        for i, p in enumerate(photos)
    )
    return f'<div class="dl-thumbs">{thumbs}</div>'

SPEC_ICONS = {
    "Год выпуска": "calendar",
    "Пробег": "speedometer",
    "Цвет": "droplet",
    "Двигатель": "gear",
    "Тип кузова": "car2",
}

def render_specs(spec_d, year):
    rows = []
    if year: rows.append(("Год выпуска", str(year)))
    if spec_d['mileage']: rows.append(("Пробег", spec_d['mileage']))
    if spec_d['color']: rows.append(("Цвет", spec_d['color']))
    if spec_d['engine']: rows.append(("Двигатель", spec_d['engine']))
    if spec_d['body']: rows.append(("Тип кузова", spec_d['body']))
    cells = "".join(
        f'<div class="dl-specs__cell"><span class="dl-specs__ico"><img src="../../images/icons3d/{SPEC_ICONS[k]}.png" alt="" loading="lazy"></span>'
        f'<div><span class="dl-specs__val">{html.escape(v)}</span><span class="dl-specs__label">{html.escape(k)}</span></div></div>'
        for k, v in rows
    )
    return f'<div class="dl-specs">{cells}</div>'

def render_komplekt(items):
    lis = "".join(f'<li class="dl-komplekt-list__item"><svg viewBox="0 0 20 20" fill="none"><path d="M5 10.5l3 3 7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>{html.escape(i)}</li>' for i in items)
    return f'<ul class="dl-komplekt-list">{lis}</ul>'

BADGE_ICONS = [
    '<svg viewBox="0 0 24 24" fill="none"><path d="M4 12l5 5L20 6" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none"><path d="M12 2v20M6 6.5c0-1.4 2.2-2.7 6-2.7s6 1.3 6 2.7-2.2 2.7-6 2.7-6 1.3-6 2.7 2.2 2.7 6 2.7 6 1.3 6 2.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="6" width="18" height="14" rx="1.5" stroke="currentColor" stroke-width="1.8"/><path d="M3 10h18M8 6V4.5a1.5 1.5 0 011.5-1.5h5A1.5 1.5 0 0116 4.5V6" stroke="currentColor" stroke-width="1.8"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none"><path d="M12 2.5l7.5 3.3v5.4c0 4.9-3.2 8.2-7.5 10.3-4.3-2.1-7.5-5.4-7.5-10.3V5.8L12 2.5z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
]
BADGE_COLORS = ['blue', 'teal', 'amber', 'violet']

BADGE2_ICONS = [
    '<path d="M12 3l7 3v6c0 5-3 8.5-7 9.5-4-1-7-4.5-7-9.5V6l7-3z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    '<ellipse cx="12" cy="7" rx="6" ry="2.4" stroke="currentColor" stroke-width="1.7"/><path d="M6 7v4c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4V7" stroke="currentColor" stroke-width="1.7"/><path d="M6 11v4c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4v-4" stroke="currentColor" stroke-width="1.7"/>',
    '<rect x="5" y="3" width="14" height="18" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    '<path d="M4 9.5l8-5 8 5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M5 9.5v8.5M9.5 9.5v8.5M14.5 9.5v8.5M19 9.5v8.5" stroke="currentColor" stroke-width="1.7"/><path d="M4 19.5h16" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M4 3.5l16 17" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
]

BADGE_ITEMS = [
    ('92% одобрение', 'Реальные клиенты'),
    ('Взнос от 0%', 'Гибкие условия'),
    ('По 2 документам', 'Быстрое оформление'),
    ('Без банка', 'Решение от нас'),
]

BADGE3_ICON_IMAGES = ['shield', 'coin', 'document', 'bank']

def render_badges2():
    cards = "".join(
        f'<div class="dl-badge3 dl-badge3--{BADGE_COLORS[i]}">'
        f'<span class="dl-badge3__ico"><img src="../../images/icons3d/{BADGE3_ICON_IMAGES[i]}.png" alt="" loading="lazy"></span>'
        f'<div class="dl-badge3__text"><b>{html.escape(t)}</b></div></div>'
        for i, (t, s) in enumerate(BADGE_ITEMS)
    )
    return f'<div class="dl-badges-grid">{cards}</div>'

HERO_HOOKS = [
    "Забирайте уже сегодня, всего по двум документам",
]

HERO_POINT_ICONS = {
    "car": '<path d="M4 16l1.4-5A2 2 0 017.3 9.5h9.4a2 2 0 011.9 1.5L20 16" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M3 16h18v3a1 1 0 01-1 1h-1a1 1 0 01-1-1v-1H6v1a1 1 0 01-1 1H4a1 1 0 01-1-1v-3z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><circle cx="7.5" cy="16" r="1.1" fill="currentColor"/><circle cx="16.5" cy="16" r="1.1" fill="currentColor"/>',
    "document": '<rect x="5" y="3" width="14" height="18" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    "heart": '<path d="M12 20.3c-.3 0-.6-.1-.8-.3C7.2 16.8 3.7 13.7 3.7 9.9 3.7 7.2 5.8 5 8.5 5c1.6 0 3 .8 3.7 2 .7-1.2 2.1-2 3.7-2 2.7 0 4.8 2.2 4.8 4.9 0 3.8-3.5 6.9-7.7 10.1-.2.2-.5.3-.8.3z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
}

HERO_POINTS = [
    ("Проверенные авто", "car"),
    ("Прозрачный договор", "document"),
    ("Поддержка на всех этапах", "heart"),
]

HERO_TAGLINES = [
    "Ближе к новым горизонтам",
    "Ваш путь начинается здесь",
    "Дорога ждёт, машина готова",
]

def render_hero_top_right(car):
    idx = int(hashlib.md5((car['art'] + 'tag').encode()).hexdigest(), 16) % len(HERO_TAGLINES)
    tagline = HERO_TAGLINES[idx]
    return f'''<div class="dl-hero-tagline-block">
    <div class="dl-hero-tagline">{html.escape(tagline)}</div>
  </div>'''

SUBTITLES_BY_BODY = {
    'кроссовер': 'Современный кроссовер для города и путешествий',
    'седан': 'Комфортный седан для города и трассы',
    'хэтчбек': 'Манёвренный хэтчбек для повседневных поездок',
    'минивэн': 'Просторный минивэн для семьи и дальних поездок',
    'универсал': 'Практичный универсал на каждый день',
    'внедорожник': 'Надёжный внедорожник для города и бездорожья',
}

def render_subtitle(spec_d):
    text = SUBTITLES_BY_BODY.get(spec_d.get('body'), 'Надёжный автомобиль для города и путешествий')
    return f'<p class="dl-h1-subtitle">{html.escape(text)}</p>'

def render_hero_banner(car, min_week, slug):
    title = car_title(car)
    idx = int(hashlib.md5(car['art'].encode()).hexdigest(), 16) % len(HERO_HOOKS)
    hook = HERO_HOOKS[idx]
    price_html = f'от <em>{fmt_money(min_week)}</em> в неделю' if min_week is not None else 'цена <em>по запросу</em>'
    points = "".join(
        f'<div class="dl-hero-banner__point"><span class="dl-hero-banner__point-ico"><svg viewBox="0 0 24 24" fill="none">{HERO_POINT_ICONS[icon]}</svg></span><span class="dl-hero-banner__point-text">{html.escape(t)}</span></div>'
        for t, icon in HERO_POINTS
    )
    return f'''<div class="dl-hero-banner">
    <div class="dl-hero-banner__main">
      <h2 class="dl-hero-banner__title">{html.escape(title)}: {price_html}</h2>
      <p class="dl-hero-banner__sub">{html.escape(hook)}</p>
    </div>
    <div class="dl-hero-banner__points">{points}</div>
  </div>'''

DESC_OPENERS = [
    "{title} {year_bit}в нашем автопарке, {body_bit}готов к передаче в лизинг прямо сейчас.",
    "Смотрите {title}{year_bit2}, один из автомобилей, которые уже стоят у нас {body_bit2}и ждут нового пользователя.",
    "{title}{year_bit2}: {body_bit}вариант для тех, кто хочет начать ездить без долгого ожидания.",
]
DESC_SPEC_CLAUSES = [
    "Пробег {mileage}, {color} цвет, двигатель {engine}.",
    "На счётчике {mileage}, кузов {color}, под капотом {engine}.",
    "{mileage} пробега, цвет {color}, мотор {engine}.",
]
DESC_KOMPLEKT_CLAUSES = [
    "Из комплектации сразу отметим: {items}.",
    "В салоне уже есть {items}.",
    "Комплектация включает {items} и другое. Полный список чуть ниже.",
]
DESC_CLOSERS = [
    "Можно приехать и посмотреть машину вживую перед тем, как принимать решение.",
    "Точную доступность на сегодня уточнит менеджер, когда оставите заявку.",
    "Если модель не подойдёт, покажем похожие варианты из наличия.",
]

def render_description(car, spec_d, art_idx_seed):
    title = car_title(car)
    h = int(hashlib.md5(art_idx_seed.encode()).hexdigest(), 16)
    opener = DESC_OPENERS[h % len(DESC_OPENERS)]
    spec_clause = DESC_SPEC_CLAUSES[(h // 7) % len(DESC_SPEC_CLAUSES)]
    komplekt_clause = DESC_KOMPLEKT_CLAUSES[(h // 13) % len(DESC_KOMPLEKT_CLAUSES)]
    closer = DESC_CLOSERS[(h // 29) % len(DESC_CLOSERS)]

    year_bit = f"{car.get('year')} года " if car.get('year') else ""
    year_bit2 = f" {car.get('year')} года" if car.get('year') else ""
    body_bit = f"{spec_d['body']} " if spec_d.get('body') else ""
    body_bit2 = f"({spec_d['body']}) " if spec_d.get('body') else ""

    parts = [opener.format(title=title, year_bit=year_bit, year_bit2=year_bit2, body_bit=body_bit, body_bit2=body_bit2)]
    if spec_d.get('mileage') and spec_d.get('color') and spec_d.get('engine'):
        parts.append(spec_clause.format(mileage=spec_d['mileage'], color=spec_d['color'], engine=spec_d['engine']))
    komplekt = komplekt_items(car.get('komplekt'))
    if komplekt:
        top = ', '.join(komplekt[:3]).lower()
        parts.append(komplekt_clause.format(items=top))
    parts.append(closer)
    return f'<p class="dl-description">{" ".join(parts)}</p>'

REASONS_ITEMS = [
    ("reason-shield", "Даже если банк отказал", "Не ограничиваемся банковским решением. Рассматриваем вашу ситуацию и подбираем доступный вариант получения автомобиля."),
    ("reason-doc-car", "Подбираем не только авто, но и решение", "Аренда с выкупом, лизинг и другие варианты оформления: подберём оптимальный вариант под вашу ситуацию."),
    ("reason-car", "Большой выбор автомобилей", "Автомобили в наличии у нас и проверенных партнёров. Если нужного варианта нет, поможем подобрать другой."),
    ("reason-briefcase", "Для себя, работы и бизнеса", "Работаем с физлицами, ИП и компаниями. Подберём автомобиль для личных поездок, работы или бизнеса."),
]

def render_reasons():
    items = "".join(
        f'<div class="dl-reasons__card"><div class="dl-reasons__ico"><img src="../../images/icons3d/{icon}.png" alt="" loading="lazy"></div>'
        f'<div class="dl-reasons__title">{html.escape(t)}</div><div class="dl-reasons__text">{html.escape(d)}</div></div>'
        for icon, t, d in REASONS_ITEMS
    )
    return f'''<div class="dl-reasons">
    <h2 class="dl-reasons__heading">Почему обращаются<br><span>в Драйв Лизинг</span></h2>
    <p class="dl-reasons__sub">Мы не просто выдаём автомобили, мы находим решение для вашей ситуации.</p>
    <div class="dl-reasons__grid">{items}</div>
  </div>'''

OWN_STEPS = [
    ("Оставляете заявку", "Выбираете машину на сайте или пишете нам, коротко расскажете, что нужно."),
    ("Проверяем допуск", "Три условия: Иркутск или до 250 км от города, гражданство РФ, стаж от 3 лет."),
    ("Подтверждаете документы", "Паспорт и водительское удостоверение. Больше ничего собирать не нужно."),
    ("Подписываем договор", "Фиксируем взнос (от 0%) и срок (12-36 мес), забираете машину."),
    ("Платите по графику", "Раз в неделю или в месяц, как вам удобнее вносить платёж."),
    ("Становитесь владельцем", "После последнего платежа автомобиль переходит в вашу собственность."),
]

OWN_ICONS = [
    '<path d="M21 3L3 10l7 3 3 7 8-17z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M10 13l6-6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    '<path d="M12 21s7-6.1 7-11.5a7 7 0 10-14 0C5 14.9 12 21 12 21z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M9.5 9.5l1.7 1.7 3.3-3.3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
    '<rect x="2.5" y="5.5" width="19" height="13" rx="2" stroke="currentColor" stroke-width="1.7"/><circle cx="8.5" cy="12" r="2" stroke="currentColor" stroke-width="1.5"/><path d="M13 10.5h6M13 13.5h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
    '<path d="M6 3h9l3 3v15H6z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M15 3v3h3" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M9 12h6M9 16h4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    '<rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M3 9.5h18M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="8" cy="14" r="1.3" fill="currentColor"/><circle cx="12" cy="14" r="1.3" fill="currentColor"/><circle cx="16" cy="14" r="1.3" fill="currentColor"/>',
    '<circle cx="8" cy="15" r="4" stroke="currentColor" stroke-width="1.7"/><path d="M11 12l9-9M17 6l2 2M14 9l2 2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
]

STEP_ICON_FILES = ['step1-plane', 'step2-doc-check', 'step3-id-person', 'step4-doc-pencil', 'step5-calendar-clock', 'step6-car-key']

CONDITIONS_ARROW_RIGHT = '<svg class="dl-conditions__connector dl-conditions__connector--h" viewBox="0 0 44 18" fill="none"><path d="M1 9h34" stroke="#8FA0C4" stroke-width="2.5" stroke-dasharray="4.5 4.5" stroke-linecap="round"/><path d="M28 3l8 6-8 6" stroke="#8FA0C4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
CONDITIONS_ARROW_LEFT = '<svg class="dl-conditions__connector dl-conditions__connector--h dl-conditions__connector--h-left" viewBox="0 0 44 18" fill="none"><path d="M1 9h34" stroke="#8FA0C4" stroke-width="2.5" stroke-dasharray="4.5 4.5" stroke-linecap="round"/><path d="M28 3l8 6-8 6" stroke="#8FA0C4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
CONDITIONS_ARROW_DOWN = '<svg class="dl-conditions__connector dl-conditions__connector--v" viewBox="0 0 20 44" fill="none"><path d="M10 1v30" stroke="#8FA0C4" stroke-width="2.5" stroke-dasharray="4.5 4.5" stroke-linecap="round"/><path d="M3 27l7 8 7-8" stroke="#8FA0C4" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'

# Стрелки-коннекторы идут "змейкой": 1-2 вправо, 2-3 вниз, 3-4 влево, 4-5 вниз, 5-6 вправо.
# Визуально это раскладка 1|2 / 4|3 / 5|6 (порядок карточек 3 и 4 меняется местами через CSS order),
# поэтому и вертикальные переходы получаются прямыми, без диагоналей.
CONDITIONS_CONNECTORS = [CONDITIONS_ARROW_RIGHT, CONDITIONS_ARROW_DOWN, CONDITIONS_ARROW_LEFT, CONDITIONS_ARROW_DOWN, CONDITIONS_ARROW_RIGHT, '']

def render_how_to_own():
    rows = "".join(
        f'<div class="dl-conditions__row">'
        f'<div class="dl-conditions__num">{i+1}</div>'
        f'<div class="dl-conditions__ico"><img src="../../images/icons3d/{icon}.png" alt="" loading="lazy"></div>'
        f'<div class="dl-conditions__body"><div class="dl-conditions__title">{html.escape(t)}</div><div class="dl-conditions__text">{html.escape(d)}</div></div>'
        + CONDITIONS_CONNECTORS[i]
        + '</div>'
        for i, (icon, (t, d)) in enumerate(zip(STEP_ICON_FILES, OWN_STEPS))
    )
    return f'''<div class="dl-conditions">
    <h2 class="dl-conditions__heading">Какие <span>условия?</span></h2>
    <p class="dl-conditions__sub">Простой и понятный процесс: от заявки до вашего автомобиля.</p>
    <div class="dl-conditions__list">{rows}</div>
    <div class="dl-conditions__tagline"><span></span>Драйв Лизинг. Пора ехать<span></span></div>
  </div>'''

MAX_CHANNEL_URL = "https://max.ru/id30954831331_biz"
TG_CHANNEL_URL = "https://t.me/drivelizing"

def render_channel_promo():
    return f'''<div class="dl-promo-img">
    <img src="../../images/promo/banner.webp" alt="Узнавайте первыми о новых предложениях: каналы Драйв Лизинг в MAX и Telegram" loading="lazy" width="1983" height="793">
    <a class="dl-promo-img__link dl-promo-img__link--max" href="{MAX_CHANNEL_URL}" target="_blank" rel="noopener" aria-label="Перейти в MAX"></a>
    <a class="dl-promo-img__link dl-promo-img__link--tg" href="{TG_CHANNEL_URL}" target="_blank" rel="noopener" aria-label="Перейти в Telegram"></a>
  </div>'''

TERMS_ICONS = [
    '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M3 9.5h18M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none"><circle cx="7" cy="7" r="3" stroke="currentColor" stroke-width="1.8"/><circle cx="17" cy="17" r="3" stroke="currentColor" stroke-width="1.8"/><path d="M18 6L6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none"><rect x="2.5" y="5.5" width="19" height="13" rx="2" stroke="currentColor" stroke-width="1.8"/><circle cx="8.5" cy="12" r="2" stroke="currentColor" stroke-width="1.6"/><path d="M13 10.5h6M13 13.5h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none"><path d="M4 12a8 8 0 0114-5.3M20 12a8 8 0 01-14 5.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M18 3v4h-4M6 21v-4h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
]

def render_terms(car):
    variants = car.get('variants') or {}
    pv_range = "0-20%"
    if variants:
        keys = sorted(variants.keys(), key=int)
        pv_range = f"{keys[0]}-{keys[-1]}%"
    cells = [
        ("12-36 мес", "Срок договора"),
        (pv_range, "Первоначальный взнос"),
        ("Паспорт + права", "Нужные документы"),
        ("Еженедельно или ежемесячно", "График платежей"),
    ]
    grid = "".join(
        f'<div class="dl-terms__cell"><div class="dl-terms__ico">{TERMS_ICONS[i]}</div>'
        f'<div class="dl-terms__val">{html.escape(v)}</div><div class="dl-terms__label">{html.escape(l)}</div></div>'
        for i, (v, l) in enumerate(cells)
    )
    return f'''<div class="dl-terms">{grid}</div>
  <ul class="dl-eligibility__list" style="margin-top:16px">
    <li><b>Прописка или проживание</b> в Иркутске или в пределах ~250 км от города</li>
    <li><b>Гражданство РФ</b></li>
    <li><b>Стаж вождения от 3 лет</b> (меньше, возможен взнос от 30%)</li>
  </ul>'''

CALC_ICONS = {
    'calculator': '<rect x="5" y="2" width="14" height="20" rx="2" stroke="currentColor" stroke-width="1.6"/><rect x="7.5" y="4.5" width="9" height="4" rx="0.5" stroke="currentColor" stroke-width="1.4"/><circle cx="8.5" cy="12.5" r="1" fill="currentColor"/><circle cx="12" cy="12.5" r="1" fill="currentColor"/><circle cx="15.5" cy="12.5" r="1" fill="currentColor"/><circle cx="8.5" cy="16" r="1" fill="currentColor"/><circle cx="12" cy="16" r="1" fill="currentColor"/><circle cx="15.5" cy="16" r="1" fill="currentColor"/><circle cx="8.5" cy="19.2" r="1" fill="currentColor"/><rect x="11" y="18.2" width="5.5" height="2" rx="1" fill="currentColor"/>',
    'coins': '<ellipse cx="12" cy="7" rx="6" ry="2.3" stroke="currentColor" stroke-width="1.6"/><path d="M6 7v4c0 1.3 2.7 2.3 6 2.3s6-1 6-2.3V7" stroke="currentColor" stroke-width="1.6"/><path d="M6 11v4c0 1.3 2.7 2.3 6 2.3s6-1 6-2.3v-4" stroke="currentColor" stroke-width="1.6"/>',
    'info': '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="8" r="1" fill="currentColor"/><path d="M12 11v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M3 9.5h18M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    'shield-percent': '<path d="M12 3l7 3v6c0 5-3 8.5-7 9.5-4-1-7-4.5-7-9.5V6l7-3z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M9.5 14.5l5-5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="10" cy="10" r="1" fill="currentColor"/><circle cx="14" cy="14" r="1" fill="currentColor"/>',
    'chart': '<path d="M4 20V13M10 20V9M16 20V5M3 20h17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    'wallet': '<rect x="3" y="6" width="18" height="13" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M3 10h18" stroke="currentColor" stroke-width="1.6"/><circle cx="17" cy="14" r="1.3" fill="currentColor"/>',
    'pie': '<circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.6"/><path d="M12 4v8l6 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    'arrow': '<path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    'car': '<path d="M4 16l1.4-5A2 2 0 017.3 9.5h9.4a2 2 0 011.9 1.5L20 16" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M3 16h18v3a1 1 0 01-1 1h-1a1 1 0 01-1-1v-1H6v1a1 1 0 01-1 1H4a1 1 0 01-1-1v-3z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="7.5" cy="16" r="1.1" fill="currentColor"/><circle cx="16.5" cy="16" r="1.1" fill="currentColor"/>',
    'document': '<rect x="5" y="3" width="14" height="18" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    'shield-check': '<path d="M12 3l7 3v6c0 5-3 8.5-7 9.5-4-1-7-4.5-7-9.5V6l7-3z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    'lock': '<rect x="5" y="10" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M8 10V7a4 4 0 018 0v3" stroke="currentColor" stroke-width="1.6"/>',
}
def ci(name):
    return f'<svg viewBox="0 0 24 24" fill="none">{CALC_ICONS[name]}</svg>'

def render_slider(kind, keys, labels_map, suffix):
    n = len(keys)
    # ПВ по умолчанию — минимальный (0%, либо минимальный доступный для этой машины,
    # если 0% нет — например у лизинговых программ). Срок договора — как раньше,
    # максимальный (самый низкий платёж), это отдельная настройка пользователя.
    active_i = 0 if kind == 'pv' else n - 1
    pct = (active_i / (n - 1) * 100) if n > 1 else 0
    labels_html = "".join(
        f'<button type="button" class="dl-slider__label{" is-active" if i == active_i else ""}" data-{kind}="{k}">{labels_map.get(k, k + suffix)}</button>'
        for i, k in enumerate(keys)
    )
    return f'''<div class="dl-slider dl-slider--{kind}" data-slider="{kind}">
        <div class="dl-slider__rail">
          <div class="dl-slider__fill" style="width:{pct:.4f}%"></div>
          <div class="dl-slider__thumb" style="left:{pct:.4f}%"></div>
        </div>
        <div class="dl-slider__labels">{labels_html}</div>
      </div>'''

def render_calculator(car):
    title_attr = html.escape(car_title(car)).replace('"', '&quot;')
    head = f'''<div class="dl-calc-head">
    <div class="dl-calc-head__text">
      <h2 class="dl-h2" style="margin:0">Рассчитайте платёж</h2>
      <p class="dl-calc-head__sub">Подберите условия и узнайте, сколько платить</p>
    </div>
    <div class="dl-calc-head__note">
      <span class="dl-calc-head__note-ico"><img src="../../images/icons3d/calc-icon.png" alt="" loading="lazy"></span>
      <span>Прозрачные условия,<br>без скрытых платежей</span>
    </div>
  </div>'''
    if car.get('isIssued'):
        return f'{head}<div class="dl-calc-unavailable">Этот автомобиль уже выдан клиенту и недоступен для оформления. Посмотрите похожие варианты в каталоге.<a class="dl-btn dl-btn--calc-cta" href="../../catalog.html" style="text-decoration:none;display:flex;align-items:center;justify-content:center;">Смотреть каталог {ci("arrow")}</a></div>'
    variants = car.get('variants')
    if not variants:
        return f'{head}<div class="dl-calc-unavailable">Точная цена уточняется у менеджера. Оставьте заявку, посчитаем индивидуально.<button class="dl-btn dl-btn--calc-cta" type="button" data-art="{car["art"]}" data-car="{title_attr}">Быстрый заказ {ci("arrow")}</button></div>'
    pv_keys = sorted(variants.keys(), key=int)
    last_variant = variants[pv_keys[-1]]
    term_keys = sorted(last_variant['terms'].keys(), key=int)
    pv_slider = render_slider('pv', pv_keys, VARIANT_LABELS, '%')
    term_slider = render_slider('term', term_keys, TERM_LABELS, ' мес')
    lease_note = '<div class="dl-calc-lease-note">Автомобиль по лизинговой программе: суммы ориентировочные, точный расчёт подготовит менеджер.</div>' if car.get('isLeaseProgram') else ''
    return f'''{head}
  <div class="dl-calc" data-car-data='{build_calculator_data(car)}' data-art="{car['art']}" data-car="{title_attr}">
    <div class="dl-field">
      <span class="dl-label dl-label--row">{ci('coins')}Первоначальный взнос</span>
      {pv_slider}
    </div>
    <div class="dl-field">
      <span class="dl-label dl-label--row">{ci('calendar')}Срок договора</span>
      {term_slider}
    </div>
    <div class="dl-result">
      <div class="dl-result__cell"><span class="dl-result__ico">{ci('calendar')}</span><span class="dl-result__num" data-out="day">-</span><span class="dl-result__unit">в день</span></div>
      <div class="dl-result__cell is-main"><span class="dl-result__ico">{ci('chart')}</span><span class="dl-result__num" data-out="week">-</span><span class="dl-result__unit-row"><span class="dl-result__unit">в неделю</span><button type="button" class="dl-hint__btn" aria-label="Как считается сумма за неделю">{ci('info')}</button></span><div class="dl-hint__pop dl-hint__pop--week">Сумма указана за 7 дней, среднее значение. Платёж за конкретную неделю может немного отличаться в зависимости от дат вашего графика.</div></div>
      <div class="dl-result__cell"><span class="dl-result__ico">{ci('wallet')}</span><span class="dl-result__num" data-out="month">-</span><span class="dl-result__unit-row"><span class="dl-result__unit">в месяц</span><button type="button" class="dl-hint__btn" aria-label="Как считается сумма за месяц">{ci('info')}</button></span><div class="dl-hint__pop dl-hint__pop--month">Сумма указана за 30 дней. При оплате календарным месяцем цена меняется в зависимости от количества дней: недостающие или лишние дни распределяются равными долями к платежу.</div></div>
    </div>
    <div class="dl-calc-save" data-out="save-banner" hidden>
      <div class="dl-calc-save__text">
        <b data-out="save-amount">Экономьте 0 ₽</b>
        <span data-out="save-sub">в месяц при большем взносе</span>
      </div>
      <div class="dl-calc-save__ico">%</div>
    </div>
    <div class="dl-pv-sum-row">
      <span class="dl-pv-sum-row__ico"><img src="../../images/icons3d/pie-icon.png" alt="" loading="lazy"></span>
      <div><div class="dl-pv-sum" data-out="pv-sum"></div><div class="dl-pv-sum__note">Окончательные условия уточнит менеджер</div></div>
    </div>
    <button class="dl-btn dl-btn--calc-cta" type="button">Быстрый заказ {ci('arrow')}</button>
  </div>
  <div class="dl-calc-note">
    <b>Вы пока ничего не платите</b>
    <span>Заявка ни к чему не обязывает. Менеджер свяжется и обсудит с вами точные условия бронирования.</span>
  </div>{lease_note}'''

def render_related(car, all_cars, slugs_by_art):
    title_attr = html.escape(car_title(car)).replace('"', '&quot;')
    others = [c for c in all_cars if c['art'] != car['art']]
    # prefer same bucket, then fill with anything else
    same_bucket = [c for c in others if c.get('bucket') == car.get('bucket')]
    pool = same_bucket if len(same_bucket) >= 4 else others
    picked = pool[:8]
    cards = []
    for c in picked:
        slug = slugs_by_art[c['art']]
        photo = c['photos'][0] if c['photos'] else None
        photo_count = len(c.get('photos') or [])
        spec_d = parse_spec(c.get('spec'))
        spec_bits = [str(x) for x in [c.get('year'), spec_d.get('engine'), spec_d.get('mileage')] if x]
        price = None
        try:
            price = min_week_price(c)
        except Exception:
            pass
        img = f'<img src="{photo_rel(photo)}" alt="{html.escape(car_title(c))}" loading="lazy">' if photo else ''
        price_html = f'от <b>{fmt_money(price)}</b> / нед.' if price else 'Цена по запросу'
        count_html = (
            f'<span class="dl-related2__count"><svg viewBox="0 0 24 24" fill="none"><rect x="3" y="6" width="18" height="14" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M8 6l1.5-2h5L16 6" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="12" cy="13" r="3.2" stroke="currentColor" stroke-width="1.8"/></svg>1/{photo_count}</span>'
            if photo_count else ''
        )
        cards.append(f'''<a class="dl-related2__card" href="../{slug}/">
      <div class="dl-related2__art">
        {img}
        <div class="dl-related2__badges"><span class="dl-related2__badge dl-related2__badge--blue">Без банка</span><span class="dl-related2__badge dl-related2__badge--teal">ПВ от 0%</span></div>
        {count_html}
      </div>
      <div class="dl-related2__body">
        <div class="dl-related2__title">{html.escape(car_title(c))}</div>
        <div class="dl-related2__spec">{html.escape(' · '.join(spec_bits))}</div>
        <div class="dl-related2__price">{price_html}</div>
        <div class="dl-related2__more">Подробнее {ci('arrow')}</div>
      </div>
    </a>''')
    return f'''<div class="dl-related2">
    <div class="dl-related2__eyebrow"><span class="dl-related2__eyebrow-dot"></span>В наличии</div>
    <div class="dl-related2__head">
      <div>
        <h2 class="dl-related2__heading">Другие <span>автомобили</span></h2>
        <p class="dl-related2__sub">Подберите вариант под ваш бюджет</p>
      </div>
      <div class="dl-related2__nav">
        <button type="button" class="dl-related2__nav-btn" data-dir="-1" aria-label="Предыдущие"><svg viewBox="0 0 24 24" fill="none"><path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        <button type="button" class="dl-related2__nav-btn" data-dir="1" aria-label="Следующие"><svg viewBox="0 0 24 24" fill="none"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        <a class="dl-related2__viewall" href="../../catalog.html">Смотреть все авто {ci('arrow')}</a>
      </div>
    </div>
    <div class="dl-related2__track">{"".join(cards)}</div>
    <div class="dl-related2__dots"></div>
    <div class="dl-related2__cta">
      <div class="dl-related2__cta-left">
        <div class="dl-related2__cta-car"><img src="../../images/icons3d/cta-car.png" alt="" loading="lazy"></div>
        <span class="dl-related2__cta-check"><svg viewBox="0 0 24 24" fill="none"><path d="M4 12l5 5L20 6" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
        <div class="dl-related2__cta-body">
          <div class="dl-related2__cta-title">Не нашли подходящий вариант?</div>
          <p class="dl-related2__cta-text">Оставьте заявку, подберём автомобиль под ваши параметры.</p>
        </div>
      </div>
      <button type="button" class="dl-btn dl-related2__cta-btn" data-art="{car['art']}" data-car="{title_attr}">Подобрать автомобиль {ci('arrow')}</button>
      <div class="dl-related2__cta-stat"><svg viewBox="0 0 24 24" fill="none"><path d="M16 11a4 4 0 10-4-4M6 11a3 3 0 100-6 3 3 0 000 6z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 20c.6-3.4 3-5.5 6-5.5M14 20c-.4-3.9 2.4-7 7-7" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg><div><b>Более 60</b><span>автомобилей в наличии</span></div></div>
    </div>
  </div>'''

def render_schema(car, url, slug, min_week, marka_slug):
    title = car_title(car)
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": f"{title} в лизинг в Иркутске",
        "image": [photo_abs(p) for p in car['photos'][:5]] if car.get('photos') else [f"{SITE_URL}/logo.png"],
        "description": f"{title}, {car.get('spec') or ''}. Лизинг и аренда с выкупом в Иркутске от Драйв Лизинг.",
        "brand": {"@type": "Brand", "name": car['marka'].strip()},
        "sku": car['art'],
    }
    if min_week is not None:
        data["offers"] = {
            "@type": "Offer",
            "url": url,
            "priceCurrency": "RUB",
            "price": str(min_week),
            "availability": "https://schema.org/OutOfStock" if car.get('isIssued') else "https://schema.org/InStock",
            "areaServed": "Иркутск"
        }
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": f"{SITE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Каталог", "item": f"{SITE_URL}/catalog.html"},
            {"@type": "ListItem", "position": 3, "name": car['marka'].strip(), "item": f"{SITE_URL}/marki/{marka_slug}/"},
            {"@type": "ListItem", "position": 4, "name": car['model'].strip(), "item": url},
        ]
    }
    return (
        f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>\n'
        f'<script type="application/ld+json">{json.dumps(breadcrumb, ensure_ascii=False)}</script>'
    )

FOOTER_HTML = '''<footer class="dl-footer">
  <div class="dl-footer__inner">
    <div class="dl-footer__top">
      <div class="dl-footer__brand">
        <a href="../../" class="dl-footer__logo"><img src="../../images/icons3d/logo-icon-small.webp" alt="Драйв Лизинг"><span class="dl-footer__logo-text"><span class="dl-footer__logo-title">ДРАЙВ</span><span class="dl-footer__logo-sub">ЛИЗИНГ</span></span></a>
        <p class="dl-footer__tagline">Лизинг и аренда автомобилей с выкупом в Иркутске. Без банка, по 2 документам, для физ. и юр. лиц.</p>
        <div class="dl-footer__social">
          <a class="dl-footer__updates" href="https://t.me/drivelizing" target="_blank" rel="noopener">Будьте в курсе наших новостей<svg viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></a>
          <div class="dl-footer__social-icons">
            <a class="dl-footer__social-ico" href="https://t.me/drivelizing" target="_blank" rel="noopener" aria-label="Telegram"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="12" fill="#29A9EB"/><path d="M17.53 7.2L15.4 17.6c-.16.72-.58.9-1.18.56l-3.26-2.4-1.57 1.51c-.17.18-.32.33-.66.33l.24-3.36 6.1-5.51c.27-.24-.06-.37-.41-.13l-7.54 4.75-3.25-1.02c-.7-.22-.72-.7.15-1.04l12.7-4.9c.59-.22 1.1.14.9 1.05z" fill="#fff"/></svg></a>
            <a class="dl-footer__social-ico" href="https://max.ru/id30954831331_biz" target="_blank" rel="noopener" aria-label="MAX"><img src="../../images/icons3d/max-badge.png" alt="MAX"></a>
          </div>
        </div>
      </div>
      <div>
        <div class="dl-footer__col-title">Навигация</div>
        <ul class="dl-footer__list">
          <li><a href="../../catalog.html">Каталог автомобилей</a></li>
          <li><a href="../../o-kompanii/">О компании</a></li>
          <li><a href="../../blog/">Блог</a></li>
          <li><a href="../../faq/">Вопросы и ответы</a></li>
          <li><a href="../../contacts/">Контакты</a></li>
          <li><a href="../../privacy.html">Политика конфиденциальности</a></li>
        </ul>
      </div>
      <div>
        <div class="dl-footer__col-title">Контакты</div>
        <div class="dl-footer__contacts">
          <div class="dl-footer__contact-item">
            <span class="dl-footer__contact-badge"><svg viewBox="0 0 24 24" fill="none"><path d="M6.6 10.8c1.3 2.5 3.1 4.3 5.6 5.6l1.9-1.9c.3-.3.7-.4 1-.2 1 .3 2.1.5 3.2.5.6 0 1 .4 1 1V19c0 .6-.4 1-1 1C10.5 20 4 13.5 4 5.7c0-.6.4-1 1-1h3.2c.6 0 1 .4 1 1 0 1.1.2 2.2.5 3.2.1.4 0 .7-.2 1l-1.9 1.9z" fill="currentColor"/></svg></span>
            <div class="dl-footer__contact-body"><a href="tel:+79950527683">+7 995 052-76-83</a><div class="dl-footer__contact-sub">Ежедневно с 9:00 до 21:00</div></div>
          </div>
          <div class="dl-footer__contact-item">
            <span class="dl-footer__contact-badge"><svg viewBox="0 0 24 24" fill="none"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5A2.5 2.5 0 1112 6.5a2.5 2.5 0 010 5z" fill="currentColor" fill-rule="evenodd" clip-rule="evenodd"/></svg></span>
            <div class="dl-footer__contact-body"><div>г. Иркутск, ул. Байкальская, 208</div><div class="dl-footer__contact-sub">Отдел продаж</div></div>
          </div>
          <div class="dl-footer__contact-item">
            <span class="dl-footer__contact-badge"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="12" fill="#29A9EB"/><path d="M17.53 7.2L15.4 17.6c-.16.72-.58.9-1.18.56l-3.26-2.4-1.57 1.51c-.17.18-.32.33-.66.33l.24-3.36 6.1-5.51c.27-.24-.06-.37-.41-.13l-7.54 4.75-3.25-1.02c-.7-.22-.72-.7.15-1.04l12.7-4.9c.59-.22 1.1.14.9 1.05z" fill="#fff"/></svg></span>
            <div class="dl-footer__contact-body"><a href="https://t.me/avtohere38" target="_blank" rel="noopener">Telegram<div class="dl-footer__contact-sub">Написать нам</div></a></div>
          </div>
          <div class="dl-footer__contact-item">
            <span class="dl-footer__contact-badge"><img src="../../images/icons3d/max-badge.png" alt=""></span>
            <div class="dl-footer__contact-body"><a href="https://max.ru/u/f9LHodD0cOJwdXPtIRKpSznrrNNKwx-l7-HcyIykYTEMu3kGUgp9u4vTgm8" target="_blank" rel="noopener">MAX<div class="dl-footer__contact-sub">Написать нам</div></a></div>
          </div>
        </div>
      </div>
      <div class="dl-footer__promo">
        <div class="dl-footer__promo-text">Уезжайте на новом автомобиле<br><span>уже сегодня</span></div>
        <img src="../../images/icons3d/footer-promo-car.png" alt="">
      </div>
    </div>
    <div class="dl-footer__bottom">
      <span>© 2026 Драйв Лизинг, Иркутск.</span>
      <div class="dl-footer__bottom-right">
        <span>Работаем с физ. и юр. лицами</span>
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 21s-7-4.3-9.5-8.8C.8 8.7 2.3 5 5.8 5c2 0 3.4 1.3 4.2 2.5C10.8 6.3 12.2 5 14.2 5c3.5 0 5 3.7 3.3 7.2C19 16.7 12 21 12 21z"/></svg>
        <span>С заботой о ваших поездках</span>
      </div>
    </div>
  </div>
</footer>'''

COOKIE_BANNER_HTML = '''<div class="dl-cookie-banner" id="dlCookieBanner" hidden>
  <div class="dl-cookie-banner__card">
    <span class="dl-cookie-banner__icon"><svg viewBox="0 0 24 24" fill="none"><path d="M12 2.5l7.5 3v6c0 5.2-3.6 9.7-7.5 11.5-3.9-1.8-7.5-6.3-7.5-11.5v-6l7.5-3z" fill="#2F6FED"/><path d="M8.7 12.3l2.2 2.2 4.4-4.4" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    <div class="dl-cookie-banner__text">
      <b>Мы ценим вашу конфиденциальность</b>
      <p>Сайт использует файлы cookie для анализа трафика и улучшения работы. Продолжая пользоваться сайтом, вы соглашаетесь с нашей <a href="../../privacy.html">политикой конфиденциальности</a>.</p>
    </div>
    <button type="button" class="dl-cookie-banner__btn" id="dlCookieAccept">Принять <svg viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
  </div>
</div>'''

PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{analytics_head}
<title>{title_tag}</title>
<meta name="description" content="{meta_desc}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="product">
<meta property="og:locale" content="ru_RU">
<meta property="og:site_name" content="Драйв Лизинг">
<meta property="og:title" content="{title_tag}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/png" href="../../favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@500;600;700;800&family=Golos+Text:wght@400;500;600;700&family=Caveat:wght@600;700&display=swap">
<link rel="stylesheet" href="../../assets/site.css">
{schema}
</head>
<body>
<div class="dl-topbar">
  <div class="dl-topbar__inner">
    <a href="../../" class="dl-topbar__logo">
      <img src="../../logo-topbar.webp" alt="Драйв Лизинг" class="dl-topbar__logo-img">
      <div class="dl-topbar__logo-text">
        <div class="dl-topbar__slogan">Помогаем получить автомобиль, <em>даже если банк отказал</em></div>
        <div class="dl-topbar__caption">Работаем с физ. и юр. лицами</div>
      </div>
    </a>
  </div>
</div>
{catnav}

<div class="dl-wrap">
  <nav class="dl-breadcrumb" aria-label="Хлебные крошки">
    <a href="../../">Главная</a><span>/</span>
    <a href="../../catalog.html">Каталог</a><span>/</span>
    <a href="../../marki/{marka_slug}/">{marka}</a><span>/</span>
    <span>{model}</span>
  </nav>

  <div class="dl-hero-section">
    <div class="dl-hero-section__inner">
      <h1 class="dl-h1">{title}</h1>
      <p class="dl-h1-sub2">В лизинг и аренду с выкупом в Иркутске</p>
      {subtitle}

      {badges}
    </div>
  </div>

  <div class="dl-detail-grid">
    <div class="dl-detail-main">
      <div class="dl-card__art dl-detail-gallery">{gallery}</div>
      {thumbs}

      {hero_banner}

      <div class="dl-heading"><h2 class="dl-h2" style="margin:0">Характеристики</h2><a class="dl-heading__link" href="#komplekt">Все характеристики<svg viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></a></div>
      {specs}

      <h2 class="dl-h2" id="komplekt">Комплектация</h2>
      {komplekt}

      <h2 class="dl-h2">Описание</h2>
      {description}

      {reasons}
    </div>

    <aside class="dl-detail-side">
      <div class="dl-calc-sticky">
        <div class="dl-card dl-calc-card" id="calc">
          {calculator}
        </div>
        <a class="dl-sample-doc" href="../../documents/dl-sample-agreement.pdf" target="_blank" rel="noopener">
          <span class="dl-sample-doc__ico"><svg viewBox="0 0 24 24" fill="none"><path d="M12 3v12m0 0l-4-4m4 4l4-4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          <span>Скачать образец договора</span>
        </a>
      </div>
    </aside>
  </div>
</div>

<div class="dl-wrap">
  {how_to_own}

  {channel_promo}

  {related}
</div>

{footer}

<div class="dl-modal-backdrop" id="dlModalBackdrop" hidden>
  <div class="dl-modal" id="dlModal"></div>
</div>

<div class="dl-lightbox" id="dlLightbox" hidden>
  <button class="dl-lightbox__close" id="dlLightboxClose" aria-label="Закрыть">&times;</button>
  <button class="dl-lightbox__nav is-prev" id="dlLightboxPrev" aria-label="Предыдущее фото"><svg viewBox="0 0 24 24" fill="none"><path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
  <img class="dl-lightbox__img" id="dlLightboxImg" src="" alt="">
  <button class="dl-lightbox__nav is-next" id="dlLightboxNext" aria-label="Следующее фото"><svg viewBox="0 0 24 24" fill="none"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
  <div class="dl-lightbox__count" id="dlLightboxCount"></div>
</div>

{cookie_banner}

<script src="../../assets/car-page.js"></script>
</body>
</html>
'''

KUZOV_LABELS = {
    'седан': 'Седан', 'кроссовер': 'Кроссовер', 'минивэн': 'Минивэн',
    'универсал': 'Универсал', 'кейкар': 'Кей-кар', 'пикап': 'Пикап', 'фургон': 'Фургон',
}

def main():
    cars = load_cars()
    slugs_by_art = {}
    used = set()
    for c in cars:
        base = slugify(f"{c['marka']}-{c['model']}")
        art_suffix = slugify(c['art'])
        slug = f"{base}-{art_suffix}"
        while slug in used:
            slug += "-2"
        used.add(slug)
        slugs_by_art[c['art']] = slug

    brand_slugs = {m: slugify(m) for m in sorted(set(c['marka'].strip() for c in cars))}
    kuzov_slugs = {k: slugify(k) for k in KUZOV_LABELS}

    write_slugs_to_catalog(cars, slugs_by_art)
    write_catalog_grid(cars, slugs_by_art)
    brand_links_tpl, kuzov_links_tpl = build_catnav_links(cars, brand_slugs, kuzov_slugs)
    write_brand_links(cars, brand_slugs, kuzov_slugs, brand_links_tpl, kuzov_links_tpl)
    catnav_cars2 = render_catnav(brand_links_tpl.format(base='../../'), kuzov_links_tpl.format(base='../../'), base='../../', active='catalog')
    catnav_content1 = render_catnav(brand_links_tpl.format(base='../../'), kuzov_links_tpl.format(base='../../'), base='../../', active=None)

    os.makedirs(CARS_DIR, exist_ok=True)
    urls = []
    for c in cars:
        slug = slugs_by_art[c['art']]
        outdir = os.path.join(CARS_DIR, slug)
        os.makedirs(outdir, exist_ok=True)
        title = car_title(c)
        spec_d = parse_spec(c.get('spec'))
        min_week = min_week_price(c)
        canonical = f"{SITE_URL}/cars/{slug}/"
        og_image = photo_abs(c['photos'][0]) if c.get('photos') else f"{SITE_URL}/logo.png"
        price_bit = f" от {fmt_money(min_week)}/нед" if min_week is not None else ""
        title_tag = f"{title} в лизинг в Иркутске без банка{price_bit} · Драйв Лизинг"
        price_sentence = f" Платёж от {fmt_money(min_week)} в неделю." if min_week is not None else " Точная цена по запросу у менеджера."
        meta_desc = f"{title}, {spec_d['raw']}. Лизинг и аренда с выкупом в Иркутске, взнос от 0%, оформление по 2 документам.{price_sentence}"
        marka_slug = brand_slugs[c['marka'].strip()]
        html_out = PAGE_TEMPLATE.format(
            title_tag=html.escape(title_tag),
            meta_desc=html.escape(meta_desc),
            canonical=canonical,
            og_image=og_image,
            schema=render_schema(c, canonical, slug, min_week, marka_slug),
            marka=html.escape(c['marka'].strip()),
            marka_slug=marka_slug,
            model=html.escape(c['model'].strip()),
            title=html.escape(title),
            title_js=html.escape(title).replace('"','&quot;'),
            badges=render_badges2(),
            hero_banner=render_hero_banner(c, min_week, slug),
            subtitle=render_subtitle(spec_d),
            hero_top_right=render_hero_top_right(c),
            gallery=render_gallery(c['photos'], title),
            thumbs=render_thumbs(c['photos'], title),
            specs=render_specs(spec_d, c.get('year')),
            komplekt=render_komplekt(komplekt_items(c['komplekt'])),
            description=render_description(c, spec_d, c['art']),
            reasons=render_reasons(),
            how_to_own=render_how_to_own(),
            channel_promo=render_channel_promo(),
            calculator=render_calculator(c),
            related=render_related(c, cars, slugs_by_art),
            art=html.escape(c['art']),
            footer=FOOTER_HTML,
            cookie_banner=COOKIE_BANNER_HTML,
            analytics_head=ANALYTICS_HEAD,
            catnav=catnav_cars2,
        )
        with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_out)
        urls.append(canonical)

    # Лендинги по маркам
    listing_urls = []
    MARKI_DIR = os.path.join(BASE_DIR, "marki")
    for marka, mslug in sorted(brand_slugs.items()):
        subset = [c for c in cars if c['marka'].strip() == marka]
        outdir = os.path.join(MARKI_DIR, mslug)
        os.makedirs(outdir, exist_ok=True)
        canonical = f"{SITE_URL}/marki/{mslug}/"
        n = len(subset)
        noun = plural_ru(n, 'автомобиль', 'автомобиля', 'автомобилей')
        html_out = render_listing_page(
            h1=f"{marka} в лизинг и аренду с выкупом в Иркутске",
            title_tag=f"{marka} в лизинг и аренду с выкупом в Иркутске · Драйв Лизинг",
            meta_desc=f"{marka} в лизинг и аренду с выкупом в Иркутске. {n} {noun} {marka} в наличии и под заказ, взнос от 0%, оформление по 2 документам, без банка.",
            intro=f"{n} {noun} {marka} в наличии и под заказ. Взнос от 0%, оформление по 2 документам, без банка — те же условия, что и на весь каталог.",
            crumb_name=marka,
            canonical=canonical,
            cars_subset=subset,
            slugs_by_art=slugs_by_art,
            total=len(cars),
            catnav=catnav_cars2,
        )
        with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_out)
        listing_urls.append(canonical)

    # Лендинги по типу кузова
    KUZOV_DIR = os.path.join(BASE_DIR, "kuzov")
    for kuzov_key, klabel in KUZOV_LABELS.items():
        subset = [c for c in cars if (c.get('kuzov') or '').strip() == kuzov_key]
        if not subset:
            continue
        kslug = kuzov_slugs[kuzov_key]
        outdir = os.path.join(KUZOV_DIR, kslug)
        os.makedirs(outdir, exist_ok=True)
        canonical = f"{SITE_URL}/kuzov/{kslug}/"
        n = len(subset)
        noun = plural_ru(n, 'автомобиль', 'автомобиля', 'автомобилей')
        klabel_lower = klabel[0].lower() + klabel[1:]
        html_out = render_listing_page(
            h1=f"{klabel} в лизинг и аренду с выкупом в Иркутске",
            title_tag=f"{klabel} в лизинг и аренду с выкупом в Иркутске · Драйв Лизинг",
            meta_desc=f"{klabel} в лизинг и аренду с выкупом в Иркутске. {n} {noun} этого типа кузова в наличии и под заказ, взнос от 0%, оформление по 2 документам, без банка.",
            intro=f"{n} {noun} типа «{klabel_lower}» в наличии и под заказ. Взнос от 0%, оформление по 2 документам, без банка — те же условия, что и на весь каталог.",
            crumb_name=klabel,
            canonical=canonical,
            cars_subset=subset,
            slugs_by_art=slugs_by_art,
            total=len(cars),
            catnav=catnav_cars2,
        )
        with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_out)
        listing_urls.append(canonical)

    # Отдельные страницы "аренда с выкупом" / "лизинг юрлицам" (были аккордеоном
    # у подвала — вынесены в полноценные страницы под свои интенты и URL)
    content_pages = [
        ('arenda-s-vykupom', 'Аренда с выкупом', 'Аренда авто с выкупом в Иркутске',
         'Аренда авто с выкупом в Иркутске без банка · Драйв Лизинг',
         'Аренда автомобиля с правом выкупа в Иркутске: без банка, взнос от 0%, оформление по 2 документам. Как считается платёж и что нужно для оформления.',
         'Для частных лиц: получаете автомобиль без банка и кредитной истории, платите по графику, по итогу машина ваша.',
         COMING_SOON_BODY),
        ('lizing-yurlicam', 'Лизинг юрлицам', 'Лизинг автомобилей для юридических лиц в Иркутске',
         'Лизинг для юридических лиц в Иркутске · Драйв Лизинг',
         'Лизинг автомобилей для ООО и ИП в Иркутске: без банка, взнос от 0%, срок до 60 месяцев. Обновление корпоративного автопарка без разовой крупной траты.',
         'Для компаний: обновляете или расширяете автопарк без банка и без разовой крупной траты, платёж относится на расходы.',
         COMING_SOON_BODY),
        ('kupit-ili-arenda-s-vykupom', 'Автокредит или аренда', 'Автокредит или аренда с выкупом: что выгоднее?',
         'Автокредит или аренда с выкупом: что выгоднее в Иркутске · Драйв Лизинг',
         'Считаем все расходы: взнос, платежи по кредиту, ОСАГО, КАСКО — и сравниваем с итоговой суммой по аренде с выкупом на реальном примере автомобиля за 1 500 000 ₽. 92% одобрений, без банка.',
         'Не сравниваем ставку банка с нашим коэффициентом — считаем, сколько денег реально уйдёт из кармана за автомобиль в каждом варианте.',
         KUPIT_ILI_ARENDA_BODY),
        ('kogda-avto-stanet-vashim', 'Когда авто станет вашим', 'Когда автомобиль становится вашим при аренде с выкупом?',
         'Когда автомобиль становится вашим при аренде с выкупом · Драйв Лизинг',
         'Что нужно выполнить по договору аренды с выкупом, чтобы автомобиль перешёл в собственность: платежи, документы, штрафы ГИБДД, что будет при просрочке или досрочном расторжении.',
         'После выполнения условий договора и полной оплаты предусмотренных платежей автомобиль оформляется в вашу собственность. Разбираем весь процесс по шагам.',
         KOGDA_AVTO_VASHIM_BODY),
        ('blog', 'Блог', 'Блог Драйв Лизинг',
         'Блог: статьи про аренду с выкупом и лизинг в Иркутске · Драйв Лизинг',
         'Полезные статьи про аренду авто с выкупом и лизинг в Иркутске: сравнение с автокредитом, расчёты, разбор условий.',
         'Разбираем на цифрах, как устроена аренда с выкупом, чем она отличается от автокредита и кому что выгоднее.',
         render_blog_list(BLOG_ARTICLES)),
        ('faq', 'Вопросы и ответы', 'Вопросы и ответы про аренду автомобиля с выкупом',
         'Вопросы и ответы про аренду с выкупом · Драйв Лизинг',
         'Отвечаем на частые вопросы про аренду автомобиля с выкупом в Драйв Лизинг: когда машина переходит в собственность, можно ли её продать или передать другому человеку, что будет при просрочке платежей.',
         'Короткие ответы на вопросы, которые чаще всего задают клиенты об аренде автомобиля с выкупом.',
         render_faq_schema(FAQ_ITEMS) + render_faq_block(FAQ_ITEMS) +
         '<p style="margin-top:20px;">Подробный разбор всего процесса — в статье <a href="../kogda-avto-stanet-vashim/">«Когда автомобиль становится вашим при аренде с выкупом?»</a>.</p>'),
        ('contacts', 'Контакты', 'Контакты Драйв Лизинг в Иркутске',
         'Контакты Драйв Лизинг в Иркутске: адрес, телефон · Драйв Лизинг',
         'Адрес и телефон Драйв Лизинг в Иркутске: ул. Байкальская, 208. Звоните или пишите в Telegram/MAX — поможем подобрать автомобиль и посчитаем условия аренды с выкупом или лизинга.',
         'Телефон, адрес отдела продаж и мессенджеры — самый быстрый способ получить ответ сегодня.',
         CONTACTS_BODY),
        ('o-kompanii', 'О компании', 'О компании Драйв Лизинг',
         'О компании Драйв Лизинг — аренда с выкупом и лизинг в Иркутске',
         'Драйв Лизинг — собственный автопарк 100+ машин в Иркутске, 7 лет на рынке, более 400 отзывов. Аренда с выкупом и лизинг без банка для физ. и юр. лиц.',
         'Кто мы и почему нам можно доверить оформление автомобиля без банка.',
         O_KOMPANII_BODY),
    ]
    banner_slides = render_banner_slides(cars, slugs_by_art)
    for slug, crumb_name, h1, title_tag, meta_desc, lead, body in content_pages:
        outdir = os.path.join(BASE_DIR, slug)
        os.makedirs(outdir, exist_ok=True)
        canonical = f"{SITE_URL}/{slug}/"
        html_out = render_content_page(h1, title_tag, meta_desc, lead, body, crumb_name, canonical, banner_slides, slug, catnav_content1)
        with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_out)
        listing_urls.append(canonical)

    # sitemap (separate file for review, not overwriting the live one yet)
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap.append(f'  <url><loc>{SITE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>')
    sitemap.append(f'  <url><loc>{SITE_URL}/catalog.html</loc><changefreq>daily</changefreq><priority>0.9</priority></url>')
    sitemap.append(f'  <url><loc>{SITE_URL}/privacy.html</loc><changefreq>monthly</changefreq><priority>0.3</priority></url>')
    for u in urls:
        sitemap.append(f'  <url><loc>{u}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>')
    for u in listing_urls:
        sitemap.append(f'  <url><loc>{u}</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>')
    sitemap.append('</urlset>')
    with open(os.path.join(BASE_DIR, "sitemap_generated.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(sitemap))

    print(f"Сгенерировано страниц: {len(cars)}")
    print(f"Лендингов по маркам/кузову: {len(listing_urls)}")
    print(f"Пример: cars/{slugs_by_art[cars[0]['art']]}/index.html")

if __name__ == "__main__":
    main()
