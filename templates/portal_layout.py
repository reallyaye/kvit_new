import html
import os

from templates.icons import icon
from templates.locale import get_locale, localized_path


def _asset_v(rel_path: str) -> str:
    """Автоматический cache-buster: возвращает timestamp изменения файла."""
    try:
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', rel_path.lstrip('/'))
        return str(int(os.path.getmtime(full_path)))
    except Exception:
        return '20260903'


def portal_layout(
    content: str,
    title: str = "ТОО КРЭК — Карагандинская Региональная Энергетическая Компания",
    description: str = "ТОО КРЭК — Карагандинская Региональная Энергетическая Компания. Передача и распределение электроэнергии, электронные квитанции, технические условия.",
    active_nav: str = "home",
    is_admin: bool = False,
    current_slug: str = ""
) -> str:
    """Генерирует базовый HTML-макет информационного портала ТОО «КРЭК»."""
    escaped_title = html.escape(title)
    escaped_desc = html.escape(description)
    style_v = _asset_v('css/style.css')
    heroui_v = _asset_v('css/heroui.css')
    sw_v = _asset_v('sw.js')
    locale = get_locale()
    canonical_source = '/' if current_slug in ('home', '', None) else f'/{current_slug}'
    canonical_path = localized_path(canonical_source, locale)
    ru_path = localized_path(canonical_source, 'ru')
    kk_path = localized_path(canonical_source, 'kk')
    html_lang = 'kk' if locale == 'kk' else 'ru'

    admin_bar_html = ''
    if is_admin:
        edit_btn = ''
        if current_slug and current_slug != '404':
            edit_btn = f'''<a href="/admin/pages/edit?slug={html.escape(current_slug)}" style="background:#2563eb;color:#fff;padding:5px 12px;border-radius:6px;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:6px;font-size:12.5px;">
                {icon('edit', 13, '#fff')} Редактировать эту страницу
            </a>'''

        admin_bar_html = f'''
        <div class="portal-admin-bar" style="background:rgba(15,23,42,0.95);backdrop-filter:blur(16px) saturate(180%);color:#e2e8f0;padding:8px 24px;display:flex;align-items:center;justify-content:space-between;font-size:13px;font-family:'Inter',-apple-system,sans-serif;border-bottom:1px solid rgba(255,255,255,0.1);position:relative;z-index:990;box-shadow:0 4px 16px rgba(0,0,0,0.2);flex-wrap:wrap;gap:10px;">
            <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
                <span style="font-weight:700;color:#38bdf8;display:inline-flex;align-items:center;gap:6px;background:rgba(56,189,248,0.12);padding:3px 10px;border-radius:9999px;border:1px solid rgba(56,189,248,0.25);">
                    {icon('shield', 14, '#38bdf8')} Панель управления
                </span>
                <a href="/admin/stats" style="color:#cbd5e1;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:6px;transition:background .15s;">
                    {icon('trending_up', 14, '#94a3b8')} Посещаемость
                </a>
                <a href="/admin/pages" style="color:#cbd5e1;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:6px;transition:background .15s;">
                    {icon('layout', 14, '#94a3b8')} Страницы
                </a>
                <a href="/admin/media" style="color:#cbd5e1;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:6px;transition:background .15s;">
                    {icon('image', 14, '#94a3b8')} Медиа
                </a>
                <a href="/admin/documents" style="color:#cbd5e1;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:6px;transition:background .15s;">
                    {icon('files', 14, '#94a3b8')} Документы
                </a>
                <a href="/admin/users" style="color:#cbd5e1;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:6px;transition:background .15s;">
                    {icon('users', 14, '#94a3b8')} Сотрудники
                </a>
                <a href="/upload" style="color:#cbd5e1;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:6px;transition:background .15s;">
                    {icon('upload', 14, '#94a3b8')} Квитанции
                </a>
                <a href="/reconcile" style="color:#cbd5e1;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:6px;transition:background .15s;">
                    {icon('reconcile', 14, '#94a3b8')} Сверка
                </a>
            </div>
            <div style="display:flex;align-items:center;gap:10px;">
                {edit_btn}
                <a href="/logout" style="color:#fda4af;background:rgba(244,63,94,0.15);border:1px solid rgba(244,63,94,0.3);padding:4px 12px;border-radius:6px;text-decoration:none;font-size:12px;font-weight:600;display:inline-flex;align-items:center;gap:5px;transition:all .15s;">
                    {icon('logout', 13, '#fda4af')} Выйти
                </a>
            </div>
        </div>'''

    return f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
