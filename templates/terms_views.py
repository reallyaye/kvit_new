# -*- coding: utf-8 -*-
"""
Представление страницы Условий использования официального веб-портала ТОО «КРЭК» (krec.kz).
"""

from templates.portal_layout import portal_layout


def render_terms_page(is_admin: bool = False) -> str:
    content = '''
    <div class="legal-page-container">
        <nav class="legal-breadcrumb" aria-label="Навигация">
            <a href="/">Главная</a>
            <span>/</span>
            <span>Условия использования</span>
        </nav>

        <header class="legal-header">
            <div class="legal-badge">Правила ресурса</div>
            <h1>Условия использования веб-портала krec.kz</h1>
            <p class="legal-subtitle">Редакция от 1 января 2026 года • ТОО «Карагандинская Региональная Энергетическая Компания»</p>
        </header>

        <div class="legal-content-card">
            <section class="legal-section">
                <h2>1. Общие положения</h2>
                <p>1.1. Настоящие Условия использования (далее — «Условия») регулируют порядок пользования официальным интернет-ресурсом <strong>krec.kz</strong> (далее — «Сайт»), принадлежащим Товариществу с ограниченной ответственностью «Карагандинская Региональная Энергетическая Компания» (БИН 031140001297, далее — «ТОО «КРЭК»»).</p>
                <p>1.2. Настоящий Сайт является официальным информационно-сервисным ресурсом региональной электросетевой компании и предназначен для информирования потребителей, предоставления счетов-квитанций за электроэнергию, подачи обращений и публикации сведений о тарифах, плановых работах и технологическом присоединении к сетям.</p>
                <p>1.3. Начало использования Сайта, включая просмотр страниц, поиск квитанций и направление обращений, означает полное и безоговорочное согласие пользователя с настоящими Условиями и <a href="/privacy" style="color:#2563eb;text-decoration:underline;">Политикой конфиденциальности</a>.</p>
            </section>

            <section class="legal-section">
                <h2>2. Порядок предоставления сервиса электронных квитанций</h2>
                <p>2.1. Сервис поиска и скачивания электронных квитанций предоставляется потребителям ТОО «КРЭК» на безвозмездной основе.</p>
                <p>2.2. Сайт <strong>не является интернет-магазином</strong>, не осуществляет дистанционную продажу товаров и не ведёт приём электронных платежей через сайт. Оплата начислений за электроэнергию производится потребителями самостоятельно через авторизованные платёжные организации (банки второго уровня, мобильные приложения, отделения почтовой связи и платёжные терминалы).</p>
                <p>2.3. Потребитель обязуется использовать сервис поиска квитанций добросовестно, не осуществлять автоматизированный сбор данных (парсинг) и не запрашивать сведения третьих лиц без законных полномочий.</p>
            </section>

            <section class="legal-section">
                <h2>3. Правила подачи обращений через Сайт</h2>
                <p>3.1. Электронная приёмная (<code>/appeals</code>) предназначена для оперативного взаимодействия потребителей с энергетической компанией.</p>
                <p>3.2. Срок рассмотрения обращений потребителей составляет <strong>до 15 рабочих дней</strong> со дня поступления в соответствии с нормами действующего законодательства Республики Казахстан (АППК РК).</p>
                <p>3.3. При подаче обращения заявитель обязуется указывать достоверные контактные данные для обратной связи. Обращения, содержащие ненормативную лексику, угрозы либо спам, рассмотрению не подлежат.</p>
            </section>

            <section class="legal-section">
                <h2>4. Интеллектуальная собственность и авторские права</h2>
                <p>4.1. Все материалы, размещённые на Сайте (включая тексты, схемы электрических сетей, производственные фотографии, фирменный логотип, дизайн и программный код), охраняются Законом Республики Казахстан «Об авторском праве и смежных правах».</p>
                <p>4.2. Использование, копирование или цитирование материалов Сайта в средствах массовой информации и на интернет-ресурсах допускается исключительно с обязательным указанием первоисточника и активной гиперссылкой на <strong>krec.kz</strong>.</p>
            </section>

            <section class="legal-section">
                <h2>5. Ограничение ответственности</h2>
                <p>5.1. ТОО «КРЭК» предпринимает все разумные меры для обеспечения точности и актуальности публикуемых сведений (графики ремонтных работ, тарифы, реестры загрузки подстанций).</p>
                <p>5.2. Оператор не несёт ответственности за перебои в работе Сайта, вызванные сбоями в сетях связи общего пользования, авариями у провайдеров хостинга либо обстоятельствами непреодолимой силы (форс-мажор).</p>
            </section>

            <section class="legal-section">
                <h2>6. Реквизиты и обратная связь</h2>
                <div class="legal-org-box">
                    <p><strong>ТОО «Карагандинская Региональная Энергетическая Компания»</strong></p>
                    <ul>
                        <li><strong>БИН:</strong> 031140001297</li>
                        <li><strong>Адрес:</strong> 100000, Республика Казахстан, Карагандинская область, г. Караганда, район имени Казыбек би, 108 учетный квартал, строение 7</li>
                        <li><strong>Канцелярия:</strong> +7 (7212) 90-03-50, 90-03-58</li>
                        <li><strong>Круглосуточная диспетчерская служба (ОДС):</strong> +7 (7212) 90-03-58, +7 (7212) 90-03-59</li>
                        <li><strong>Email:</strong> <a href="mailto:info@krec.kz">info@krec.kz</a></li>
                    </ul>
                </div>
            </section>
        </div>
    </div>

    <style>
    .legal-page-container {
        max-width: 980px;
        margin: 0 auto;
        padding: 24px 20px 60px;
        color: #0f172a;
        font-family: 'Inter', -apple-system, sans-serif;
    }
    .legal-breadcrumb {
        font-size: 13px;
        color: #64748b;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .legal-breadcrumb a {
        color: #2563eb;
        text-decoration: none;
    }
    .legal-breadcrumb a:hover {
        text-decoration: underline;
    }
    .legal-header {
        margin-bottom: 30px;
        padding-bottom: 20px;
        border-bottom: 1px solid #e2e8f0;
    }
    .legal-badge {
        display: inline-block;
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #0284c7;
        background: #e0f2fe;
        padding: 4px 12px;
        border-radius: 9999px;
        margin-bottom: 12px;
    }
    .legal-header h1 {
        font-size: 28px;
        line-height: 1.3;
        margin: 0 0 10px;
        color: #0f172a;
        font-weight: 800;
    }
    .legal-subtitle {
        font-size: 14px;
        color: #64748b;
        margin: 0;
    }
    .legal-content-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 36px 40px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
    }
    .legal-section {
        margin-bottom: 32px;
    }
    .legal-section:last-child {
        margin-bottom: 0;
    }
    .legal-section h2 {
        font-size: 19px;
        color: #1e293b;
        margin: 0 0 14px;
        padding-bottom: 8px;
        border-bottom: 1px solid #f1f5f9;
        font-weight: 700;
    }
    .legal-section p {
        font-size: 14.5px;
        line-height: 1.65;
        color: #334155;
        margin: 0 0 14px;
    }
    .legal-section ul {
        margin: 0 0 16px 20px;
        padding: 0;
        color: #334155;
    }
    .legal-section li {
        font-size: 14px;
        line-height: 1.6;
        margin-bottom: 8px;
    }
    .legal-org-box {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-left: 4px solid #2563eb;
        border-radius: 8px;
        padding: 16px 20px;
        margin: 16px 0 20px;
    }
    .legal-org-box p {
        margin: 0 0 10px;
        font-weight: 700;
        color: #1e293b;
    }
    .legal-org-box ul {
        margin: 0 0 0 18px;
    }
    @media (max-width: 768px) {
        .legal-content-card {
            padding: 24px 18px;
        }
        .legal-header h1 {
            font-size: 22px;
        }
    }
    </style>
    '''
    return portal_layout(
        content=content,
        title='Условия использования — ТОО «КРЭК»',
        description='Официальные условия использования информационного ресурса krec.kz ТОО «Карагандинская Региональная Энергетическая Компания».',
        active_nav='terms',
        is_admin=is_admin,
        current_slug='terms'
    )
