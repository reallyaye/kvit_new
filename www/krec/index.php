<?php
/**
 * Единая точка входа (Front Controller & Router) сайта ТОО «КРЭК»
 */

$requestUri = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
$route = trim($requestUri, '/');

// Дефолтный маршрут для главной страницы
if ($route === '' || $route === 'index.php' || $route === 'index.html') {
    require __DIR__ . '/pages/home.php';
    exit;
}

// 1. Проверка наличия страницы в папке pages/
$pageCandidate = $route;
if (!str_ends_with($pageCandidate, '.php')) {
    $pageCandidate .= '.php';
}

$pagePath = __DIR__ . '/pages/' . basename($pageCandidate);
if (file_exists($pagePath)) {
    require $pagePath;
    exit;
}

// 2. Проверка наличия в реестре документов (обратная совместимость всех старых URL)
$docsJsonPath = __DIR__ . '/data/documents.json';
if (file_exists($docsJsonPath)) {
    $docsRegistry = json_decode(file_get_contents($docsJsonPath), true) ?: [];
    $docKey = basename($route);
    if (!str_ends_with($docKey, '.php')) {
        $docKey .= '.php';
    }

    if (isset($docsRegistry[$docKey])) {
        $doc = $docsRegistry[$docKey];
        if (!empty($doc['iframes'])) {
            require __DIR__ . '/views/iframe_view.php';
        } else {
            require __DIR__ . '/views/report_view.php';
        }
        exit;
    }
}

// 3. 404 Not Found
http_response_code(404);
if (file_exists(__DIR__ . '/pages/404.php')) {
    require __DIR__ . '/pages/404.php';
} else {
    echo "<h1>404 Страница не найдена</h1>";
}
