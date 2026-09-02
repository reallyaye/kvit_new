import html
import os

from templates.icons import icon


def _asset_v(rel_path: str) -> str:
    """Автоматический cache-buster: возвращает timestamp изменения файла."""
    try:
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', rel_path.lstrip('/'))
        return str(int(os.path.getmtime(full_path)))
    except Exception:
        return '20260901'


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
                <a href="/admin/pages" style="color:#cbd5e1;text-decoration:none;font-weight:600;display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:6px;transition:background .15s;">
                    {icon('file_text', 14, '#94a3b8')} Страницы
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
<html lang="ru">
<head>
<meta charset="utf-8" />
<meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, viewport-fit=cover">
<meta name="theme-color" content="#0f172a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="description" content="{escaped_desc}" />
<meta name="robots" content="index,follow">
<title>{escaped_title}</title>
<link rel="manifest" href="/manifest.json">
<link rel="stylesheet" href="/css/style.css?v={style_v}" type="text/css" />
<link rel="stylesheet" href="/css/heroui.css?v={heroui_v}" type="text/css" />
<link rel="shortcut icon" href="/favicon.ico?v={style_v}" type="image/vnd.microsoft.icon">
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
<!-- Yandex.Metrika counter -->
<script type="text/javascript" >
    (function (d, w, c) {{
        (w[c] = w[c] || []).push(function() {{
            try {{
                w.yaCounter51197381 = new Ya.Metrika2({{
                    id:51197381,
                    clickmap:true,
                    trackLinks:true,
                    accurateTrackBounce:true,
                    webvisor:true
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
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/51197381" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->

<div id="wrap">

<!-- ===== ШАПКА САЙТА ===== -->
<div id="header">
    <a href="/" class="header-brand">
        <img src="/images/logo.png?v=8" alt="ТОО КРЭК" class="header-logo-img" />
        <div class="header-titles">
            <span class="header-title-main">ТОО &laquo;КРЭК&raquo;</span>
            <span class="header-title-sub">Карагандинская Региональная Энергетическая Компания</span>
        </div>
    </a>
    <div class="header-right-actions">
        <a href="/kvit/" class="header-kvit-link">
            <svg class="svg-icon-stroke" width="16" height="16" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            <span>Квитанции онлайн</span>
        </a>
        <button class="mobile-nav-toggle" id="mobileNavToggle" aria-label="Открыть навигационное меню" aria-expanded="false" onclick="toggleMobileNav(event)">
            <span class="burger-icon-bars">
                <span></span><span></span><span></span>
            </span>
            <span class="mobile-nav-toggle-text">Меню</span>
        </button>
    </div>
</div>

<div class="mobile-nav-backdrop" id="mobileNavBackdrop" onclick="closeMobileNav()"></div>

<!-- ===== НАВИГАЦИОННОЕ МЕНЮ (НА ПК - ПОЛОСА, НА ТЕЛЕФОНЕ - ВЫПАДАЮЩЕЕ МЕНЮ) ===== -->
<div class="nav" id="portalNav">
    <ul>
        <li>
            <a href="/" class="{'active' if active_nav == 'home' else ''}" onclick="handleNavLinkClick(event, this)">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                <span>Главная</span>
            </a>
        </li>

        <li class="has-submenu">
            <div class="nav-item-row" onclick="toggleMobileSubmenu(event, this)">
                <a href="/reports" class="{'active' if active_nav == 'reports' else ''}" onclick="handleSubmenuParentClick(event, this)">
                    <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                    <span>Отчеты</span>
                </a>
                <button type="button" class="submenu-toggle-btn" aria-label="Раскрыть или скрыть подменю" onclick="toggleMobileSubmenu(event, this)">
                    {icon('chevron_down', 14, '#94a3b8')}
                </button>
            </div>
            <div class="underblock mega-menu-reports">
                <div class="mega-column">
                    <div class="mega-year-pill">
                        {icon('calendar', 13, '#38bdf8')} 2026 год
                    </div>
                    <div class="mega-section-label">
                        {icon('trending_up', 12, '#94a3b8')} Инвестиционная программа
                    </div>
                    <ul class="mega-list">
                        <li><a href="/invest-1-2026.php">{icon('file_text', 13, '#38bdf8')} <span>Отчет ИП 1 квартал 2026</span></a></li>
                        <li><a href="/invest-2-2026.php">{icon('file_text', 13, '#38bdf8')} <span>Отчет ИП 2 квартал 2026</span></a></li>
                    </ul>
                    <div class="mega-section-label" style="margin-top:10px;">
                        {icon('circle_dollar', 12, '#94a3b8')} Тарифная смета
                    </div>
                    <ul class="mega-list">
                        <li><a href="/isp_ts_2026_1.php">{icon('file_text', 13, '#38bdf8')} <span>Отчет ТС 1 полугодие 2026</span></a></li>
                    </ul>
                </div>

                <div class="mega-column">
                    <div class="mega-year-pill">
                        {icon('calendar', 13, '#38bdf8')} 2025 год
                    </div>
                    <div class="mega-section-label">
                        {icon('trending_up', 12, '#94a3b8')} Инвестиционная программа
                    </div>
                    <ul class="mega-list">
                        <li><a href="/invest-1-2025.php">{icon('file_text', 13, '#94a3b8')} <span>Отчет ИП 1 квартал 2025</span></a></li>
                        <li><a href="/invest-2-2025.php">{icon('file_text', 13, '#94a3b8')} <span>Отчет ИП 2 квартал 2025</span></a></li>
                        <li><a href="/invest-3-2025.php">{icon('file_text', 13, '#94a3b8')} <span>Отчет ИП 3 квартал 2025</span></a></li>
                        <li><a href="/invest-4-2025.php">{icon('file_text', 13, '#94a3b8')} <span>Отчет ИП 4 квартал 2025</span></a></li>
                    </ul>
                    <div class="mega-section-label" style="margin-top:10px;">
                        {icon('circle_dollar', 12, '#94a3b8')} Тарифная смета
                    </div>
                    <ul class="mega-list">
                        <li><a href="/isp_ts_2025_1.php">{icon('file_text', 13, '#94a3b8')} <span>Отчет ТС 1 полугодие 2025</span></a></li>
                    </ul>
                </div>

                <div class="mega-column">
                    <div class="mega-year-pill">
                        {icon('calendar', 13, '#38bdf8')} 2024 год
                    </div>
                    <div class="mega-section-label">
                        {icon('trending_up', 12, '#94a3b8')} Инвестиционная программа
                    </div>
                    <ul class="mega-list">
                        <li><a href="/invest-1-2024.php">{icon('file_text', 13, '#94a3b8')} <span>Отчет ИП 1 квартал 2024</span></a></li>
                        <li><a href="/invest-2-2024.php">{icon('file_text', 13, '#94a3b8')} <span>Отчет ИП 2 квартал 2024</span></a></li>
                        <li><a href="/invest-3-2024.php">{icon('file_text', 13, '#94a3b8')} <span>Отчет ИП 3 квартал 2024</span></a></li>
                        <li><a href="/invest-4-2024.php">{icon('file_text', 13, '#94a3b8')} <span>Отчет ИП 4 квартал 2024</span></a></li>
                    </ul>
                </div>

                <div class="mega-column mega-column-archive">
                    <div class="mega-archive-card">
                        <div class="mega-archive-badge">{icon('folder', 13, '#38bdf8')} Архив</div>
                        <div class="mega-archive-title">Отчетность прошлых лет</div>
                        <p class="mega-archive-desc">Полный архив отчетов по инвестпрограммам и тарифным сметам за период 2014–2026 гг.</p>
                        <a href="/reports" class="mega-archive-btn">
                            <span>Все отчеты</span>
                            {icon('chevron_right', 13, '#fff')}
                        </a>
                    </div>
                </div>
            </div>
        </li>

        <li class="has-submenu">
            <div class="nav-item-row" onclick="toggleMobileSubmenu(event, this)">
                <a href="/load" class="{'active' if active_nav in ('load', 'ktp', 'lines10kv', 'line') else ''}" onclick="handleSubmenuParentClick(event, this)">
                    <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                    <span>Загрузка ПС</span>
                </a>
                <button type="button" class="submenu-toggle-btn" aria-label="Раскрыть или скрыть подменю" onclick="toggleMobileSubmenu(event, this)">
                    {icon('chevron_down', 14, '#94a3b8')}
                </button>
            </div>
            <div class="underblock mega-menu-simple">
                <div class="mega-simple-column">
                    <div class="mega-simple-title">
                        {icon('zap', 14, '#38bdf8')} Пропускная способность сетей
                    </div>
                    <ul class="mega-list mega-simple-list">
                        <li>
                            <a href="/load">
                                <span class="menu-icon-box">{icon('hard_drive', 14, '#38bdf8')}</span>
                                <span class="menu-text-wrap">
                                    <span class="menu-link-title">Подстанции 35-110 кВ</span>
                                    <span class="menu-link-desc">Загрузка и резерв мощности трансформаторов</span>
                                </span>
                            </a>
                        </li>
                        <li>
                            <a href="/line">
                                <span class="menu-icon-box">{icon('activity', 14, '#38bdf8')}</span>
                                <span class="menu-text-wrap">
                                    <span class="menu-link-title">Линии 35-110 кВ</span>
                                    <span class="menu-link-desc">Высоковольтные воздушные линии электропередач</span>
                                </span>
                            </a>
                        </li>
                        <li>
                            <a href="/lines10kv">
                                <span class="menu-icon-box">{icon('zap', 14, '#38bdf8')}</span>
                                <span class="menu-text-wrap">
                                    <span class="menu-link-title">Линии 6-10 кВ</span>
                                    <span class="menu-link-desc">Распределительные кабельные и воздушные сети</span>
                                </span>
                            </a>
                        </li>
                        <li>
                            <a href="/ktp">
                                <span class="menu-icon-box">{icon('grid', 14, '#38bdf8')}</span>
                                <span class="menu-text-wrap">
                                    <span class="menu-link-title">КТП 6(10) кВ</span>
                                    <span class="menu-link-desc">Комплектные трансформаторные подстанции</span>
                                </span>
                            </a>
                        </li>
                    </ul>
                </div>
            </div>
        </li>

        <li>
            <a href="/tarif" class="{'active' if active_nav == 'tarif' else ''}" onclick="handleNavLinkClick(event, this)">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><line x1="12" y1="6" x2="12" y2="8"/><line x1="12" y1="16" x2="12" y2="18"/></svg>
                <span>Тарифы</span>
            </a>
        </li>

        <li>
            <a href="/zakup" class="{'active' if active_nav == 'zakup' else ''}" onclick="handleNavLinkClick(event, this)">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
                <span>Закупки</span>
            </a>
        </li>

        <li>
            <a href="/tu" class="{'active' if active_nav == 'tu' else ''}" onclick="handleNavLinkClick(event, this)">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                <span>Тех. условия</span>
            </a>
        </li>

        <li>
            <a href="/consumers" class="{'active' if active_nav in ('consumers', 'potreb') else ''}" onclick="handleNavLinkClick(event, this)">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                <span>Потребителям</span>
            </a>
        </li>

        <li>
            <a href="/notices" class="{'active' if active_nav in ('notices', 'notices_old', 'notices.php') else ''}" onclick="handleNavLinkClick(event, this)">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
                <span>Объявления</span>
            </a>
        </li>

        <li>
            <a href="/contacts" class="{'active' if active_nav == 'contacts' else ''}" onclick="handleNavLinkClick(event, this)">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                <span>Контакты</span>
            </a>
        </li>

        <li>
            <a href="/kvit/" class="nav-kvit {'active' if active_nav == 'kvit' else ''}" onclick="handleNavLinkClick(event, this)">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                <span>Электронные квитанции</span>
            </a>
        </li>
    </ul>
</div>

<!-- ===== ОСНОВНОЙ КОНТЕНТ ===== -->
<div class="content-container">
{content}
</div>

<!-- ===== ПОДВАЛ САЙТА ===== -->
<div id="footer">
    <div class="footer-links">
        <a href="/docs">Нормативные документы</a> &bull;
        <a href="/vacancy">Вакансии</a> &bull;
        <a href="/tbquest">Охрана труда и ТБ</a> &bull;
        <a href="/price">Прейскурант услуг</a> &bull;
        <a href="/kvit/">Электронные квитанции</a>
    </div>
    <div class="footer-copy">
        &copy; 2005&ndash;2026 ТОО &laquo;Карагандинская Региональная Энергетическая Компания&raquo; (ТОО &laquo;КРЭК&raquo;). Все права защищены.
    </div>
</div>

</div><!-- /#wrap -->

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

function toggleMobileSubmenu(e, elem) {{
    if (e) {{
        e.preventDefault();
        e.stopPropagation();
    }}
    const parentLi = elem ? elem.closest('li.has-submenu') : null;
    if (!parentLi) return;

    const wasOpen = parentLi.classList.contains('submenu-open');

    // Закрываем другие подменю
    document.querySelectorAll('.nav > ul > li.has-submenu.submenu-open').forEach(li => {{
        if (li !== parentLi) {{
            li.classList.remove('submenu-open');
        }}
    }});

    if (wasOpen) {{
        parentLi.classList.remove('submenu-open');
    }} else {{
        parentLi.classList.add('submenu-open');
    }}
}}

function handleSubmenuParentClick(e, link) {{
    if (window.innerWidth <= 1080) {{
        if (e) {{
            e.preventDefault();
            e.stopPropagation();
        }}
        toggleMobileSubmenu(e, link);
    }}
}}

function handleNavLinkClick(e, link) {{
    if (window.innerWidth <= 1080) {{
        closeMobileNav();
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
    document.querySelectorAll('#portalNav .underblock a').forEach(function(a) {{
        a.addEventListener('click', function() {{
            if (window.innerWidth <= 1080) {{
                closeMobileNav();
            }}
        }});
    }});
    try {{
        var saved = localStorage.getItem('krec_announce_lang');
        if (saved === 'ru') {{
            switchAnnouncementLang('ru');
        }}
    }} catch(e) {{}}
}});

function switchAnnouncementLang(lang) {{
    var kzElements = document.querySelectorAll('.announce-kz, #announcementKz');
    var ruElements = document.querySelectorAll('.announce-ru, #announcementRu');
    var kzBtns = document.querySelectorAll('.btn-announce-kz, #btnAnnounceKz');
    var ruBtns = document.querySelectorAll('.btn-announce-ru, #btnAnnounceRu');
    
    if (lang === 'ru') {{
        kzElements.forEach(function(el) {{ el.style.display = 'none'; }});
        ruElements.forEach(function(el) {{ el.style.display = 'block'; }});
        kzBtns.forEach(function(btn) {{ btn.classList.remove('active'); }});
        ruBtns.forEach(function(btn) {{ btn.classList.add('active'); }});
        try {{ localStorage.setItem('krec_announce_lang', 'ru'); }} catch(e) {{}}
    }} else {{
        ruElements.forEach(function(el) {{ el.style.display = 'none'; }});
        kzElements.forEach(function(el) {{ el.style.display = 'block'; }});
        ruBtns.forEach(function(btn) {{ btn.classList.remove('active'); }});
        kzBtns.forEach(function(btn) {{ btn.classList.add('active'); }});
        try {{ localStorage.setItem('krec_announce_lang', 'kz'); }} catch(e) {{}}
    }}
}}
</script>
</body>
</html>"""
