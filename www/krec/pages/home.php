<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<meta name="description" content="ТОО КРЭК — Карагандинская Региональная Энергетическая Компания. Передача и распределение электроэнергии, электронные квитанции, технические условия."/>
<title>ТОО КРЭК — Карагандинская Региональная Энергетическая Компания</title>
<?php
    include ('header.html');
?>

<!-- ===== ГЛАВНЫЙ БАННЕР: ПОЛУЧИТЬ КВИТАНЦИЮ ===== -->
<div class="kvit-hero-banner">
    <div class="kvit-hero-info">
        <div class="kvit-badge">
            <svg class="svg-icon-stroke" width="14" height="14" viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            Онлайн-сервис для потребителей
        </div>
        <h2>Электронные квитанции за электроэнергию</h2>
        <p>Быстрый поиск, просмотр и скачивание квитанций в формате PDF по номеру лицевого счёта или адресу без очередей и регистрации.</p>
        <div class="kvit-hero-features">
            <span>
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                Поиск по счёту и адресу
            </span>
            <span>
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                Мгновенное скачивание PDF
            </span>
            <span>
                <svg class="svg-icon-stroke" width="15" height="15" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                Все периоды начислений
            </span>
        </div>
    </div>
    <div class="kvit-hero-actions">
        <a href="/kvit/" class="kvit-btn-primary">
            <svg class="svg-icon-stroke" width="18" height="18" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            Получить квитанцию
        </a>
        <a href="https://t.me/kreckvitbot" target="_blank" rel="noopener noreferrer" class="kvit-btn-secondary" title="Получить квитанцию в Telegram">
            <svg class="svg-icon-stroke" width="16" height="16" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            Через Telegram-бота
        </a>
    </div>
</div>

<!-- ===== BENTO GRID: ИНФОРМАЦИЯ О ПРЕДПРИЯТИИ ===== -->
<div class="bento-grid">
    <!-- О компании -->
    <div class="bento-card bento-col-8">
        <div class="bento-header">
            <div class="bento-icon-box">
                <svg class="svg-icon-stroke" width="20" height="20" viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            </div>
            <h2 class="bento-title">О компании ТОО &laquo;КРЭК&raquo;</h2>
        </div>
        <p>Карагандинская Региональная Энергетическая Компания приняла статус юридического лица в марте 2005 года. Основным видом деятельности является передача и распределение электрической энергии физическим и юридическим лицам Карагандинской области.</p>
        <p style="margin-bottom:0;">Общая территория обслуживания электрических сетей составляет <strong>98,347 тыс. км&sup2;</strong>. Протяженность воздушных линий электропередач превышает <strong>6 600 км</strong> с радиусом обслуживания <strong>550 км</strong>.</p>
    </div>

    <!-- Ключевые показатели -->
    <div class="bento-card bento-col-4">
        <div class="bento-header">
            <div class="bento-icon-box">
                <svg class="svg-icon-stroke" width="20" height="20" viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
            </div>
            <h2 class="bento-title">Масштаб сети</h2>
        </div>
        <div style="display:flex; flex-direction:column; gap:12px;">
            <div style="border-left:3px solid #2563eb; padding-left:12px;">
                <div style="font-size:20px; font-weight:800; color:#0f172a;">> 6 600 км</div>
                <div style="font-size:12.5px; color:#64748b;">Протяженность ЛЭП</div>
            </div>
            <div style="border-left:3px solid #38bdf8; padding-left:12px;">
                <div style="font-size:20px; font-weight:800; color:#0f172a;">98 347 км&sup2;</div>
                <div style="font-size:12.5px; color:#64748b;">Территория обслуживания</div>
            </div>
            <div style="border-left:3px solid #0f172a; padding-left:12px;">
                <div style="font-size:20px; font-weight:800; color:#0f172a;">6 районов</div>
                <div style="font-size:12.5px; color:#64748b;">Электросетевых РЭС</div>
            </div>
        </div>
    </div>

    <!-- Электросетевые районы (РЭС) -->
    <div class="bento-card bento-col-12">
        <div class="bento-header">
            <div class="bento-icon-box">
                <svg class="svg-icon-stroke" width="20" height="20" viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            </div>
            <h2 class="bento-title">Электросетевые районы (РЭС)</h2>
        </div>
        <p>В ТОО &laquo;КРЭК&raquo; применена территориальная схема управления. В состав входят 6 электросетевых районов, в каждый из которых входит от 1 до 5 сетевых участков:</p>
        <div class="res-grid">
            <div class="res-item">
                <svg class="svg-icon-stroke" width="16" height="16" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                Абайский РЭС
            </div>
            <div class="res-item">
                <svg class="svg-icon-stroke" width="16" height="16" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                Осакаровский РЭС
            </div>
            <div class="res-item">
                <svg class="svg-icon-stroke" width="16" height="16" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                Молодежный РЭС
            </div>
            <div class="res-item">
                <svg class="svg-icon-stroke" width="16" height="16" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                Нуринский РЭС
            </div>
            <div class="res-item">
                <svg class="svg-icon-stroke" width="16" height="16" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                Каркаралинский РЭС
            </div>
            <div class="res-item">
                <svg class="svg-icon-stroke" width="16" height="16" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                Егиндыбулакский РЭС
            </div>
        </div>
    </div>
</div>

<!-- Карточка со схемой сетей -->
<div class="card">
    <div class="bento-header">
        <div class="bento-icon-box">
            <svg class="svg-icon-stroke" width="20" height="20" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
        </div>
        <h2 class="bento-title">Общая схема электрических сетей ТОО &laquo;КРЭК&raquo;</h2>
    </div>
    <div style="border-radius:10px; overflow:hidden; border:1px solid #e2e8f0; margin-top:12px;">
        <a href="images/nets.png" target="_blank" title="Нажмите, чтобы открыть схему в полном размере">
            <img src="images/nets.png" alt="Схема электрических сетей КРЭК" style="width:100%; display:block; transition:opacity 0.2s;" onmouseover="this.style.opacity='0.95'" onmouseout="this.style.opacity='1'" />
        </a>
    </div>
</div>

<?php
    include ('footer.html');
?>
