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
    <button class="dl-gallery__expand" type="button" aria-label="Открыть на весь экран"><svg viewBox="0 0 24 24" fill="none"><path d="M9 3H5a2 2 0 00-2 2v4M15 3h4a2 2 0 012 2v4M9 21H5a2 2 0 01-2-2v-4M15 21h4a2 2 0 002-2v-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
  </div>'''

def render_thumbs(photos, title):
    if not photos or len(photos) < 2:
        return ''
    thumbs = "".join(
        f'<button class="dl-thumb{" is-active" if i==0 else ""}" data-i="{i}"><img src="../../{p}" alt="{html.escape(title)}, миниатюра {i+1}" loading="lazy"></button>'
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

HERO_POINTS = [
    ("Проверенные авто", "car"),
    ("Прозрачный договор", "document2"),
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
        f'<div class="dl-hero-banner__point"><span class="dl-hero-banner__point-ico"><img src="../../images/icons3d/{icon}.png" alt="" loading="lazy"></span><span class="dl-hero-banner__point-text">{html.escape(t)}</span></div>'
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
    active_i = n - 1
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
    variants = car.get('variants')
    if not variants:
        return f'{head}<div class="dl-calc-unavailable">Точная цена уточняется у менеджера. Оставьте заявку, посчитаем индивидуально.<button class="dl-btn dl-btn--calc-cta" type="button" data-art="{car["art"]}" data-car="{title_attr}">Забронировать {ci("arrow")}</button></div>'
    pv_keys = sorted(variants.keys(), key=int)
    last_variant = variants[pv_keys[-1]]
    term_keys = sorted(last_variant['terms'].keys(), key=int)
    pv_slider = render_slider('pv', pv_keys, VARIANT_LABELS, '%')
    term_slider = render_slider('term', term_keys, TERM_LABELS, ' мес')
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
    <div class="dl-pv-sum-row">
      <span class="dl-pv-sum-row__ico"><img src="../../images/icons3d/pie-icon.png" alt="" loading="lazy"></span>
      <div><div class="dl-pv-sum" data-out="pv-sum"></div><div class="dl-pv-sum__note">Окончательные условия уточнит менеджер</div></div>
    </div>
    <button class="dl-btn dl-btn--calc-cta" type="button">Забронировать {ci('arrow')}</button>
  </div>
  <div class="dl-calc-note">
    <b>Вы пока ничего не платите</b>
    <span>Заявка ни к чему не обязывает. Менеджер свяжется и обсудит с вами точные условия бронирования.</span>
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
        <div class="dl-topbar__slogan">Помогаем получить автомобиль, <em>даже если банк отказал</em></div>
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
        <div class="dl-card dl-calc-card">
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

<div class="dl-lightbox" id="dlLightbox" hidden>
  <button class="dl-lightbox__close" id="dlLightboxClose" aria-label="Закрыть">&times;</button>
  <button class="dl-lightbox__nav is-prev" id="dlLightboxPrev" aria-label="Предыдущее фото"><svg viewBox="0 0 24 24" fill="none"><path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
  <img class="dl-lightbox__img" id="dlLightboxImg" src="" alt="">
  <button class="dl-lightbox__nav is-next" id="dlLightboxNext" aria-label="Следующее фото"><svg viewBox="0 0 24 24" fill="none"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
  <div class="dl-lightbox__count" id="dlLightboxCount"></div>
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
            reasons=render_reasons(),
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