<meta charset="utf-8" />
<meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, viewport-fit=cover">
<meta name="theme-color" content="#0f172a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="description" content="{escaped_desc}" />
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://krec.kz{canonical_path}">
<link rel="alternate" hreflang="ru" href="https://krec.kz{ru_path}">
<link rel="alternate" hreflang="kk" href="https://krec.kz{kk_path}">
<link rel="alternate" hreflang="x-default" href="https://krec.kz{ru_path}">
<meta property="og:title" content="{escaped_title}">
<meta property="og:description" content="{escaped_desc}">
<meta property="og:url" content="https://krec.kz{canonical_path}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="ТОО «КРЭК»">
<meta property="og:image" content="https://krec.kz/images/logo.png">
<title>{escaped_title}</title>
<link rel="manifest" href="/manifest.json">
<link rel="stylesheet" href="/css/style.css?v={style_v}" type="text/css" />
<link rel="stylesheet" href="/css/heroui.css?v={heroui_v}" type="text/css" />
<link rel="shortcut icon" href="/favicon.ico?v={style_v}" type="image/vnd.microsoft.icon">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "ТОО «Карагандинская Региональная Энергетическая Компания»",
  "alternateName": "ТОО «КРЭК»",
  "url": "https://krec.kz",
  "logo": "https://krec.kz/images/logo.png",
  "telephone": "+7-7212-90-03-58",
  "email": "info@krec.kz",
  "taxID": "031140001297",
  "address": {{
    "@type": "PostalAddress",
    "streetAddress": "108 уч. квартал, строение 7",
    "addressLocality": "Караганда",
    "addressRegion": "Карагандинская область",
    "postalCode": "100000",
    "addressCountry": "KZ"
  }}
}}
</script>
<script>
if ('serviceWorker' in navigator) {{
    window.addEventListener('load', function() {{
        navigator.serviceWorker.register('/sw.js?v={sw_v}').then(function(reg) {{
            reg.update();
        }}).catch(function() {{}});
    }});
    navigator.serviceWorker.addEventListener('controllerchange', function() {{
        if (!window._swReloaded) {{
            window._swReloaded = true;
            window.location.reload();
        }}
    }});
}}
</script>
</head>
<body>
{admin_bar_html}

<div id="wrap">

