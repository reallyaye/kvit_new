const CACHE_NAME = 'krek-portal-v1';
const OFFLINE_URL = '/offline.html';
const PRECACHE_ASSETS = [
    '/offline.html',
    '/css/style.css?v=8',
    '/images/logo.png?v=8',
    '/favicon.ico?v=8',
    '/manifest.json'
];

// Установка Service Worker и кэширование оффлайн-ресурсов
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(PRECACHE_ASSETS);
        }).then(() => self.skipWaiting())
    );
});

// Активация и очистка устаревших кэшей
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

    // Не перехватываем POST, WebSocket и админские действия
    if (req.method !== 'GET') {
        return;
    }

    // Для навигации (переходов по страницам сайта)
    if (req.mode === 'navigate' || (req.headers.get('accept') && req.headers.get('accept').includes('text/html'))) {
        event.respondWith(
            fetch(req).catch(async () => {
                const cache = await caches.open(CACHE_NAME);
                const cachedOffline = await cache.match(OFFLINE_URL);
                return cachedOffline || new Response('Оффлайн-режим ТОО КРЭК', {
                    headers: { 'Content-Type': 'text/html; charset=utf-8' }
                });
            })
        );
        return;
    }

    // Для статических ресурсов (CSS, изображения, фавикон)
    event.respondWith(
        caches.match(req).then(cachedRes => {
            if (cachedRes) {
                // Обновляем кэш в фоне
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
