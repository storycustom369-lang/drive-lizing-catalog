#!/usr/bin/env python3
"""
Генератор отдельных страниц под каждую машину из живого каталога (CARS в catalog.html).
Точка А -> Б: превращает JS-модалки внутри одной страницы в реальные краулящиеся URL.

Запуск: python3 generate_cars.py
Результат: cars/<slug>/index.html на каждую машину + обновлённый sitemap.xml (не трогает старый sitemap.xml файл напрямую, пишет sitemap_generated.xml для ручной проверки перед заменой).
"""
import re, json, os, html

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG_HTML = os.path.join(BASE_DIR, "catalog.html")
CARS_DIR = os.path.join(BASE_DIR, "cars")
SITE_URL = "https://driveleasing38.ru"
WORKER_URL = "https://odd-meadow-4208.litaufit.workers.dev"

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

def load_cars():
    text = open(CATALOG_HTML, encoding='utf-8').read()
    m = re.search(r'var CARS = (\[.*?\]);', text, re.S)
    return json.loads(m.group(1))

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

def render_gallery(photos, title):
    if not photos:
        return '<div class="dl-gallery__empty">Фото уточняйте у менеджера</div>'
    slides = "".join(
        f'<div class="dl-gallery__slide"><img src="../../{p}" alt="{html.escape(title)}, фото {i+1}" loading="{"eager" if i==0 else "lazy"}"></div>'
        for i, p in enumerate(photos)
    )
    dots = "".join(f'<button class="dl-gallery__dot{" is-active" if i==0 else ""}" data-i="{i}" aria-label="Фото {i+1}"></button>' for i in range(len(photos)))
    return f'''<div class="dl-gallery" data-count="{len(photos)}">
    <div class="dl-gallery__track">{slides}</div>
    <button class="dl-gallery__nav is-prev" aria-label="Предыдущее фото"><svg viewBox="0 0 24 24" fill="none"><path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
    <button class="dl-gallery__nav is-next" aria-label="Следующее фото"><svg viewBox="0 0 24 24" fill="none"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
    <div class="dl-gallery__dots">{dots}</div>
    <div class="dl-gallery__count">1 / {len(photos)}</div>
  </div>'''

def render_specs(spec_d, year):
    rows = []
    if year: rows.append(("Год выпуска", str(year)))
    if spec_d['mileage']: rows.append(("Пробег", spec_d['mileage']))
    if spec_d['color']: rows.append(("Цвет", spec_d['color']))
    if spec_d['engine']: rows.append(("Двигатель", spec_d['engine']))
    if spec_d['body']: rows.append(("Тип кузова", spec_d['body']))
    cells = "".join(f'<div class="dl-specs__cell"><span class="dl-specs__val">{html.escape(v)}</span><span class="dl-specs__label">{html.escape(k)}</span></div>' for k,v in rows)
    return f'<div class="dl-specs">{cells}</div>'

def render_komplekt(items):
    lis = "".join(f'<li class="dl-komplekt-list__item"><svg viewBox="0 0 20 20" fill="none"><path d="M5 10.5l3 3 7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>{html.escape(i)}</li>' for i in items)
    return f'<ul class="dl-komplekt-list">{lis}</ul>'

def render_calculator(car):
    variants = car.get('variants')
    if not variants:
        return '<div class="dl-calc-unavailable">Точная цена уточняется у менеджера — оставьте заявку, посчитаем индивидуально.<button class="dl-btn dl-btn--calc-cta" type="button">Оставить заявку</button></div>'
    pv_keys = sorted(variants.keys(), key=int)
    first_variant = variants[pv_keys[0]]
    term_keys = sorted(first_variant['terms'].keys(), key=int)
    pv_buttons = "".join(f'<button data-pv="{k}" class="{"is-active" if i==0 else ""}">{VARIANT_LABELS.get(k, k+"%")}</button>' for i,k in enumerate(pv_keys))
    term_buttons = "".join(f'<button data-term="{k}" class="{"is-active" if i==0 else ""}">{TERM_LABELS.get(k, k+" мес")}</button>' for i,k in enumerate(term_keys))
    return f'''<div class="dl-calc" data-car-data='{build_calculator_data(car)}'>
    <div class="dl-field">
      <span class="dl-label">Первоначальный взнос</span>
      <div class="dl-seg dl-seg--pv" style="grid-template-columns:repeat({len(pv_keys)},1fr)">{pv_buttons}</div>
    </div>
    <div class="dl-field">
      <span class="dl-label">Срок договора</span>
      <div class="dl-seg dl-seg--term" style="grid-template-columns:repeat({len(term_keys)},1fr)">{term_buttons}</div>
    </div>
    <div class="dl-result">
      <div class="dl-result__cell"><span class="dl-result__num" data-out="day">-</span><span class="dl-result__unit">в день</span></div>
      <div class="dl-result__cell is-main"><span class="dl-result__num" data-out="week">-</span><span class="dl-result__unit">в неделю</span></div>
      <div class="dl-result__cell"><span class="dl-result__num" data-out="month">-</span><span class="dl-result__unit">в месяц</span></div>
    </div>
    <div class="dl-pv-sum" data-out="pv-sum"></div>
    <button class="dl-btn dl-btn--calc-cta" type="button">Оставить заявку на этот автомобиль</button>
  </div>'''