<!-- ===== ЕДИНЫЙ СОВРЕМЕННЫЙ STICKY HEADER ===== -->
<header class="krec-header" id="krecHeader">
    <div class="krec-header-container">
        <a href="/" class="krec-brand">
            <img src="/images/logo.png?v=8" alt="ТОО КРЭК" class="krec-logo-img" />
            <div class="krec-brand-text">
                <span class="krec-brand-title">ТОО &laquo;КРЭК&raquo;</span>
                <span class="krec-brand-subtitle">Электрические сети Карагандинской области</span>
            </div>
        </a>

        <!-- Основная навигация -->
        <nav class="krec-nav" id="portalNav" aria-label="Основная навигация">
            <div class="krec-nav-mobile-header">
                <span class="krec-nav-mobile-title">Меню портала</span>
                <button type="button" class="krec-nav-close-btn" aria-label="Закрыть меню" onclick="closeMobileNav()">&times;</button>
            </div>
            <ul class="krec-nav-list">
                <li class="krec-nav-item has-dropdown">
                    <a href="/consumers" class="krec-nav-link {'active' if active_nav in ('consumers', 'potreb', 'price', 'tarif', 'pd_byt_potr') else ''}">
                        <span>Потребителям</span>
                        <svg class="nav-chevron" width="10" height="10" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                    </a>
                    <div class="krec-dropdown">
                        <a href="/kvit/" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Электронная квитанция</div>
                                <div class="krec-dd-desc">Поиск, просмотр и скачивание PDF</div>
                            </div>
                        </a>
                        <a href="/tarif" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><circle cx="12" cy="12" r="10"/><line x1="7" y1="6.5" x2="17" y2="6.5"/><line x1="7" y1="10.5" x2="17" y2="10.5"/><line x1="12" y1="10.5" x2="12" y2="18.5"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Тариф на передачу э/э</div>
                                <div class="krec-dd-desc">Регулируемый тариф (Приказ № 77-ОД)</div>
                            </div>
                        </a>
                        <a href="/price" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><circle cx="7" cy="7" r="1.5"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Цены на электроснабжение</div>
                                <div class="krec-dd-desc">Розничные цены для потребителей районов</div>
                            </div>
                        </a>
                        <a href="/pd_byt_potr" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Типовой публичный договор</div>
                                <div class="krec-dd-desc">Договор электроснабжения</div>
                            </div>
                        </a>
                        <a href="/appeals" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Обратиться в КРЭК</div>
                                <div class="krec-dd-desc">Электронная приемная обращений</div>
                            </div>
                        </a>
                        <a href="/notices" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Объявления и новости</div>
                                <div class="krec-dd-desc">Официальные сообщения компании</div>
                            </div>
                        </a>
                    </div>
                </li>

                <li class="krec-nav-item has-dropdown">
                    <a href="/tu" class="krec-nav-link {'active' if active_nav in ('tu', 'connection', 'lists') else ''}">
                        <span>Подключение</span>
                        <svg class="nav-chevron" width="10" height="10" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                    </a>
                    <div class="krec-dropdown">
                        <a href="/tu" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Технические условия</div>
                                <div class="krec-dd-desc">Порядок подключения и этапы</div>
                            </div>
                        </a>
                        <a href="/lists" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Необходимые документы</div>
                                <div class="krec-dd-desc">Checklist для физлиц, юрлиц и ИП</div>
                            </div>
                        </a>
                        <a href="https://gov.ggk.kz" target="_blank" rel="noopener noreferrer" class="krec-dropdown-item highlight-portal">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Портал АИС ГГК (gov.ggk.kz) ↗</div>
                                <div class="krec-dd-desc">Подача заявки онлайн с ЭЦП</div>
                            </div>
                        </a>
                    </div>
                </li>

                <li class="krec-nav-item has-dropdown">
                    <a href="/load" class="krec-nav-link {'active' if active_nav in ('load', 'line', 'lines10kv', 'ktp') else ''}">
                        <span>Сеть</span>
                        <svg class="nav-chevron" width="10" height="10" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                    </a>
                    <div class="krec-dropdown">
                        <a href="/load" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Подстанции 35–110 кВ</div>
                                <div class="krec-dd-desc">Загрузка и резерв мощности</div>
                            </div>
                        </a>
                        <a href="/line" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Линии 35–110 кВ</div>
                                <div class="krec-dd-desc">Высоковольтные сети</div>
                            </div>
                        </a>
                        <a href="/lines10kv" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Линии 6–10 кВ</div>
                                <div class="krec-dd-desc">Распределительные сети</div>
                            </div>
                        </a>
                        <a href="/ktp" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg></div>
                            <div>
                                <div class="krec-dd-title">КТП 6(10) кВ</div>
                                <div class="krec-dd-desc">Трансформаторные подстанции</div>
                            </div>
                        </a>
                    </div>
                </li>

                <li class="krec-nav-item has-dropdown">
                    <a href="/contacts" class="krec-nav-link {'active' if active_nav in ('contacts', 'company', 'about') else ''}">
                        <span>Компания</span>
                        <svg class="nav-chevron" width="10" height="10" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                    </a>
                    <div class="krec-dropdown">
                        <a href="/#about" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></div>
                            <div>
                                <div class="krec-dd-title">О компании ТОО «КРЭК»</div>
                                <div class="krec-dd-desc">Масштаб сети и инфраструктура</div>
                            </div>
                        </a>
                        <a href="/contacts" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Контакты и службы</div>
                                <div class="krec-dd-desc">Центральный офис и подразделения</div>
                            </div>
                        </a>
                        <a href="/contacts#res" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Районы сетей (6 РЭС)</div>
                                <div class="krec-dd-desc">Абай, Осакаровка, Нура, Каркаралинск...</div>
                            </div>
                        </a>
                        <a href="/tbquest" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Охрана труда и ТБ</div>
                                <div class="krec-dd-desc">Техника безопасности персонала</div>
                            </div>
                        </a>
                    </div>
                </li>

                <li class="krec-nav-item">
                    <a href="/zakup" class="krec-nav-link {'active' if active_nav == 'zakup' else ''}">
                        <span>Закупки</span>
                    </a>
                </li>

                <li class="krec-nav-item">
                    <a href="/vacancy" class="krec-nav-link {'active' if active_nav == 'vacancy' else ''}">
                        <span>Вакансии</span>
                    </a>
                </li>

                <li class="krec-nav-item has-dropdown">
                    <a href="/docs" class="krec-nav-link {'active' if active_nav in ('docs', 'reports') else ''}">
                        <span>Документы</span>
                        <svg class="nav-chevron" width="10" height="10" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                    </a>
                    <div class="krec-dropdown">
                        <a href="/docs" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Нормативная база</div>
                                <div class="krec-dd-desc">Законы и правила РК</div>
                            </div>
                        </a>
                        <a href="/reports" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Отчеты по ИП и ТС</div>
                                <div class="krec-dd-desc">Инвестпрограмма и тарифная смета</div>
                            </div>
                        </a>
                        <a href="/price" class="krec-dropdown-item">
                            <div class="krec-dd-icon"><svg width="15" height="15" viewBox="0 0 24 24" class="svg-icon-stroke"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div>
                            <div>
                                <div class="krec-dd-title">Прейскурант услуг</div>
                                <div class="krec-dd-desc">Регулируемые и сервисные услуги</div>
                            </div>
                        </a>
                    </div>
                </li>
            </ul>
        </nav>

        <!-- Правый блок: Бургер-меню -->
        <div class="krec-header-actions">
            <div class="krec-lang-switch" aria-label="Язык страницы">
                <a href="{ru_path}" class="krec-lang-btn {'active' if locale == 'ru' else ''}" lang="ru">Рус</a>
                <span class="krec-lang-sep">/</span>
                <a href="{kk_path}" class="krec-lang-btn {'active' if locale == 'kk' else ''}" lang="kk">Қаз</a>
            </div>
            <button class="mobile-nav-toggle" id="mobileNavToggle" aria-label="Открыть навигационное меню" aria-expanded="false" onclick="toggleMobileNav(event)">
                <span class="burger-icon-bars">
                    <span></span><span></span><span></span>
                </span>
            </button>
        </div>
    </div>
