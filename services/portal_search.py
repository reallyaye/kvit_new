import html
import re

from templates.portal_layout import portal_layout
from templates.portal_views import DOCUMENTS_REGISTRY, PORTAL_PAGES


def _clean_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = re.sub(r'<script.*?</script>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    return ' '.join(text.split())

PAGE_METADATA = {
    'home': {'category': 'Главная страница', 'url': '/'},
    'consumers': {'category': 'Потребителям', 'url': '/consumers'},
    'tarif': {'category': 'Тарифная политика', 'url': '/tarif'},
    'tu': {'category': 'Подключение к сетям', 'url': '/tu'},
    'outages': {'category': 'Мониторинг сети и отключения', 'url': '/outages'},
    'appeals': {'category': 'Электронная приемная', 'url': '/appeals'},
    'contacts': {'category': 'Контакты и РЭС', 'url': '/contacts'},
    'vacancy': {'category': 'Карьера и вакансии', 'url': '/vacancy'},
    'docs': {'category': 'Document Center', 'url': '/docs'},
    'reports': {'category': 'Отчетность и сметы', 'url': '/reports'},
    'zakup': {'category': 'Закупки и тендеры', 'url': '/zakup'},
    'load': {'category': 'Сетевая инфраструктура', 'url': '/load'},
    'line': {'category': 'Сетевая инфраструктура', 'url': '/line'},
    'lines10kv': {'category': 'Сетевая инфраструктура', 'url': '/lines10kv'},
    'ktp': {'category': 'Сетевая инфраструктура', 'url': '/ktp'},
    'lists': {'category': 'Перечень документов', 'url': '/lists'},
    'price': {'category': 'Прейскурант услуг', 'url': '/price'},
    'notices': {'category': 'Пресс-центр и объявления', 'url': '/notices'},
    'pd_byt_potr': {'category': 'Типовой договор', 'url': '/pd_byt_potr'},
    'tbquest': {'category': 'Охрана труда и ТБ', 'url': '/tbquest'},
    'online': {'category': 'Электронные сервисы', 'url': '/online'},
}

def highlight_term(text: str, query: str) -> str:
    if not query:
        return html.escape(text)
    words = [re.escape(w) for w in query.strip().split() if len(w) >= 2]
    if not words:
        return html.escape(text)
    pattern = re.compile(r'(' + '|'.join(words) + r')', re.IGNORECASE)
    parts = pattern.split(text)
    res = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            res.append(f'<mark style="background:#fef08a; color:#854d0e; padding:1px 4px; border-radius:3px; font-weight:600;">{html.escape(part)}</mark>')
        else:
            res.append(html.escape(part))
    return ''.join(res)

def extract_snippet(text: str, query: str, max_chars: int = 220) -> str:
    words = [re.escape(w) for w in query.strip().split() if len(w) >= 2]
    if not words:
        return text[:max_chars] + ('...' if len(text) > max_chars else '')

    pattern = re.compile(r'(' + '|'.join(words) + r')', re.IGNORECASE)
    m = pattern.search(text)
    if not m:
        return text[:max_chars] + ('...' if len(text) > max_chars else '')

    start = max(0, m.start() - 60)
    end = min(len(text), start + max_chars)
    prefix = '...' if start > 0 else ''
    suffix = '...' if end < len(text) else ''
    return prefix + text[start:end].strip() + suffix

def search_portal_content(query: str, max_results: int = 25):
    query = query.strip()
    if not query:
        return []

    q_words = [w.lower() for w in query.split() if len(w) >= 2]
    if not q_words:
        q_words = [query.lower()]

    results = []

    # 1. Поиск по страницам портала
    for page_key, page_data in PORTAL_PAGES.items():
        title = page_data.get('title', page_key)
        raw_html = page_data.get('html', '')
        plain_text = _clean_text(raw_html)

        score = 0
        title_lower = title.lower()
        text_lower = plain_text.lower()

        for w in q_words:
            if w in title_lower:
                score += 10
            if w in text_lower:
                score += 2 + text_lower.count(w)

        if score > 0:
            meta = PAGE_METADATA.get(page_key, {'category': 'Раздел сайта', 'url': f'/{page_key}'})
            snippet = extract_snippet(plain_text, query)
            results.append({
                'score': score,
                'title': title,
                'url': meta['url'],
                'category': meta['category'],
                'snippet': snippet,
                'type': 'page'
            })

    # 2. Поиск по реестру документов
    for doc_key, doc in DOCUMENTS_REGISTRY.items():
        title = doc.get('title', doc_key)
        category = doc.get('category', 'Документ')
        year = doc.get('year', '')
        files = doc.get('files', [])
        files_str = ' '.join([f if isinstance(f, str) else f.get('name', '') for f in files])

        doc_full = f"{title} {category} {year} {files_str}".lower()
        score = 0
        for w in q_words:
            if w in title.lower():
                score += 8
            if w in doc_full:
                score += 3

        if score > 0:
            clean_url = f"/{doc_key.removesuffix('.php')}"
            snippet = f"Документ за {year} год. Категория: {category}. Файлы: {len(files)} прил." if files else f"Документ за {year} год. Категория: {category}."
            results.append({
                'score': score,
                'title': title,
                'url': clean_url,
                'category': f'Документ • {year}' if year else 'Документ',
                'snippet': snippet,
                'type': 'doc'
            })

    # Сортировка по релевантности
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:max_results]