def render_related(car, all_cars, slugs_by_art):
    others = [c for c in all_cars if c['art'] != car['art']]
    # prefer same bucket, then fill with anything else
    same_bucket = [c for c in others if c.get('bucket') == car.get('bucket')]
    pool = same_bucket if len(same_bucket) >= 4 else others
    picked = pool[:6]
    cards = []
    for c in picked:
        slug = slugs_by_art[c['art']]
        photo = c['photos'][0] if c['photos'] else None
        price = None
        try:
            first_pv = sorted(c['variants'].keys(), key=int)[0]
            first_term = sorted(c['variants'][first_pv]['terms'].keys(), key=int)[0]
            price = c['variants'][first_pv]['terms'][first_term]['week']
        except Exception:
            pass
        img = f'<img src="../../{photo}" alt="{html.escape(car_title(c))}" loading="lazy">' if photo else ''
        price_html = f'<span class="dl-num">{fmt_money(price)}</span><span class="dl-price-week">/нед</span>' if price else ''
        cards.append(f'''<a class="dl-card dl-related__card" href="../{slug}/">
      <div class="dl-card__art">{img}</div>
      <div class="dl-card__body">
        <div class="dl-title">{html.escape(car_title(c))}</div>
        <div class="dl-price-row">{price_html}</div>
      </div>
    </a>''')
    return f'<div class="dl-grid dl-related">{"".join(cards)}</div>'

def render_schema(car, url, slug, min_week):
    title = car_title(car)
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": f"{title} в лизинг в Иркутске",
        "image": [f"{SITE_URL}/{p}" for p in car['photos'][:5]] if car.get('photos') else [f"{SITE_URL}/logo.png"],
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
            "availability": "https://schema.org/InStock",
            "areaServed": "Иркутск"
        }
    return f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'

PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@500;600;700;800&family=Golos+Text:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="../../assets/site.css">
{schema}
</head>
<body>
<div class="dl-topbar">
  <div class="dl-topbar__inner">
    <a href="../../" class="dl-topbar__logo">
      <img src="../../logo.png" alt="Драйв Лизинг" class="dl-topbar__logo-img">
      <div class="dl-topbar__logo-text">
        <div class="dl-topbar__slogan">Уезжайте на новом автомобиле <em>уже сегодня</em></div>
        <div class="dl-topbar__caption">Работаем с физ. и юр. лицами</div>
      </div>
    </a>
  </div>
</div>