</header>

<div class="mobile-nav-backdrop" id="mobileNavBackdrop" onclick="closeMobileNav()"></div>

<!-- ===== ОСНОВНОЙ КОНТЕНТ ===== -->
<div class="content-container">
{content}
</div>

<!-- ===== БОЛЬШОЙ КОРПОРАТИВНЫЙ FOOTER ===== -->
<footer class="krec-footer" id="krecFooter">
    <div class="krec-footer-top">
        <div class="krec-footer-container">
            <div class="krec-footer-col">
                <h4 class="krec-footer-title">Потребителям</h4>
                <ul class="krec-footer-links">
                    <li><a href="/kvit/">Электронная квитанция</a></li>
                    <li><a href="/consumers">Сервисный центр потребителей</a></li>
                    <li><a href="/tarif">Тариф на передачу э/э</a></li>
                    <li><a href="/price">Цены на электроснабжение</a></li>
                                        <li><a href="/pd_byt_potr">Типовой публичный договор</a></li>
                    <li><a href="/appeals">Обратиться в КРЭК</a></li>
                    <li><a href="/notices">Объявления и новости</a></li>
                </ul>
            </div>

            <div class="krec-footer-col">
                <h4 class="krec-footer-title">Подключение и сеть</h4>
                <ul class="krec-footer-links">
                    <li><a href="/tu">Порядок подключения к сетям</a></li>
                    <li><a href="/tu">Технические условия (ТУ)</a></li>
                    <li><a href="/lists">Необходимые документы</a></li>
                    <li><a href="https://gov.ggk.kz" target="_blank" rel="noopener noreferrer">Портал АИС ГГК (gov.ggk.kz) ↗</a></li>
                    <li><a href="/load">Загрузка подстанций 35–110 кВ</a></li>
                    <li><a href="/images/nets.png" target="_blank" rel="noopener noreferrer">Схема электрических сетей ↗</a></li>
                </ul>
            </div>

            <div class="krec-footer-col">
                <h4 class="krec-footer-title">Компания</h4>
                <ul class="krec-footer-links">
                    <li><a href="/#about">О компании ТОО «КРЭК»</a></li>
                    <li><a href="/contacts#res">Районы электрических сетей (6 РЭС)</a></li>
                    <li><a href="/contacts">Контакты и реквизиты</a></li>
                    <li><a href="/privacy">Политика конфиденциальности</a></li>
                    <li><a href="/terms">Условия использования</a></li>
                    <li><a href="javascript:void(0)" onclick="krecOpenCookieModal()">Настройки файлов cookie</a></li>
                    <li><a href="/vacancy">Вакансии предприятия</a></li>
                    <li><a href="/tbquest">Охрана труда и безопасность</a></li>
                </ul>
            </div>

            <div class="krec-footer-col">
                <h4 class="krec-footer-title">Документы и закупки</h4>
                <ul class="krec-footer-links">
                    <li><a href="/reports">Отчетность по инвестпрограмме</a></li>
                    <li><a href="/reports">Отчетность по тарифной смете</a></li>
                    <li><a href="/docs">Нормативно-правовая база</a></li>
                    <li><a href="/zakup">Планы закупок и тендеры</a></li>
                    <li><a href="/price">Прейскурант сервисных услуг</a></li>
                    <li><a href="/privacy#rights">Защита персональных данных</a></li>
                </ul>
            </div>
        </div>
    </div>

    <div class="krec-footer-bottom">
        <div class="krec-footer-container bottom-row">
            <div class="krec-footer-copy">
                <div>&copy; 2005&ndash;2026 ТОО &laquo;Карагандинская Региональная Энергетическая Компания&raquo; (ТОО &laquo;КРЭК&raquo;). Все права защищены.</div>
                <div style="margin-top:4px; font-size:12.5px; color:#cbd5e1;">
                    БИН: <strong>031140001297</strong> &bull; 100000, Карагандинская обл., г. Караганда, район им. Казыбек би, 108 учетный квартал, стр. 7
                </div>
                <div style="margin-top:3px; font-size:12px; color:#94a3b8;">
                    Вопросы по персональным данным: <a href="mailto:dpo@krec.kz" style="color:#93c5fd; text-decoration:none;">dpo@krec.kz</a> &bull; Канцелярия: +7 (7212) 90-03-50
                </div>
                <div style="margin-top:6px; font-size:12px; color:#94a3b8; display:flex; align-items:center; gap:6px;">
                    <svg width="13" height="13" viewBox="0 0 24 24" class="svg-icon-stroke" style="stroke:#94a3b8;"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                    <span>Разработка и создание портала: <a href="https://t.me/REALLY_DE4D" target="_blank" rel="noopener noreferrer" style="color:#e2e8f0; font-weight:700; text-decoration:none; border-bottom:1px dotted #64748b; transition:all 0.2s;" onmouseover="this.style.color='#60a5fa';this.style.borderBottomColor='#60a5fa'" onmouseout="this.style.color='#e2e8f0';this.style.borderBottomColor='#64748b'">Жүніс Тамерлан</a></span>
                </div>
            </div>
            <div class="krec-footer-ods">
                <span class="ods-badge">ОДС (круглосуточно)</span>
                <a href="tel:+77212900358" class="ods-tel">+7 (7212) 90-03-58</a>
                <span class="ods-sep">•</span>
                <a href="tel:+77212900359" class="ods-tel">+7 (7212) 90-03-59</a>
            </div>
        </div>
    </div>
