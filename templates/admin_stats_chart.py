# -*- coding: utf-8 -*-
import html


def _get_labeled_indices(daily_trend: list, target_count: int = 8) -> set:
    """Вычисляет гармоничный набор индексов для отображения подписей дат на оси X без наложения."""
    num_days = len(daily_trend)
    if num_days <= 14:
        return set(range(num_days))

    ideal_step = max(3, round(num_days / target_count))
    anchors = {0, num_days - 1}
    for idx, item in enumerate(daily_trend):
        d_str = str(item.get('date', ''))
        if d_str.endswith('-01'):
            anchors.add(idx)

    sorted_anchors = sorted(anchors)
    selected = set(anchors)

    for a_idx in range(len(sorted_anchors) - 1):
        left = sorted_anchors[a_idx]
        right = sorted_anchors[a_idx + 1]
        dist = right - left
        if dist >= 6:
            n_sub = round(dist / ideal_step)
            for k in range(1, n_sub):
                sub_pos = left + round((k * dist) / n_sub)
                if (right - sub_pos >= 2) and (sub_pos - left >= 2):
                    selected.add(sub_pos)
        elif dist >= 4:
            selected.add(left + dist // 2)

    return selected


_STATS_CHART_CSS = """
<style>
    .chart-group:hover rect.view-bar, .chart-group.active rect.view-bar { fill: #1d4ed8 !important; opacity: 1 !important; filter: drop-shadow(0 3px 6px rgba(37,99,235,0.35)); }
    .chart-group:hover rect.user-bar, .chart-group.active rect.user-bar { fill: #0284c7 !important; }
    .chart-group:hover text.bar-val, .chart-group.active text.bar-val { font-weight: 700 !important; fill: #0f172a !important; }
    .chart-group:hover rect.bar-col-bg, .chart-group.active rect.bar-col-bg { opacity: 1 !important; }

    .stats-chart-wrapper {
        position: relative;
        width: 100%;
        overflow-x: auto;
        padding-bottom: 8px;
    }

    .chart-tooltip {
        position: absolute;
        pointer-events: none;
        opacity: 0;
        transition: opacity 0.15s cubic-bezier(0.16, 1, 0.3, 1), transform 0.15s cubic-bezier(0.16, 1, 0.3, 1);
        background: rgba(15, 23, 42, 0.94);
        backdrop-filter: blur(8px);
        color: #fff;
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 12px;
        line-height: 1.4;
        box-shadow: 0 10px 25px -5px rgba(0,0,0,0.25), 0 8px 10px -6px rgba(0,0,0,0.2);
        z-index: 100;
        white-space: nowrap;
        min-width: 175px;
        border: 1px solid rgba(255,255,255,0.14);
    }
    .chart-tooltip.visible { opacity: 1; }
    .chart-tooltip.tooltip-top { transform: translate(-50%, -100%); }
    .chart-tooltip.tooltip-top::after {
        content: '';
        position: absolute;
        bottom: -6px;
        left: calc(50% + var(--arrow-shift, 0px));
        transform: translateX(-50%);
        border-width: 6px 6px 0;
        border-style: solid;
        border-color: rgba(15, 23, 42, 0.94) transparent transparent transparent;
    }
    .chart-tooltip.tooltip-bottom { transform: translate(-50%, 0); }
    .chart-tooltip.tooltip-bottom::after {
        content: '';
        position: absolute;
        top: -6px;
        left: calc(50% + var(--arrow-shift, 0px));
        transform: translateX(-50%);
        border-width: 0 6px 6px;
        border-style: solid;
        border-color: transparent transparent rgba(15, 23, 42, 0.94) transparent;
    }
</style>
"""

_STATS_TOOLTIP_SCRIPT = """
<script>
(function() {
    var tooltip = document.getElementById('statsChartTooltip');
    var card = document.getElementById('statsChartCard');
    var svg = document.getElementById('statsChartSvg');
    if (!tooltip || !card || !svg) return;

    var groups = svg.querySelectorAll('.chart-group');
    function showTooltip(group) {
        var dateStr = group.getAttribute('data-fulldate') || group.getAttribute('data-date') || '';
        var views = Number(group.getAttribute('data-views') || 0).toLocaleString('ru-RU');
        var visitors = Number(group.getAttribute('data-visitors') || 0).toLocaleString('ru-RU');
        var cx = Number(group.getAttribute('data-cx') || 0);
        var cy = Number(group.getAttribute('data-cy') || 0);

        tooltip.innerHTML = '<div style="font-size:12.5px;font-weight:700;color:#f8fafc;margin-bottom:6px;padding-bottom:5px;border-bottom:1px solid rgba(255,255,255,0.14);">' + dateStr + '</div>' +
            '<div style="display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:4px;">' +
                '<span style="display:flex;align-items:center;color:#94a3b8;"><span style="width:8px;height:8px;border-radius:2px;background:#2563eb;display:inline-block;margin-right:6px;"></span>Просмотры</span>' +
                '<span style="font-weight:700;color:#fff;font-size:13px;font-family:Consolas,monospace;">' + views + '</span>' +
            '</div>' +
            '<div style="display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:4px;">' +
                '<span style="display:flex;align-items:center;color:#94a3b8;"><span style="width:8px;height:8px;border-radius:2px;background:#38bdf8;display:inline-block;margin-right:6px;"></span>Уникальные</span>' +
                '<span style="font-weight:700;color:#38bdf8;font-size:13px;font-family:Consolas,monospace;">' + visitors + '</span>' +
            '</div>';

        var cardRect = card.getBoundingClientRect();
        var svgRect = svg.getBoundingClientRect();
        var scaleX = svgRect.width / 860.0;
        var scaleY = svgRect.height / 195.0;

        var colX = (svgRect.left - cardRect.left) + (cx * scaleX);
        var colY = (svgRect.top - cardRect.top) + (cy * scaleY);

        var tooltipHalfWidth = 90;
        var clampLeft = Math.max(tooltipHalfWidth + 10, Math.min(colX, cardRect.width - tooltipHalfWidth - 10));
        var arrowShift = colX - clampLeft;

        if (colY < 95) {
            tooltip.style.left = clampLeft + 'px';
            tooltip.style.top = (colY + 28) + 'px';
            tooltip.className = 'chart-tooltip tooltip-bottom visible';
        } else {
            tooltip.style.left = clampLeft + 'px';
            tooltip.style.top = (colY - 10) + 'px';
            tooltip.className = 'chart-tooltip tooltip-top visible';
        }
        tooltip.style.setProperty('--arrow-shift', arrowShift + 'px');

        groups.forEach(function(g) { g.classList.remove('active'); });
        group.classList.add('active');
    }

    function hideTooltip() {
        tooltip.className = 'chart-tooltip';
        groups.forEach(function(g) { g.classList.remove('active'); });
    }

    groups.forEach(function(g) {
        g.addEventListener('mouseenter', function() { showTooltip(g); });
        g.addEventListener('mouseleave', hideTooltip);
        g.addEventListener('focus', function() { showTooltip(g); });
        g.addEventListener('blur', hideTooltip);
        g.addEventListener('click', function(e) {
            e.stopPropagation();
            showTooltip(g);
        });
    });

    document.addEventListener('click', function(e) {
        if (!card.contains(e.target)) hideTooltip();
    });
})();
</script>
"""


def render_stats_chart_svg(daily_trend: list) -> str:
    """Генерирует интерактивный SVG-график динамики визитов по дням."""
    if not daily_trend:
        return '<div style="padding:40px;text-align:center;color:#64748b;">Нет накопленных данных за выбранный период</div>'

    chart_bars_html = []
    max_views = max([d.get('views', 0) for d in daily_trend] + [1])
    chart_width = 860
    chart_height = 195
    baseline = chart_height - 34
    num_days = len(daily_trend)
    pad_x = 16
    available_w = chart_width - pad_x * 2
    bar_gap = 6 if num_days > 14 else 10
    total_gaps = (num_days - 1) * bar_gap
    bar_width = max(14, int((available_w - total_gaps) / num_days))

    labeled_indices = _get_labeled_indices(daily_trend)

    for idx, item in enumerate(daily_trend):
        v_val = item.get('views', 0)
        u_val = item.get('visitors', 0)
        lbl = html.escape(item.get('label', ''))
        bar_h = max(4, int((v_val / max_views) * (baseline - 32))) if max_views > 0 else 4
        x = pad_x + idx * (bar_width + bar_gap)
        y = baseline - bar_h

        u_bar_h = max(2, int((u_val / max_views) * (baseline - 32))) if max_views > 0 else 2
        u_y = baseline - u_bar_h

        cx = x + bar_width / 2.0
        is_labeled = idx in labeled_indices
        d_str = str(item.get('date', ''))
        is_first_of_month = d_str.endswith('-01')
        is_last_day = (idx == num_days - 1)

        months_full_ru = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        try:
            _parts = [int(p) for p in d_str.split('-')]
            full_date_str = f"{_parts[2]} {months_full_ru[_parts[1]]} {_parts[0]}"
        except Exception:
            full_date_str = d_str

        if is_first_of_month:
            lbl_color = '#2563eb'
            lbl_weight = '700'
            tick_stroke = '#3b82f6'
            tick_width = '1.5'
        elif is_last_day:
            lbl_color = '#0f172a'
            lbl_weight = '600'
            tick_stroke = '#94a3b8'
            tick_width = '1.5'
        else:
            lbl_color = '#64748b'
            lbl_weight = '500'
            tick_stroke = '#cbd5e1'
            tick_width = '1'

        if is_labeled:
            tick_and_label_svg = f'''
            <line x1="{cx}" y1="{baseline}" x2="{cx}" y2="{baseline + 4}" stroke="{tick_stroke}" stroke-width="{tick_width}" />
            <text x="{cx}" y="{baseline + 18}" text-anchor="middle" font-size="11" font-weight="{lbl_weight}" fill="{lbl_color}" font-family="'Inter',sans-serif">{lbl}</text>
            '''
        else:
            tick_and_label_svg = f'''
            <circle cx="{cx}" cy="{baseline + 2}" r="1" fill="#cbd5e1" />
            '''

        chart_bars_html.append(f'''
        <g class="chart-group" tabindex="0" style="cursor:pointer;"
           data-date="{d_str}"
           data-fulldate="{full_date_str}"
           data-views="{v_val}"
           data-visitors="{u_val}"
           data-cx="{cx:.1f}"
           data-cy="{y:.1f}">
            <title>{d_str}: {u_val} уникальных посетителей, {v_val} просмотров</title>
            <rect class="bar-col-bg" x="{x - bar_gap/2}" y="10" width="{bar_width + bar_gap}" height="{baseline - 10}" rx="6" fill="#f1f5f9" opacity="0" style="transition:opacity 0.15s; pointer-events:none;"></rect>
            <rect class="view-bar" x="{x}" y="{y}" width="{bar_width}" height="{bar_h}" rx="3.5" fill="url(#blueGrad)" opacity="0.85">
                <animate attributeName="height" from="0" to="{bar_h}" dur="0.4s" fill="freeze" />
            </rect>
            <rect class="user-bar" x="{x + 1.5}" y="{u_y}" width="{max(3, bar_width - 3)}" height="{u_bar_h}" rx="2.5" fill="#38bdf8">
                <animate attributeName="height" from="0" to="{u_bar_h}" dur="0.5s" fill="freeze" />
            </rect>
            {tick_and_label_svg}
            <text class="bar-val" x="{cx}" y="{max(14, y - 6)}" text-anchor="middle" font-size="10" font-weight="600" fill="#1e293b" font-family="'Inter',sans-serif">{v_val if v_val > 0 else ''}</text>
        </g>
        ''')

    return f'''
    {_STATS_CHART_CSS}
    <div class="stats-chart-wrapper" id="statsChartWrapper">
        <svg id="statsChartSvg" viewBox="0 0 {chart_width} {chart_height}" width="100%" height="{chart_height}" style="min-width:650px;display:block;">
            <defs>
                <linearGradient id="blueGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stop-color="#2563eb" />
                    <stop offset="100%" stop-color="#3b82f6" />
                </linearGradient>
            </defs>
            <line x1="0" y1="{baseline}" x2="{chart_width}" y2="{baseline}" stroke="#e2e8f0" stroke-width="1.5" />
            <line x1="0" y1="{baseline // 2}" x2="{chart_width}" y2="{baseline // 2}" stroke="#f1f5f9" stroke-dasharray="4 4" />
            {''.join(chart_bars_html)}
        </svg>
    </div>
    {_STATS_TOOLTIP_SCRIPT}
    '''
