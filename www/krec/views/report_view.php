<?php
/**
 * Шаблон для вывода одиночного отчета / инвестиционной программы / тарифа со ссылкой на скачивание
 * @var array $doc Метаданные документа из data/documents.json
 */
$pageTitle = htmlspecialchars($doc['title'] ?? 'ТОО КРЭК — Отчет');
$pageDesc = htmlspecialchars($doc['description'] ?? 'Карагандинская Региональная Энергетическая Компания');
$pageH1 = htmlspecialchars($doc['h1'] ?? $doc['title'] ?? 'Отчет');
$dateText = !empty($doc['date_text']) ? htmlspecialchars($doc['date_text']) : '';
$files = $doc['files'] ?? [];
?>
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="description" content="<?= $pageDesc ?>"/>
<title><?= $pageTitle ?></title>
<?php include (__DIR__ . '/../includes/header.html'); ?>

<h1><?= $pageH1 ?></h1>

<?php if ($dateText): ?>
    <p class="doc-date"><?= $dateText ?></p>
<?php endif; ?>

<div class="line"></div>

<?php if (!empty($files)): ?>
    <div class="doc-actions" style="margin: 20px 0; display: flex; flex-wrap: wrap; gap: 12px;">
        <?php foreach ($files as $file): ?>
            <?php 
                $fileName = basename($file);
                $fileUrl = '/files/' . rawurlencode($fileName);
            ?>
            <div class="buttom">
                <a href="<?= $fileUrl ?>" target="_blank" rel="noopener noreferrer">
                    Посмотреть документ (<?= htmlspecialchars($fileName) ?>)
                </a>
            </div>
        <?php endforeach; ?>
    </div>
<?php else: ?>
    <p>Документ временно недоступен для скачивания.</p>
<?php endif; ?>

<?php include (__DIR__ . '/../includes/footer.html'); ?>