</footer>

</div><!-- /#wrap -->

<!-- ===== КОРПОРАТИВНЫЙ БАННЕР СОГЛАСИЯ НА COOKIES ===== -->
<div id="krecCookieBanner" class="krec-cookie-banner" style="display:none;" role="region" aria-label="Уведомление о файлах cookie">
    <div class="krec-cookie-container">
        <div class="krec-cookie-text">
            <div class="krec-cookie-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                <span>Файлы cookie и конфиденциальность данных</span>
            </div>
            <p>Мы используем обязательные cookies для работы портала и аналитические cookies (Яндекс.Метрика) для анализа посещаемости сайта. На страницах поиска квитанций и обращений запись экрана и перехват ввода клавиатуры отключены. Вы можете принять все или продолжить только с техническими cookies. Подробнее: <a href="/privacy" style="color:#60a5fa;text-decoration:underline;">Политика сбора и обработки данных</a>.</p>
        </div>
        <div class="krec-cookie-actions">
            <button type="button" class="krec-cookie-btn krec-cookie-btn-primary" onclick="krecAcceptAllCookies()">Принять все</button>
            <button type="button" class="krec-cookie-btn krec-cookie-btn-outline" onclick="krecRejectCookies()">Только необходимые</button>
            <button type="button" class="krec-cookie-btn krec-cookie-btn-subtle" onclick="krecOpenCookieModal()">Настроить</button>
        </div>
    </div>
</div>

<!-- ===== МОДАЛЬНОЕ ОКНО НАСТРОЙКИ COOKIES ===== -->
<div id="krecCookieModal" class="krec-cookie-modal-backdrop" style="display:none;" onclick="if(event.target===this)krecCloseCookieModal()">
    <div class="krec-cookie-modal-content" role="dialog" aria-modal="true" aria-labelledby="krecCookieModalTitle">
        <div class="krec-cookie-modal-header">
            <h3 id="krecCookieModalTitle">Настройки файлов cookie и аналитики</h3>
            <button type="button" class="krec-cookie-close-btn" onclick="krecCloseCookieModal()" aria-label="Закрыть">&times;</button>
        </div>
        <div class="krec-cookie-modal-body">
            <p style="margin-bottom:16px; font-size:13.5px; color:#64748b; line-height:1.5;">В соответствии с Законом Республики Казахстан «О персональных данных и их защите» вы можете настроить категории используемых файлов cookie.</p>

            <div class="krec-cookie-option">
                <div class="krec-cookie-opt-header">
                    <div>
                        <strong>Технические (необходимые) cookies</strong>
                        <span class="krec-badge-req">Всегда активны</span>
                    </div>
                </div>
                <p>Обеспечивают базовое функционирование сайта: выбор языка, сессии, предотвращение атак. Без них сайт не может работать.</p>
            </div>

            <div class="krec-cookie-option">
                <div class="krec-cookie-opt-header">
                    <div>
                        <strong>Аналитические cookies (Яндекс.Метрика)</strong>
                    </div>
                    <label class="krec-switch">
                        <input type="checkbox" id="krecConsentAnalyticsCheckbox">
                        <span class="krec-slider"></span>
                    </label>
                </div>
                <p>Сбор агрегированной обезличенной статистики посещаемости. На страницах поиска квитанций и формы обращений Webvisor (запись действий на экране) отключён принудительно.</p>
            </div>
        </div>
        <div class="krec-cookie-modal-footer">
            <button type="button" class="krec-cookie-btn krec-cookie-btn-outline" onclick="krecCloseCookieModal()">Отмена</button>
            <button type="button" class="krec-cookie-btn krec-cookie-btn-primary" onclick="krecSaveCookieSettings()">Сохранить выбор</button>
        </div>
    </div>