<div class="dl-wrap">
  <nav class="dl-breadcrumb" aria-label="Хлебные крошки">
    <a href="../../">Главная</a><span>/</span>
    <a href="../../catalog.html">Каталог</a><span>/</span>
    <a href="../../catalog.html">{marka}</a><span>/</span>
    <span>{model}</span>
  </nav>

  <div class="dl-badges-row">
    <span class="dl-badge">92% одобрение</span>
    <span class="dl-badge">Взнос от 0%</span>
    <span class="dl-badge">По 2 документам</span>
    <span class="dl-badge">Без банка</span>
  </div>

  <h1 class="dl-h1">{title} в лизинг и аренду с выкупом в Иркутске</h1>

  <div class="dl-detail-grid">
    <div class="dl-detail-main">
      <div class="dl-card__art dl-detail-gallery">{gallery}</div>

      <h2 class="dl-h2">Характеристики</h2>
      {specs}

      <h2 class="dl-h2">Комплектация</h2>
      {komplekt}

      <div class="dl-eligibility">
        <h2 class="dl-h2">Условия допуска</h2>
        <ul class="dl-eligibility__list">
          <li><b>Прописка или проживание</b> в Иркутске или в пределах ~250 км от города</li>
          <li><b>Гражданство РФ</b></li>
          <li><b>Стаж вождения от 3 лет</b> (меньше — возможен взнос от 30%)</li>
        </ul>
      </div>
    </div>

    <aside class="dl-detail-side">
      <div class="dl-card dl-calc-card">
        <h2 class="dl-h2" style="margin-top:0">Рассчитайте платёж</h2>
        {calculator}
      </div>
    </aside>
  </div>

  <div class="dl-heading"><h2>Другие машины в наличии</h2></div>
  {related}

  <div class="dl-cta">
    <div class="dl-cta__inner">
      <div class="dl-cta__left">
        <div class="dl-cta__frame">
          <div class="dl-cta__title">Оставьте заявку на {title}</div>
          <p class="dl-cta__text">Менеджер свяжется в течение рабочего дня, уточнит детали и оформит документы.</p>
        </div>
      </div>
      <div class="dl-cta__right">
        <form class="dl-lead-form" data-art="{art}" data-car="{title_js}">
          <div class="dl-form-field"><input class="dl-form-input" type="text" name="name" placeholder="Имя" required></div>
          <div class="dl-form-field"><input class="dl-form-input" type="tel" name="phone" placeholder="Телефон" required></div>
          <button class="dl-btn" type="submit">Отправить заявку</button>
        </form>
      </div>
    </div>
  </div>
</div>

<script src="../../assets/car-page.js"></script>
</body>
</html>
'''

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

    os.makedirs(CARS_DIR, exist_ok=True)
    urls = []
    for c in cars:
        slug = slugs_by_art[c['art']]
        outdir = os.path.join(CARS_DIR, slug)
        os.makedirs(outdir, exist_ok=True)
        title = car_title(c)
        spec_d = parse_spec(c.get('spec'))
        min_week = None
        if c.get('variants'):
            pv_keys = sorted(c['variants'].keys(), key=int)
            term_keys = sorted(c['variants'][pv_keys[0]]['terms'].keys(), key=int)
            min_week = c['variants'][pv_keys[0]]['terms'][term_keys[0]]['week']
        canonical = f"{SITE_URL}/cars/{slug}/"
        og_image = f"{SITE_URL}/{c['photos'][0]}" if c.get('photos') else f"{SITE_URL}/logo.png"
        price_bit = f" от {fmt_money(min_week)}/нед" if min_week is not None else ""
        title_tag = f"{title} в лизинг в Иркутске без банка{price_bit} — Драйв Лизинг"
        price_sentence = f" Платёж от {fmt_money(min_week)} в неделю." if min_week is not None else " Точная цена — по запросу у менеджера."
        meta_desc = f"{title}, {spec_d['raw']}. Лизинг и аренда с выкупом в Иркутске, взнос от 0%, оформление по 2 документам.{price_sentence}"
        html_out = PAGE_TEMPLATE.format(
            title_tag=html.escape(title_tag),
            meta_desc=html.escape(meta_desc),
            canonical=canonical,
            og_image=og_image,
            schema=render_schema(c, canonical, slug, min_week),
            marka=html.escape(c['marka'].strip()),
            model=html.escape(c['model'].strip()),
            title=html.escape(title),
            title_js=html.escape(title).replace('"','&quot;'),
            gallery=render_gallery(c['photos'], title),
            specs=render_specs(spec_d, c.get('year')),
            komplekt=render_komplekt(komplekt_items(c['komplekt'])),
            calculator=render_calculator(c),
            related=render_related(c, cars, slugs_by_art),
            art=html.escape(c['art']),
        )
        with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_out)
        urls.append(canonical)

    # sitemap (separate file for review, not overwriting the live one yet)
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap.append(f'  <url><loc>{SITE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>')
    sitemap.append(f'  <url><loc>{SITE_URL}/catalog.html</loc><changefreq>daily</changefreq><priority>0.9</priority></url>')
    sitemap.append(f'  <url><loc>{SITE_URL}/privacy.html</loc><changefreq>monthly</changefreq><priority>0.3</priority></url>')
    for u in urls:
        sitemap.append(f'  <url><loc>{u}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>')
    sitemap.append('</urlset>')
    with open(os.path.join(BASE_DIR, "sitemap_generated.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(sitemap))

    print(f"Сгенерировано страниц: {len(cars)}")
    print(f"Пример: cars/{slugs_by_art[cars[0]['art']]}/index.html")

if __name__ == "__main__":
    main()
