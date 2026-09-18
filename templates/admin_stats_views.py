# -*- coding: utf-8 -*-
"""
Шаблоны панели мониторинга посещаемости веб-портала ТОО «КРЭК» (/admin/stats).
Реализует эстетичный HeroUI дашборд с KPI-карточками, SVG-графиками динамики,
топом популярных страниц, распределением мобильных/ПК устройств и лентой визитов.
"""

import html
from typing import Any, Dict, Optional

from templates.admin_nav import _admin_nav_bar
from templates.admin_stats_chart import render_stats_chart_svg
from templates.icons import icon

_STATS_RESPONSIVE_CSS = """
<style>
    .stats-two-cols {
        display: grid;
        grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
        gap: 20px;
        margin-bottom: 24px;
    }
    .stats-kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 14px;
        margin-bottom: 24px;
    }
    @media (max-width: 900px) {
        .stats-two-cols {
            grid-template-columns: 1fr !important;
            gap: 16px !important;
        }
    }
    @media (max-width: 480px) {
        .stats-kpi-grid {
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
    }
</style>
"""


def render_admin_stats_dashboard(
    stats: Dict[str, Any],
    csrf_token: str = '',
    username: str = 'admin',
    message: Optional[str] = None,
    error: Optional[str] = None
) -> str:
    """Генерирует главный дашборд посещаемости сайта для администратора."""
    msg_html = f'<div class="msg-box" style="background:#ecfdf5;color:#065f46;border:1.5px solid #a7f3d0;padding:12px 18px;border-radius:10px;margin-bottom:20px;font-weight:600;display:flex;align-items:center;gap:10px;">{icon("check_circle", 18, "#059669")} {html.escape(message)}</div>' if message else ''
    err_html = f'<div class="msg-box" style="background:#fff1f2;color:#9f1239;border:1.5px solid #fecdd3;padding:12px 18px;border-radius:10px;margin-bottom:20px;font-weight:600;display:flex;align-items:center;gap:10px;">{icon("alert_triangle", 18, "#e11d48")} {html.escape(error)}</div>' if error else ''

    # Значения KPI
    u_today = stats.get('unique_today', 0)
    v_today = stats.get('views_today', 0)
    u_yesterday = stats.get('unique_yesterday', 0)
    v_yesterday = stats.get('views_yesterday', 0)
    u_week = stats.get('unique_week', 0)
    v_week = stats.get('views_week', 0)
    u_month = stats.get('unique_month', 0)
    v_month = stats.get('views_month', 0)
    mob_pct = stats.get('mobile_share_pct', 0.0)
    bot_today = stats.get('bot_views_today', 0)

    # 1. Построение SVG-графика динамики по дням
    daily_trend = stats.get('daily_trend', [])
    chart_svg = render_stats_chart_svg(daily_trend)

    # 2. Популярные страницы
    top_pages = stats.get('top_pages', [])
    top_pages_rows = []
    if top_pages:
        for idx, page in enumerate(top_pages, 1):
            p_path = html.escape(page.get('path', '/'))
            p_views = page.get('views', 0)
            p_visitors = page.get('visitors', 0)
            p_pct = page.get('pct', 0.0)

            title_alias = {
                '/': 'Главная страница',
                '/search': 'Поиск квитанций',
                '/kvit/': 'Сервис квитанций',
                '/tu': 'Технические условия',
                '/tarif': 'Тарифы и нормы',
                '/appeals': 'Подача обращений граждан',
                '/contacts': 'Контакты и реквизиты',
                '/zakupki': 'Закупки и тендеры',
                '/notices': 'Объявления потребителям',
                '/reports': 'Финансовая отчетность',
                '/history': 'История компании',
                '/leadership': 'Руководство',
                '/vacancies': 'Вакансии компании',
            }.get(p_path, '')

            alias_badge = f'<span style="font-size:12px;color:#64748b;font-weight:400;margin-left:6px;">({title_alias})</span>' if title_alias else ''

            top_pages_rows.append(f'''
            <tr style="border-bottom:1px solid #f1f5f9;transition:background 0.15s;">
                <td style="padding:10px 14px;color:#94a3b8;font-weight:600;">{idx}</td>
                <td style="padding:10px 14px;font-weight:600;color:#0f172a;">
                    <a href="{p_path}" target="_blank" style="color:#2563eb;text-decoration:none;">{p_path}</a>
                    {alias_badge}
                </td>
                <td style="padding:10px 14px;text-align:right;font-weight:700;color:#1e293b;font-family:Consolas,monospace;">{p_views:,}</td>
                <td style="padding:10px 14px;text-align:right;color:#0284c7;font-weight:600;font-family:Consolas,monospace;">{p_visitors:,}</td>
                <td style="padding:10px 14px;text-align:right;">
                    <span style="background:#eff6ff;color:#1d4ed8;padding:3px 8px;border-radius:6px;font-size:11.5px;font-weight:700;">{p_pct}%</span>
                </td>
            </tr>
            ''')
    else:
        top_pages_rows.append('<tr><td colspan="5" style="padding:20px;text-align:center;color:#64748b;">Нет данных за выбранный период</td></tr>')

    # 3. Устройства
    dev = stats.get('device_stats') or stats.get('devices', {})
    d_mob = dev.get('mobile', 0)
    d_desk = dev.get('desktop', 0)
    d_tab = dev.get('tablet', 0)
    dev_total = max(1, d_mob + d_desk + d_tab)
    mob_pct_calc = round((d_mob / dev_total) * 100, 1)
    desk_pct_calc = round((d_desk / dev_total) * 100, 1)
    tab_pct_calc = round((d_tab / dev_total) * 100, 1)

    # 4. Браузеры
    raw_browsers = stats.get('browser_stats') or stats.get('browsers', [])
    if isinstance(raw_browsers, dict):
        browsers = [{'browser': k, 'count': v} for k, v in raw_browsers.items()]
    elif isinstance(raw_browsers, list):
        browsers = [
            b if isinstance(b, dict) else ({'browser': b[0], 'count': b[1]} if isinstance(b, (list, tuple)) and len(b) >= 2 else {'browser': str(b), 'count': 1})
            for b in raw_browsers
        ]
    else:
        browsers = []

    browser_rows = []
    b_max = max([b.get('count', b.get('views', 0)) for b in browsers] + [1])
    for b in browsers[:5]:
        b_name = html.escape(b.get('browser', 'Неизвестно'))
        b_cnt = b.get('count', b.get('views', 0))
        b_pct = round((b_cnt / b_max) * 100) if b_max else 0
        browser_rows.append(f'''
        <div style="margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
                <span style="color:#334155;font-weight:600;">{b_name}</span>
                <span style="color:#64748b;font-weight:700;">{b_cnt:,}</span>
            </div>
            <div style="background:#f1f5f9;height:6px;border-radius:3px;overflow:hidden;">
                <div style="background:#3b82f6;height:100%;width:{b_pct}%;"></div>
            </div>
        </div>
        ''')

    # 5. Последние визиты
    recent_visits = stats.get('recent_visits', [])
    recent_rows = []
    for rv in recent_visits:
        rv_time = html.escape(rv.get('time_str') or rv.get('time', ''))
        rv_path = html.escape(rv.get('path', ''))
        rv_dev = rv.get('device_type') or rv.get('device', 'desktop')
        rv_dev_icon = 'phone' if rv_dev == 'mobile' else ('tablet' if rv_dev == 'tablet' else 'monitor')
        rv_browser = html.escape(rv.get('browser', ''))
        raw_ip = str(rv.get('ip_masked') or rv.get('ip_hash', ''))
        rv_ip_display = html.escape(raw_ip if (raw_ip.endswith('…') or raw_ip.endswith('...')) else f"{raw_ip[:10]}…")

        recent_rows.append(f'''
        <tr style="border-bottom:1px solid #f1f5f9;font-size:12.5px;">
            <td style="padding:8px 12px;color:#64748b;font-family:Consolas,monospace;white-space:nowrap;">{rv_time}</td>
            <td style="padding:8px 12px;font-weight:600;color:#1e293b;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{rv_path}</td>
            <td style="padding:8px 12px;font-family:Consolas,monospace;color:#94a3b8;font-size:11.5px;">{rv_ip_display}</td>
            <td style="padding:8px 12px;color:#475569;">
                <span style="display:inline-flex;align-items:center;gap:4px;">{icon(rv_dev_icon, 13, '#64748b')} {rv_dev}</span>
            </td>
            <td style="padding:8px 12px;color:#64748b;">{rv_browser}</td>
        </tr>
        ''')

    return f'''
    {_STATS_RESPONSIVE_CSS}
    <div class="card" style="max-width:1150px;margin:24px auto;">
        {_admin_nav_bar('stats', role='admin', username=username)}

        <!-- ШАПКА ДАШБОРДА -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;flex-wrap:wrap;gap:14px;">
            <div>
                <h1 style="font-size:22px;color:#1e293b;margin:0 0 4px;display:flex;align-items:center;gap:8px;">
                    {icon('trending_up', 24, '#2563eb')} Статистика посещаемости портала
                </h1>
                <p class="subtitle" style="margin:0;">Официальная статистика визитов портала ТОО «КРЭК» без использования сторонних счетчиков.</p>
            </div>
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
                <form action="/admin/stats/import-nginx" method="post" style="display:inline;">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
                    <button type="submit" class="btn btn-outline btn-sm" style="display:inline-flex;align-items:center;gap:6px;background:#f8fafc;border-color:#cbd5e1;color:#334155;" title="Синхронизировать данные из access.log веб-сервера Nginx">
                        {icon('download', 14, '#2563eb')} Импорт из Nginx
                    </button>
                </form>
                <a href="/admin/stats" class="btn btn-outline btn-sm" style="display:inline-flex;align-items:center;gap:6px;">
                    {icon('activity', 14, '#2563eb')} Обновить
                </a>
            </div>
        </div>

        {msg_html}
        {err_html}

        <!-- СЕТКА KPI-КАРТОЧЕК -->
        <div class="stats-kpi-grid">
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#eff6ff;color:#2563eb;display:flex;align-items:center;justify-content:center;">
                    {icon('users', 18, '#2563eb')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Сегодня</span>
                <div style="font-size:26px;font-weight:800;color:#1e293b;margin:6px 0 2px;">{u_today:,}</div>
                <div style="font-size:12.5px;color:#64748b;">{v_today:,} просмотров</div>
            </div>

            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#f8fafc;color:#64748b;display:flex;align-items:center;justify-content:center;">
                    {icon('clock', 18, '#64748b')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Вчера</span>
                <div style="font-size:26px;font-weight:800;color:#475569;margin:6px 0 2px;">{u_yesterday:,}</div>
                <div style="font-size:12.5px;color:#64748b;">{v_yesterday:,} просмотров</div>
            </div>

            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#f0fdf4;color:#16a34a;display:flex;align-items:center;justify-content:center;">
                    {icon('trending_up', 18, '#16a34a')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">За 7 дней</span>
                <div style="font-size:26px;font-weight:800;color:#16a34a;margin:6px 0 2px;">{u_week:,}</div>
                <div style="font-size:12.5px;color:#64748b;">{v_week:,} просмотров</div>
            </div>

            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#faf5ff;color:#9333ea;display:flex;align-items:center;justify-content:center;">
                    {icon('bar_chart', 18, '#9333ea')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">За 30 дней</span>
                <div style="font-size:26px;font-weight:800;color:#9333ea;margin:6px 0 2px;">{u_month:,}</div>
                <div style="font-size:12.5px;color:#64748b;">{v_month:,} просмотров</div>
            </div>

            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#fff7ed;color:#ea580c;display:flex;align-items:center;justify-content:center;">
                    {icon('phone', 18, '#ea580c')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Мобильные</span>
                <div style="font-size:26px;font-weight:800;color:#ea580c;margin:6px 0 2px;">{mob_pct}%</div>
                <div style="font-size:12.5px;color:#64748b;">доля смартфонов</div>
            </div>

            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#f8fafc;color:#64748b;display:flex;align-items:center;justify-content:center;">
                    {icon('shield_check', 18, '#64748b')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Роботы/Боты</span>
                <div style="font-size:26px;font-weight:800;color:#64748b;margin:6px 0 2px;">{bot_today:,}</div>
                <div style="font-size:12.5px;color:#64748b;">отсеяно за сегодня</div>
            </div>
        </div>

        <!-- ГРАФИК ДИНАМИКИ ПО ДНЯМ -->
        <div id="statsChartCard" style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:22px;margin-bottom:24px;box-shadow:0 1px 4px rgba(0,0,0,0.03);position:relative;">
            <div id="statsChartTooltip" class="chart-tooltip"></div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px;">
                <div>
                    <h3 style="margin:0 0 4px;font-size:16px;color:#1e293b;">Динамика визитов по дням</h3>
                    <p style="margin:0;font-size:12.5px;color:#64748b;">Синий столбец — общее число просмотров страниц, голубой — уникальные посетители.</p>
                </div>
                <div style="display:flex;gap:14px;align-items:center;font-size:12px;color:#64748b;">
                    <span style="display:inline-flex;align-items:center;gap:5px;">
                        <span style="width:10px;height:10px;background:#2563eb;border-radius:2px;display:inline-block;"></span> Просмотры
                    </span>
                    <span style="display:inline-flex;align-items:center;gap:5px;">
                        <span style="width:10px;height:10px;background:#38bdf8;border-radius:2px;display:inline-block;"></span> Уникальные посетители
                    </span>
                </div>
            </div>

            {chart_svg}
        </div>

        <!-- ДВЕ КОЛОНКИ: ТОП СТРАНИЦ И УСТРОЙСТВА/БРАУЗЕРЫ -->
        <div class="stats-two-cols">
            <!-- ТОП-10 СТРАНИЦ -->
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                <h3 style="margin:0 0 14px;font-size:16px;color:#1e293b;display:flex;align-items:center;gap:8px;">
                    {icon('list', 16, '#2563eb')} Популярные страницы (Топ-10)
                </h3>
                <div style="overflow-x:auto;">
                    <table style="width:100%;border-collapse:collapse;font-size:13.5px;">
                        <thead>
                            <tr style="background:#f8fafc;border-bottom:1.5px solid #e2e8f0;color:#64748b;text-align:left;font-size:12px;text-transform:uppercase;">
                                <th style="padding:8px 14px;">#</th>
                                <th style="padding:8px 14px;">Страница</th>
                                <th style="padding:8px 14px;text-align:right;">Просмотры</th>
                                <th style="padding:8px 14px;text-align:right;">Уникальные</th>
                                <th style="padding:8px 14px;text-align:right;">Доля</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(top_pages_rows)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- УСТРОЙСТВА И БРАУЗЕРЫ -->
            <div style="display:flex;flex-direction:column;gap:18px;">
                <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                    <h3 style="margin:0 0 14px;font-size:15px;color:#1e293b;display:flex;align-items:center;gap:8px;">
                        {icon('phone', 16, '#ea580c')} Типы устройств
                    </h3>

                    <div style="margin-bottom:12px;">
                        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
                            <span style="color:#334155;font-weight:600;">Смартфоны</span>
                            <span style="color:#ea580c;font-weight:700;">{mob_pct_calc}% ({d_mob:,})</span>
                        </div>
                        <div style="background:#f1f5f9;height:7px;border-radius:4px;overflow:hidden;">
                            <div style="background:#ea580c;height:100%;width:{mob_pct_calc}%;"></div>
                        </div>
                    </div>

                    <div style="margin-bottom:12px;">
                        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
                            <span style="color:#334155;font-weight:600;">Компьютеры и ноутбуки</span>
                            <span style="color:#2563eb;font-weight:700;">{desk_pct_calc}% ({d_desk:,})</span>
                        </div>
                        <div style="background:#f1f5f9;height:7px;border-radius:4px;overflow:hidden;">
                            <div style="background:#2563eb;height:100%;width:{desk_pct_calc}%;"></div>
                        </div>
                    </div>

                    <div>
                        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
                            <span style="color:#334155;font-weight:600;">Планшеты</span>
                            <span style="color:#10b981;font-weight:700;">{tab_pct_calc}% ({d_tab:,})</span>
                        </div>
                        <div style="background:#f1f5f9;height:7px;border-radius:4px;overflow:hidden;">
                            <div style="background:#10b981;height:100%;width:{tab_pct_calc}%;"></div>
                        </div>
                    </div>
                </div>

                <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                    <h3 style="margin:0 0 10px;font-size:15px;color:#1e293b;display:flex;align-items:center;gap:8px;">
                        {icon('code', 16, '#2563eb')} Популярные браузеры
                    </h3>
                    <div style="display:flex;flex-direction:column;">
                        {''.join(browser_rows) if browser_rows else '<div style="color:#64748b;font-size:13px;padding:8px 0;">Данные накапливаются</div>'}
                    </div>
                </div>
            </div>
        </div>

        <!-- ПОСЛЕДНИЕ ВИЗИТЫ В РЕАЛЬНОМ ВРЕМЕНИ -->
        <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
                <h3 style="margin:0;font-size:16px;color:#1e293b;display:flex;align-items:center;gap:8px;">
                    {icon('clock', 16, '#2563eb')} Последние визиты в реальном времени
                </h3>
                <span style="font-size:12px;color:#64748b;">Отображаются последние 15 переходов с защитой IP-адресов</span>
            </div>

            <div style="overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:13px;">
                    <thead>
                        <tr style="background:#f8fafc;border-bottom:1.5px solid #e2e8f0;color:#64748b;text-align:left;font-size:11.5px;text-transform:uppercase;">
                            <th style="padding:8px 12px;">Время</th>
                            <th style="padding:8px 12px;">Страница</th>
                            <th style="padding:8px 12px;">Хэш IP</th>
                            <th style="padding:8px 12px;">Тип</th>
                            <th style="padding:8px 12px;">Браузер</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(recent_rows)}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    '''