</div>

<style>
/* Cookie Banner & Modal styles */
.krec-cookie-banner {{
    position: fixed;
    bottom: 20px;
    left: 20px;
    right: 20px;
    max-width: 960px;
    margin: 0 auto;
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(16px) saturate(180%);
    -webkit-backdrop-filter: blur(16px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 16px;
    padding: 18px 24px;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35);
    z-index: 99999;
    color: #f8fafc;
    font-family: 'Inter', -apple-system, sans-serif;
    animation: krecSlideUp 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}}
@keyframes krecSlideUp {{
    from {{ transform: translateY(100%); opacity: 0; }}
    to {{ transform: translateY(0); opacity: 1; }}
}}
.krec-cookie-container {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    flex-wrap: wrap;
}}
.krec-cookie-text {{
    flex: 1 1 500px;
}}
.krec-cookie-title {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 700;
    font-size: 15px;
    color: #38bdf8;
    margin-bottom: 6px;
}}
.krec-cookie-text p {{
    margin: 0;
    font-size: 13px;
    line-height: 1.55;
    color: #cbd5e1;
}}
.krec-cookie-actions {{
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}}
.krec-cookie-btn {{
    padding: 9px 18px;
    border-radius: 9999px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    font-family: inherit;
    border: none;
}}
.krec-cookie-btn-primary {{
    background: #2563eb;
    color: #ffffff;
}}
.krec-cookie-btn-primary:hover {{
    background: #1d4ed8;
    transform: translateY(-1px);
}}
.krec-cookie-btn-outline {{
    background: rgba(255, 255, 255, 0.08);
    color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.2);
}}
.krec-cookie-btn-outline:hover {{
    background: rgba(255, 255, 255, 0.16);
    border-color: rgba(255, 255, 255, 0.35);
}}
.krec-cookie-btn-subtle {{
    background: transparent;
    color: #94a3b8;
    padding: 9px 12px;
}}
.krec-cookie-btn-subtle:hover {{
    color: #f8fafc;
    text-decoration: underline;
}}
.krec-cookie-modal-backdrop {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(15, 23, 42, 0.7);
    backdrop-filter: blur(8px);
    z-index: 100000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    box-sizing: border-box;
}}
.krec-cookie-modal-content {{
    background: #ffffff;
    color: #0f172a;
    width: 100%;
    max-width: 540px;
    border-radius: 18px;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.25);
    overflow: hidden;
    animation: krecModalZoom 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}}
@keyframes krecModalZoom {{
    from {{ transform: scale(0.95); opacity: 0; }}
    to {{ transform: scale(1); opacity: 1; }}
}}
.krec-cookie-modal-header {{
    padding: 20px 24px;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    align-items: center;
    justify-content: space-between;
}}
.krec-cookie-modal-header h3 {{
    margin: 0;
    font-size: 17px;
    font-weight: 700;
    color: #0f172a;
}}
.krec-cookie-close-btn {{
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: #64748b;
    line-height: 1;
}}
.krec-cookie-modal-body {{
    padding: 20px 24px;
    max-height: 60vh;
    overflow-y: auto;
}}
.krec-cookie-option {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 14px;
}}
.krec-cookie-opt-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
}}
.krec-badge-req {{
    font-size: 11px;
    background: #e2e8f0;
    color: #475569;
    padding: 2px 8px;
    border-radius: 9999px;
    margin-left: 8px;
    font-weight: 600;
}}
.krec-cookie-option p {{
    margin: 0;
    font-size: 12.5px;
    color: #64748b;
    line-height: 1.45;
}}
.krec-switch {{
    position: relative;
    display: inline-block;
    width: 44px;
    height: 24px;
}}
.krec-switch input {{
    opacity: 0;
    width: 0;
    height: 0;
}}
.krec-slider {{
    position: absolute;
    cursor: pointer;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: #cbd5e1;
    transition: .25s;
    border-radius: 24px;
}}
.krec-slider:before {{
    position: absolute;
    content: "";
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: .25s;
    border-radius: 50%;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}}
.krec-switch input:checked + .krec-slider {{
    background-color: #2563eb;
}}
.krec-switch input:checked + .krec-slider:before {{
    transform: translateX(20px);
}}
.krec-cookie-modal-footer {{
    padding: 16px 24px;
    border-top: 1px solid #e2e8f0;
    background: #f8fafc;
    display: flex;
    justify-content: flex-end;
    gap: 12px;
}}
.krec-cookie-modal-footer .krec-cookie-btn-outline {{
    background: #ffffff;
    color: #475569;
    border-color: #cbd5e1;
}}
.krec-cookie-modal-footer .krec-cookie-btn-outline:hover {{
    background: #f1f5f9;
}}
</style>

