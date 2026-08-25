import html

def portal_layout(
    content: str,
    title: str = "ТОО КРЭК — Карагандинская Региональная Энергетическая Компания",
    description: str = "ТОО КРЭК — Карагандинская Региональная Энергетическая Компания. Передача и распределение электроэнергии, электронные квитанции, технические условия.",
    active_nav: str = "home"
) -> str:
    """Генерирует базовый HTML-макет информационного портала ТОО «КРЭК»."""
    escaped_title = html.escape(title)
    escaped_desc = html.escape(description)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{escaped_desc}" />
<meta name="robots" content="index,follow">
<title>{escaped_title}</title>
<link rel="stylesheet" href="/css/style.css" type="text/css" media="screen" />
<link rel="shortcut icon" href="/favicon.ico" type="image/vnd.microsoft.icon">
</head>
<body>
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
        <div class="header-logo-icon">
            <svg class="svg-icon-stroke" width="20" height="20" viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        </div>
        <div class="header-titles">
            <span class="header-title-main">ТОО &laquo;КРЭК&raquo;</span>
            <span class="header-title-sub">Карагандинская Региональная Энергетическая Компания</span>
        </div>
    </a>
    <a href="/kvit/" class="header-kvit-link">
        <svg class="svg-icon-stroke" width="16" height="16" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
        <span>Квитанции онлайн</span>
    </a>
</div>

<!-- ===== НАВИГАЦИОННОЕ МЕНЮ ===== -->
<div class="nav">
    <ul>
        <li>
            <a href="/" class="{'active' if active_nav == 'home' else ''}">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                Главная
            </a>
        </li>

        <li>
            <a href="/reports" class="{'active' if active_nav == 'reports' else ''}">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                Отчеты
            </a>
            <div class="underblock">
                <div class="block">
                    <ul>
                        <h1>2026 год</h1>
                        <h2>Инвестиционная программа</h2>
                        <li><a href="/invest-1-2026.php">Отчет ИП 1 квартал 2026</a></li>
                        <li><a href="/invest-2-2026.php">Отчет ИП 2 квартал 2026</a></li>
                        <h2>Тарифная смета</h2>
                        <li><a href="/isp_ts_2026_1.php">Отчет ТС 1 полугодие 2026</a></li>
                    </ul>
                </div>
                <div class="block">
                    <ul>
                        <h1>2025 год</h1>
                        <h2>Инвестиционная программа</h2>
                        <li><a href="/invest-1-2025.php">Отчет ИП 1 квартал 2025</a></li>
                        <li><a href="/invest-2-2025.php">Отчет ИП 2 квартал 2025</a></li>
                        <li><a href="/invest-3-2025.php">Отчет ИП 3 квартал 2025</a></li>
                        <li><a href="/invest-4-2025.php">Отчет ИП 4 квартал 2025</a></li>
                        <h2>Тарифная смета</h2>
                        <li><a href="/isp_ts_2025_1.php">Отчет ТС 1 полугодие 2025</a></li>
                    </ul>
                </div>
                <div class="block">
                    <ul>
                        <h1>2024 год</h1>
                        <h2>Инвестиционная программа</h2>
                        <li><a href="/invest-1-2024.php">Отчет ИП 1 квартал 2024</a></li>
                        <li><a href="/invest-2-2024.php">Отчет ИП 2 квартал 2024</a></li>
                        <li><a href="/invest-3-2024.php">Отчет ИП 3 квартал 2024</a></li>
                        <li><a href="/invest-4-2024.php">Отчет ИП 4 квартал 2024</a></li>
                    </ul>
                </div>
                <div class="block">
                    <ul>
                        <h1>Архив</h1>
                        <li><a href="/reports">Все отчеты за 2014–2026 гг.</a></li>
                    </ul>
                </div>
            </div>
        </li>

        <li>
            <a href="/load" class="{'active' if active_nav == 'load' else ''}">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                Загрузка ПС
            </a>
            <div class="underblock">
                <div class="block">
                    <ul>
                        <li><a href="/ktp">КТП 6(10) кВ</a></li>
                        <li><a href="/lines10kv">Линии 6-10 кВ</a></li>
                        <li><a href="/line">Линии 35-110 кВ</a></li>
                    </ul>
                </div>
            </div>
        </li>

        <li>
            <a href="/tarif" class="{'active' if active_nav == 'tarif' else ''}">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><line x1="12" y1="6" x2="12" y2="8"/><line x1="12" y1="16" x2="12" y2="18"/></svg>
                Тарифы
            </a>
        </li>

        <li>
            <a href="/zakup" class="{'active' if active_nav == 'zakup' else ''}">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
                Закупки
            </a>
        </li>

        <li>
            <a href="/tu" class="{'active' if active_nav == 'tu' else ''}">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                Тех. условия
            </a>
        </li>

        <li>
            <a href="/consumers" class="{'active' if active_nav == 'consumers' else ''}">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                Потребителям
            </a>
        </li>

        <li>
            <a href="/contacts" class="{'active' if active_nav == 'contacts' else ''}">
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                Контакты
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
</body>
</html>"""
