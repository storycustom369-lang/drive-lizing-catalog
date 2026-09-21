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

def render_thumbs(photos, title):
    if not photos or len(photos) < 2:
        return ''
    thumbs = "".join(
        f'<button class="dl-thumb{" is-active" if i==0 else ""}" data-i="{i}"><img src="../../{p}" alt="{html.escape(title)}, миниатюра {i+1}" loading="lazy"></button>'
        for i, p in enumerate(photos)
    )
    return f'<div class="dl-thumbs">{thumbs}</div>'

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

BADGE_ICONS = [
    '<svg viewBox="0 0 24 24" fill="none"><path d="M4 12l5 5L20 6" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none"><path d="M12 2v20M6 6.5c0-1.4 2.2-2.7 6-2.7s6 1.3 6 2.7-2.2 2.7-6 2.7-6 1.3-6 2.7 2.2 2.7 6 2.7 6 1.3 6 2.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="6" width="18" height="14" rx="1.5" stroke="currentColor" stroke-width="1.8"/><path d="M3 10h18M8 6V4.5a1.5 1.5 0 011.5-1.5h5A1.5 1.5 0 0116 4.5V6" stroke="currentColor" stroke-width="1.8"/></svg>',
    '<svg viewBox="0 0 24 24" fill="none"><path d="M12 2.5l7.5 3.3v5.4c0 4.9-3.2 8.2-7.5 10.3-4.3-2.1-7.5-5.4-7.5-10.3V5.8L12 2.5z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
]
BADGE_COLORS = ['blue', 'teal', 'amber', 'violet']

def render_badges2():
    items = ['92% одобрение', 'Взнос от 0%', 'По 2 документам', 'Без банка']
    chips = "".join(
        f'<span class="dl-badge2 dl-badge2--{BADGE_COLORS[i]}"><span class="dl-badge2__ico">{BADGE_ICONS[i]}</span>{html.escape(t)}</span>'
        for i, t in enumerate(items)
    )
    return f'<div class="dl-badges-row">{chips}</div>'

HERO_HOOKS = [
    "Забирайте на этой неделе, документы за один визит",
    "Оформление в день обращения, без визита в банк",
    "Из наличия, можно посмотреть и забрать сразу",
    "Без справок о доходах и без КАСКО при оформлении",
]