<script>
function toggleMobileNav(e) {{
    if (e) {{
        e.preventDefault();
        e.stopPropagation();
    }}
    const nav = document.getElementById('portalNav');
    const toggle = document.getElementById('mobileNavToggle');
    const backdrop = document.getElementById('mobileNavBackdrop');
    const isOpen = nav.classList.toggle('is-open');
    if (toggle) {{
        toggle.classList.toggle('active', isOpen);
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    }}
    if (backdrop) {{
        backdrop.classList.toggle('is-visible', isOpen);
    }}
    document.body.classList.toggle('mobile-menu-active', isOpen);
}}

function closeMobileNav() {{
    const nav = document.getElementById('portalNav');
    const toggle = document.getElementById('mobileNavToggle');
    const backdrop = document.getElementById('mobileNavBackdrop');
    if (nav) nav.classList.remove('is-open');
    if (toggle) {{
        toggle.classList.remove('active');
        toggle.setAttribute('aria-expanded', 'false');
    }}
    if (backdrop) backdrop.classList.remove('is-visible');
    document.body.classList.remove('mobile-menu-active');
}}

function switchAnnouncementLang(lang) {{
    var ruCard = document.getElementById('announcementRu');
    var kzCard = document.getElementById('announcementKz');
    var btnRu = document.getElementById('btnAnnounceRu');
    var btnKz = document.getElementById('btnAnnounceKz');

    if (lang === 'kz') {{
        if (ruCard) ruCard.style.display = 'none';
        if (kzCard) kzCard.style.display = 'block';
        if (btnRu) btnRu.classList.remove('active');
        if (btnKz) btnKz.classList.add('active');
    }} else {{
        if (kzCard) kzCard.style.display = 'none';
        if (ruCard) ruCard.style.display = 'block';
        if (btnKz) btnKz.classList.remove('active');
        if (btnRu) btnRu.classList.add('active');
    }}
    try {{
        localStorage.setItem('krec_announce_lang', lang);
    }} catch(e) {{}}
}}

function switchPortalLang(lang) {{
    var ruBtn = document.getElementById('btnLangRu');
    var kzBtn = document.getElementById('btnLangKz');
    if (ruBtn && kzBtn) {{
        if (lang === 'kz') {{
            ruBtn.classList.remove('active');
            kzBtn.classList.add('active');
        }} else {{
            kzBtn.classList.remove('active');
            ruBtn.classList.add('active');
        }}
    }}
    try {{
        localStorage.setItem('krec_portal_lang', lang);
        document.cookie = 'krec_lang=' + lang + '; path=/; max-age=31536000';
    }} catch(e) {{}}

    // Синхронизируем официальные объявления, если присутствуют на странице
    if (typeof switchAnnouncementLang === 'function') {{
        switchAnnouncementLang(lang);
    }}
}}

document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') {{
        closeMobileNav();
    }}
}});

window.addEventListener('resize', function() {{
    if (window.innerWidth > 1080) {{
        closeMobileNav();
    }}
}});

document.addEventListener('DOMContentLoaded', function() {{
    try {{
        var saved = localStorage.getItem('krec_portal_lang') || localStorage.getItem('krec_announce_lang');
        if (saved === 'kz') {{
            switchPortalLang('kz');
        }}
    }} catch(e) {{}}
}});

