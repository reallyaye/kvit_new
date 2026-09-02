const CACHE_NAME = 'krek-portal-v3';
const OFFLINE_URL = '/offline.html';
const PRECACHE_ASSETS = [
    '/offline.html',
    '/css/style.css',
    '/images/logo.png',
    '/favicon.ico',
    '/manifest.json'
];

// Установка Service Worker и немедленная активация
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(async cache => {
            try {
                await cache.addAll(PRECACHE_ASSETS);
            } catch (err) {
                // Если какой-то ассет не загрузился, гарантированно кэшируем хотя бы offline.html
                try { await cache.add(OFFLINE_URL); } catch (e) {}
            }
        }).then(() => self.skipWaiting())
    );
});

// Активация и удаление старых версий кэша
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => {
            return Promise.all(
                keys.map(key => {
                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Перехват запросов (Fetch)
self.addEventListener('fetch', event => {
    const req = event.request;

    // Не перехватываем POST, WebSocket и админку
    if (req.method !== 'GET') {
        return;
    }

    // Для HTML навигации (переходы по страницам)
    if (req.mode === 'navigate' || (req.headers.get('accept') && req.headers.get('accept').includes('text/html'))) {
        event.respondWith(
            fetch(req).catch(async () => {
                const cache = await caches.open(CACHE_NAME);
                const cachedOffline = await cache.match(OFFLINE_URL, { ignoreSearch: true }) 
                                   || await caches.match('/offline.html', { ignoreSearch: true });
                if (cachedOffline) {
                    return cachedOffline;
                }
                // Прямой запрос из кэша
                const anyOffline = await caches.match(OFFLINE_URL);
                if (anyOffline) {
                    return anyOffline;
                }
                // Если кэш совсем пуст - генерируем полноценный красивый ответ с контактами
                return new Response(`<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/><title>Автономный режим — ТОО «КРЭК»</title><style>* { box-sizing: border-box; } body { font-family: system-ui, sans-serif; background: #f8fafc; color: #1e293b; margin: 0; padding: 20px; text-align: center; } .card { max-width: 600px; margin: 40px auto; background: #ffffff; border: 1px solid #cbd5e1; border-radius: 16px; padding: 30px 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); } h1 { font-size: 22px; color: #0f172a; margin-top: 10px; } p { color: #475569; font-size: 14.5px; line-height: 1.5; } .btn { display: inline-block; background: #2563eb; color: #fff; text-decoration: none; padding: 10px 22px; border-radius: 8px; font-weight: 600; cursor: pointer; border: none; margin: 15px 0; } .contacts { text-align: left; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-top: 20px; font-size: 13.5px; } .phone { color: #2563eb; font-weight: 700; text-decoration: none; display: block; margin: 4px 0 10px; }</style></head><body><div class="card"><div style="display:inline-block;background:#fef2f2;color:#b91c1c;padding:6px 14px;border-radius:20px;font-size:12px;font-weight:700;">НЕТ ПОДКЛЮЧЕНИЯ К СЕТИ</div><h1>Вы находитесь в автономном режиме</h1><p>Сайт ТОО «КРЭК» временно работает без интернета. Страница обновится автоматически при появлении сети.</p><button class="btn" onclick="window.location.reload()">Проверить соединение</button><div class="contacts"><strong>Контакты экстренных служб ТОО «КРЭК»:</strong><div style="margin-top:10px;"><span>Оперативно-диспетчерская служба (ОДС, круглосуточно):</span><a href="tel:+77212900358" class="phone">+7 (7212) 90-03-58</a><a href="tel:+77212900359" class="phone">+7 (7212) 90-03-59</a><span>Приёмная:</span><a href="tel:+77212900350" class="phone">+7 (7212) 90-03-50</a><span>По вопросам оплаты:</span><a href="tel:+77212900353" class="phone">+7 (7212) 90-03-53</a></div></div></div><script>window.addEventListener('online', function(){ window.location.reload(); });</script></body></html>`, {
                    headers: { 'Content-Type': 'text/html; charset=utf-8' }
                });
            })
        );
        return;
    }

    // Для статических файлов
    event.respondWith(
        caches.match(req, { ignoreSearch: true }).then(cachedRes => {
            if (cachedRes) {
                fetch(req).then(networkRes => {
                    if (networkRes && networkRes.status === 200) {
                        caches.open(CACHE_NAME).then(cache => cache.put(req, networkRes));
                    }
                }).catch(() => {});
                return cachedRes;
            }
            return fetch(req);
        })
    );
});