HERO_POINTS = [
    ("Проверенные авто", '<path d="M4 16l4-9h8l4 9" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M2 16h20M6 16v3M18 16v3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M9 10.5l2 2 4-4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'),
    ("Прозрачный договор", '<path d="M6 3h9l3 3v15H6z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M15 3v3h3" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M9 12h6M9 16h6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>'),
    ("Поддержка на всех этапах", '<path d="M4 16l1.4-5A2 2 0 017.3 9.5h9.4a2 2 0 011.9 1.5L20 16" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M3 16h18v3a1 1 0 01-1 1h-1a1 1 0 01-1-1v-1H6v1a1 1 0 01-1 1H4a1 1 0 01-1-1v-3z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><circle cx="7.5" cy="16" r="1.2" fill="currentColor"/><circle cx="16.5" cy="16" r="1.2" fill="currentColor"/>'),
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
        f'<div class="dl-hero-banner__point"><span class="dl-hero-banner__point-ico dl-hero-banner__point-ico--{BADGE_COLORS[i % len(BADGE_COLORS)]}"><svg viewBox="0 0 24 24" fill="none">{icon}</svg></span><span class="dl-hero-banner__point-text">{html.escape(t)}</span></div>'
        for i, (t, icon) in enumerate(HERO_POINTS)
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

def render_location_promo():
    return '''<a class="dl-location-promo" href="https://driveleasing38.ru/" target="_blank" rel="noopener">
    <img src="../../images/site/hero-bg.webp" alt="Озеро Байкал рядом с Иркутском">
    <div class="dl-location-promo__inner">
      <div class="dl-location-promo__badge">
        <svg viewBox="0 0 24 24" fill="none"><path d="M12 21s7-6.1 7-11.5a7 7 0 10-14 0C5 14.9 12 21 12 21z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="12" cy="9.5" r="2.3" stroke="currentColor" stroke-width="1.8"/></svg>
        <div><b>Иркутск</b><span>рядом с Байкалом</span></div>
      </div>
      <div class="dl-location-promo__foot">
        <span>Удобное расположение и живописные маршруты рядом</span>
        <span class="dl-location-promo__arrow"><svg viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
      </div>
    </div>
  </a>'''

WHY_CARDS = [
    ("Без банка и скоринга", "Решение по машине принимаем сами, не банк, поэтому не смотрим кредитную историю и официальный доход."),
    ("Прозрачный расчёт", "Один и тот же коэффициент к цене авто в зависимости от взноса: 2.3 без взноса, 1.8 при 20%. Без скрытых надбавок."),
    ("Свой автопарк, не посредники", "100+ автомобилей у партнёра с 7-летней историей на рынке и 400+ отзывами. Машина реальная, не с чужого объявления."),
    ("Работаем с физ. и юр. лицами", "Те же условия для ИП и организаций: не нужно искать отдельного лизингодателя под бизнес."),
]

def render_why_choose():
    items = "".join(
        f'<div class="dl-why-item"><div class="dl-why-item__ico dl-why-item__ico--{BADGE_COLORS[i]}"><svg viewBox="0 0 24 24" fill="none">{BADGE_ICONS[i]}</svg></div>'
        f'<div><div class="dl-why-item__title">{html.escape(t)}</div><div class="dl-why-item__text">{html.escape(d)}</div></div></div>'
        for i, (t, d) in enumerate(WHY_CARDS)
    )
    return f'<div class="dl-why-list">{items}</div>'

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

def render_how_to_own():
    items = "".join(
        f'<div class="dl-why-item"><div class="dl-why-item__ico dl-why-item__ico--{BADGE_COLORS[i % len(BADGE_COLORS)]}"><svg viewBox="0 0 24 24" fill="none">{OWN_ICONS[i]}</svg></div>'
        f'<div><div class="dl-why-item__title">{html.escape(t)}</div><div class="dl-why-item__text">{html.escape(d)}</div></div></div>'
        for i, (t, d) in enumerate(OWN_STEPS)
    )
    return f'<div class="dl-steps-grid">{items}</div>'

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

def render_calculator(car):
    title_attr = html.escape(car_title(car)).replace('"', '&quot;')
    variants = car.get('variants')
    if not variants:
        return f'<div class="dl-calc-unavailable">Точная цена уточняется у менеджера. Оставьте заявку, посчитаем индивидуально.<button class="dl-btn dl-btn--calc-cta" type="button" data-art="{car["art"]}" data-car="{title_attr}">Забронировать</button></div>'
    pv_keys = sorted(variants.keys(), key=int)
    last_variant = variants[pv_keys[-1]]
    term_keys = sorted(last_variant['terms'].keys(), key=int)
    pv_buttons = "".join(f'<button data-pv="{k}" class="{"is-active" if i==len(pv_keys)-1 else ""}">{VARIANT_LABELS.get(k, k+"%")}</button>' for i,k in enumerate(pv_keys))
    term_buttons = "".join(f'<button data-term="{k}" class="{"is-active" if i==len(term_keys)-1 else ""}">{TERM_LABELS.get(k, k+" мес")}</button>' for i,k in enumerate(term_keys))
    return f'''<div class="dl-calc" data-car-data='{build_calculator_data(car)}' data-art="{car['art']}" data-car="{title_attr}">
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
    <button class="dl-btn dl-btn--calc-cta" type="button">Забронировать</button>
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
            price = min_week_price(c)
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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Onest:wght@500;600;700;800&family=Golos+Text:wght@400;500;600;700&family=Caveat:wght@600;700&display=swap">
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

  <div class="dl-hero-section">
    <div class="dl-hero-section__inner">
      <div class="dl-hero-top">
        <div class="dl-hero-top__main">
          <h1 class="dl-h1"><em>{title}</em> в лизинг и аренду с выкупом в Иркутске</h1>
          {subtitle}
        </div>
        {hero_top_right}
      </div>

      {badges}
    </div>
  </div>

  <div class="dl-detail-grid">
    <div class="dl-detail-main">
      <div class="dl-card__art dl-detail-gallery">{gallery}</div>
      {thumbs}

      {hero_banner}

      <h2 class="dl-h2">Характеристики</h2>
      {specs}

      <h2 class="dl-h2">Комплектация</h2>
      {komplekt}

      <h2 class="dl-h2">Описание</h2>
      {description}
    </div>

    <aside class="dl-detail-side">
      <div class="dl-card dl-calc-card">
        <h2 class="dl-h2" style="margin-top:0">Рассчитайте платёж</h2>
        {calculator}
      </div>
    </aside>
  </div>
</div>

{location_promo}

<div class="dl-wrap">
  <h2 class="dl-h2">Почему выгодно выбрать аренду с выкупом у нас</h2>
  {why_choose}

  <h2 class="dl-h2">Как стать владельцем</h2>
  {how_to_own}

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

<div class="dl-modal-backdrop" id="dlModalBackdrop" hidden>
  <div class="dl-modal" id="dlModal"></div>
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
        min_week = min_week_price(c)
        canonical = f"{SITE_URL}/cars/{slug}/"
        og_image = f"{SITE_URL}/{c['photos'][0]}" if c.get('photos') else f"{SITE_URL}/logo.png"
        price_bit = f" от {fmt_money(min_week)}/нед" if min_week is not None else ""
        title_tag = f"{title} в лизинг в Иркутске без банка{price_bit} · Драйв Лизинг"
        price_sentence = f" Платёж от {fmt_money(min_week)} в неделю." if min_week is not None else " Точная цена по запросу у менеджера."
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
            badges=render_badges2(),
            hero_banner=render_hero_banner(c, min_week, slug),
            subtitle=render_subtitle(spec_d),
            hero_top_right=render_hero_top_right(c),
            gallery=render_gallery(c['photos'], title),
            thumbs=render_thumbs(c['photos'], title),
            specs=render_specs(spec_d, c.get('year')),
            komplekt=render_komplekt(komplekt_items(c['komplekt'])),
            description=render_description(c, spec_d, c['art']),
            location_promo=render_location_promo(),
            why_choose=render_why_choose(),
            how_to_own=render_how_to_own(),
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