// ===== COOKIE CONSENT & METRIKA SHIELD =====
(function() {{
    var sensitiveSlugs = ['appeals', 'search', 'kvit', 'receipt'];
    var currentSlug = '{current_slug}'.toLowerCase();
    var isSensitive = sensitiveSlugs.indexOf(currentSlug) !== -1;

    function getStoredConsent() {{
        try {{
            var raw = localStorage.getItem('krec_cookie_consent');
            if (raw) return JSON.parse(raw);
        }} catch(e) {{}}
        return null;
    }}

    function purgeTrackingData() {{
        var host = window.location.hostname;
        var domains = ['', '.' + host, host];
        var parts = host.split('.');
        if (parts.length >= 2) {{
            domains.push('.' + parts.slice(-2).join('.'));
        }}
        try {{
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {{
                var c = cookies[i].trim();
                var eq = c.indexOf('=');
                var name = eq > -1 ? c.substring(0, eq).trim() : c;
                if (name.indexOf('_ym') === 0 || name.indexOf('yabs') === 0 || name === 'krec_analytics') {{
                    for (var d = 0; d < domains.length; d++) {{
                        var dom = domains[d];
                        var domAttr = dom ? '; domain=' + dom : '';
                        document.cookie = name + '=; path=/; max-age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT' + domAttr;
                    }}
                }}
            }}
            document.cookie = 'krec_analytics=0; path=/; max-age=31536000; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
        }} catch(e) {{}}

        try {{
            var removeKeys = [];
            for (var k = 0; k < localStorage.length; k++) {{
                var key = localStorage.key(k);
                if (key && (key.indexOf('_ym') === 0 || key.indexOf('yabs') === 0 || key.indexOf('metrika') !== -1)) {{
                    removeKeys.push(key);
                }}
            }}
            for (var j = 0; j < removeKeys.length; j++) {{
                localStorage.removeItem(removeKeys[j]);
            }}
        }} catch(e) {{}}

        try {{
            var sRemoveKeys = [];
            for (var sk = 0; sk < sessionStorage.length; sk++) {{
                var sKey = sessionStorage.key(sk);
                if (sKey && (sKey.indexOf('_ym') === 0 || sKey.indexOf('yabs') === 0 || sKey.indexOf('metrika') !== -1)) {{
                    sRemoveKeys.push(sKey);
                }}
            }}
            for (var sj = 0; sj < sRemoveKeys.length; sj++) {{
                sessionStorage.removeItem(sRemoveKeys[sj]);
            }}
        }} catch(e) {{}}

        if (window.yaCounter51197381) {{
            try {{
                if (typeof window.yaCounter51197381.destructor === 'function') {{
                    window.yaCounter51197381.destructor();
                }}
            }} catch(e) {{}}
            window.yaCounter51197381 = null;
        }}
        window._krecMetrikaInitialized = false;
    }}

    function storeConsent(allowAnalytics) {{
        var val = {{
            analytics: !!allowAnalytics,
            necessary: true,
            timestamp: new Date().toISOString(),
            version: 'v1.0-2026-kz'
        }};
        try {{
            localStorage.setItem('krec_cookie_consent', JSON.stringify(val));
            if (allowAnalytics) {{
                document.cookie = 'krec_analytics=1; path=/; max-age=31536000; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
            }} else {{
                purgeTrackingData();
            }}
        }} catch(e) {{}}
        return val;
    }}

    function loadYandexMetrika(enableWebvisor) {{
        if (window.yaCounter51197381 || window._krecMetrikaInitialized) return;
        window._krecMetrikaInitialized = true;

        (function (d, w, c) {{
            (w[c] = w[c] || []).push(function() {{
                try {{
                    // На чувствительных страницах (/appeals, /search, /kvit, /receipt)
                    // Webvisor, clickmap и отслеживание ссылок принудительно отключены
                    w.yaCounter51197381 = new Ya.Metrika2({{
                        id: 51197381,
                        clickmap: !isSensitive,
                        trackLinks: !isSensitive,
                        accurateTrackBounce: true,
                        webvisor: enableWebvisor && !isSensitive
                    }});
                }} catch(e) {{ }}
            }});

            var n = d.getElementsByTagName("script")[0],
                s = d.createElement("script"),
                f = function () {{ n.parentNode.insertBefore(s, n); }};
            s.type = "text/javascript";
            s.async = true;
            s.src = "https://mc.yandex.ru/metrika/tag.js";

            if (w.opera == "[object Opera]") {{
                d.addEventListener("DOMContentLoaded", f, false);
            }} else {{ f(); }}
        }})(document, window, "yandex_metrika_callbacks2");
    }}

    window.krecAcceptAllCookies = function() {{
        storeConsent(true);
        var b = document.getElementById('krecCookieBanner');
        if (b) b.style.display = 'none';
        loadYandexMetrika(true);
    }};

    window.krecRejectCookies = function() {{
        storeConsent(false);
        var b = document.getElementById('krecCookieBanner');
        if (b) b.style.display = 'none';
    }};

    window.krecOpenCookieModal = function() {{
        var c = getStoredConsent();
        var chk = document.getElementById('krecConsentAnalyticsCheckbox');
        if (chk) chk.checked = !!(c && c.analytics);
        var modal = document.getElementById('krecCookieModal');
        if (modal) modal.style.display = 'flex';
    }};

    window.krecCloseCookieModal = function() {{
        var modal = document.getElementById('krecCookieModal');
        if (modal) modal.style.display = 'none';
    }};

    window.krecSaveCookieSettings = function() {{
        var chk = document.getElementById('krecConsentAnalyticsCheckbox');
        var allowed = chk ? chk.checked : false;
        storeConsent(allowed);
        krecCloseCookieModal();
        var b = document.getElementById('krecCookieBanner');
        if (b) b.style.display = 'none';
        if (allowed) {{
            loadYandexMetrika(true);
        }}
    }};

    document.addEventListener('DOMContentLoaded', function() {{
        var consent = getStoredConsent();
        if (!consent) {{
            var b = document.getElementById('krecCookieBanner');
            if (b) b.style.display = 'block';
        }} else if (consent.analytics) {{
            loadYandexMetrika(true);
        }}
    }});
}})();
</script>
</body>
</html>"""