def render_global_search_page(query: str, results: list, is_admin: bool = False) -> str:
    escaped_q = html.escape(query)
    count = len(results)

    results_html = []
    if results:
        for item in results:
            h_title = highlight_term(item['title'], query)
            h_snippet = highlight_term(item['snippet'], query)

            card = f'''
            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:14px; padding:20px 24px; margin-bottom:14px; box-shadow:0 2px 6px rgba(15,23,42,0.03); transition:all 0.15s;">
                <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                    <span style="display:inline-block; font-size:11.5px; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; background:#f1f5f9; color:#475569; padding:3px 10px; border-radius:6px;">{html.escape(item['category'])}</span>
                    <span style="color:#94a3b8; font-size:12px;">•</span>
                    <span style="color:#64748b; font-size:12px; font-family:monospace;">{html.escape(item['url'])}</span>
                </div>
                <h3 style="font-size:17px; font-weight:700; margin:0 0 8px 0;">
                    <a href="{item['url']}" style="color:#0f172a; text-decoration:none; hover:color:#2563eb;">{h_title}</a>
                </h3>
                <p style="font-size:14px; color:#475569; line-height:1.55; margin:0 0 12px 0;">{h_snippet}</p>
                <div>
                    <a href="{item['url']}" style="display:inline-flex; align-items:center; gap:4px; font-size:13px; font-weight:600; color:#2563eb; text-decoration:none;">
                        <span>Перейти в раздел</span>
                        <svg class="svg-icon-stroke" width="13" height="13" viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                    </a>
                </div>
            </div>
            '''
            results_html.append(card)
        cards_block = '\n'.join(results_html)
    else:
        cards_block = f'''
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:16px; padding:40px 24px; text-align:center; box-shadow:0 2px 6px rgba(15,23,42,0.03);">
            <div style="width:52px; height:52px; border-radius:50%; background:#f1f5f9; color:#64748b; display:flex; align-items:center; justify-content:center; margin:0 auto 16px auto;">
                <svg class="svg-icon-stroke" width="24" height="24" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            </div>
            <h3 style="font-size:18px; font-weight:700; color:#0f172a; margin:0 0 8px 0;">Ничего не найдено по запросу «{escaped_q}»</h3>
            <p style="font-size:14px; color:#64748b; max-width:500px; margin:0 auto 20px auto; line-height:1.5;">
                Попробуйте изменить формулировку, проверить орфографию или воспользоваться нашими популярными разделами.
            </p>
            <div style="display:flex; flex-wrap:wrap; justify-content:center; gap:8px;">
                <a href="/tarif" style="background:#f8fafc; border:1px solid #e2e8f0; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; color:#0f172a; text-decoration:none;">Тарифы</a>
                <a href="/tu" style="background:#f8fafc; border:1px solid #e2e8f0; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; color:#0f172a; text-decoration:none;">Технические условия</a>
                <a href="/outages" style="background:#f8fafc; border:1px solid #e2e8f0; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; color:#0f172a; text-decoration:none;">Отключения</a>
                <a href="/vacancy" style="background:#f8fafc; border:1px solid #e2e8f0; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; color:#0f172a; text-decoration:none;">Вакансии</a>
                <a href="/contacts" style="background:#f8fafc; border:1px solid #e2e8f0; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; color:#0f172a; text-decoration:none;">Контакты РЭС</a>
                <a href="/kvit/" style="background:#f8fafc; border:1px solid #e2e8f0; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:600; color:#0f172a; text-decoration:none;">Поиск квитанции</a>
            </div>
        </div>
        '''

    body = f'''
    <nav class="breadcrumb-nav" aria-label="Хлебные крошки">
        <a href="/">
            <svg class="svg-icon-stroke" width="13" height="13" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
            Главная
        </a>
        <span class="breadcrumb-sep">
            <svg class="svg-icon-stroke" width="12" height="12" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
        </span>
        <span class="breadcrumb-current">Поиск по сайту</span>
    </nav>

    <div class="page-title-wrap">
        <div class="page-category-badge">
            <svg class="svg-icon-stroke" width="12" height="12" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            Информационный поиск
        </div>
        <h1 class="page-main-title">Результаты поиска по сайту</h1>
        <p style="color:#64748b; font-size:14.5px; margin:0; line-height:1.5;">
            По запросу «<strong style="color:#0f172a;">{escaped_q}</strong>» найдено совпадений: <strong style="color:#2563eb;">{count}</strong>
        </p>
    </div>

    <!-- ФОРМА ПОВТОРНОГО ПОИСКА -->
    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:14px; padding:16px 20px; margin-bottom:28px; box-shadow:0 2px 6px rgba(15,23,42,0.03);">
        <form action="/search" method="GET" style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
            <div style="flex:1; min-width:240px; display:flex; align-items:center; gap:8px; background:#f8fafc; border:1px solid #cbd5e1; border-radius:8px; padding:8px 14px;">
                <svg class="svg-icon-stroke" width="16" height="16" viewBox="0 0 24 24" style="color:#64748b;"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                <input type="text" name="q" value="{escaped_q}" placeholder="Введите слово для поиска по сайту..." style="width:100%; border:none; background:transparent; font-size:14px; outline:none; font-family:inherit; color:#0f172a;" required>
            </div>
            <button type="submit" style="background:#2563eb; color:#ffffff; border:none; border-radius:8px; padding:9px 20px; font-size:13.5px; font-weight:600; cursor:pointer; font-family:inherit; display:inline-flex; align-items:center; gap:6px;">
                <span>Искать</span>
            </button>
            <a href="/kvit/" style="font-size:13px; font-weight:600; color:#64748b; text-decoration:none; padding:8px 12px;">Поиск квитанции →</a>
        </form>
    </div>

    <div class="search-results-list">
        {cards_block}
    </div>
    '''
    return portal_layout(body, title=f'Поиск: {query} — ТОО «КРЭК»', active_nav='', is_admin=is_admin, current_slug='search')
