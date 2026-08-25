<?php
/**
 * Шаблон для вывода схем подстанций, КТП, ЛЭП со встроенными просмотрщиками PDF/iframe
 * @var array $doc Метаданные документа из data/documents.json
 */
$pageTitle = htmlspecialchars($doc['title'] ?? 'ТОО КРЭК — Загрузка подстанций и сетей');
$pageDesc = htmlspecialchars($doc['description'] ?? 'Карагандинская Региональная Энергетическая Компания');
$pageH1 = htmlspecialchars($doc['h1'] ?? $doc['title'] ?? 'Схемы и загрузка');
$dateText = !empty($doc['date_text']) ? htmlspecialchars($doc['date_text']) : '';
$iframes = $doc['iframes'] ?? [];
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
    <p class="doc-date" style="font-weight: 600; color: #475569; margin: 10px 0 20px;"><?= $dateText ?></p>
<?php endif; ?>

<?php if (!empty($iframes)): ?>
    <div class="iframes-container" style="display: flex; flex-direction: column; gap: 30px; margin: 20px 0;">
        <?php foreach ($iframes as $iframeSrc): ?>
            <?php 
                $fileName = basename($iframeSrc);
                $cleanSrc = '/files/' . rawurlencode($fileName);
            ?>
            <div class="iframe-box" style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
                <div style="margin-bottom: 8px; font-weight: 500; color: #1e293b; display: flex; justify-content: space-between; align-items: center;">
                    <span><?= htmlspecialchars($fileName) ?></span>
                    <a href="<?= $cleanSrc ?>" target="_blank" style="font-size: 13px; color: #2563eb; text-decoration: underline;">Открыть в новой вкладке ↗</a>
                </div>
                <iframe src="<?= $cleanSrc ?>" width="100%" height="800" style="border: none; border-radius: 4px; background: #fff;"></iframe>
            </div>
        <?php endforeach; ?>
    </div>
<?php elseif (!empty($files)): ?>
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
    <p>Документ временно недоступен.</p>
<?php endif; ?>

<?php include (__DIR__ . '/../includes/footer.html'); ?>
