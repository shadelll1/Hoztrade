# src -> база: загрузка РАСШИРЕНИЯ из XML, обновление БД, проверка модулей.
# Основная конфигурация (УНФ) при этом не трогается — перезаписывается только расширение.
# Ключ -Yes пропускает подтверждение.
param([switch]$Yes)
. "$PSScriptRoot\common.ps1"
Assert-Base

$src = Join-Path $Root 'src'
if (-not (Test-Path -LiteralPath (Join-Path $src 'Configuration.xml'))) {
	Write-Host "[ОШИБКА] Нет исходников расширения в $src — сначала dump.bat"
	exit 1
}

Write-Host ''
Write-Host "Будет ПЕРЕЗАПИСАНО расширение «$EXT_NAME» в базе $ONEC_FILEBASE_PATH"
Write-Host "Источник: $src"
Write-Host 'Конфигуратор и 1С:Предприятие должны быть закрыты.'
if (-not $Yes) {
	$ans = Read-Host 'Продолжить? (Y/N)'
	if ($ans -notmatch '^[YyДд]') { Write-Host 'Отменено.'; exit 0 }
}

# 1. Загрузка исходников в конфигурацию расширения
Write-Host "`n[1/3] Загрузка расширения из файлов ..."
$code = Invoke-Designer -LogName 'load.log' -CommandArgs @(
	'/LoadConfigFromFiles', $src, '-Extension', $EXT_NAME, '-format', 'Hierarchical')
if ($code -ne 0) { Write-Host "`n[ОШИБКА] Загрузка не удалась (код $code). Смотрите load.log"; exit 1 }

# 2. Применение расширения к базе (реструктуризация таблиц новых объектов)
Write-Host "`n[2/3] Обновление расширения в БД ..."
$code = Invoke-Designer -LogName 'load.log' -Append -CommandArgs @('/UpdateDBCfg', '-Extension', $EXT_NAME)
if ($code -ne 0) { Write-Host "`n[ОШИБКА] Обновление БД не удалось (код $code). Смотрите load.log"; exit 1 }

# 3. Проверка модулей: LoadConfigFromFiles код не компилирует — синтаксические ошибки ловятся только здесь
Write-Host "`n[3/3] Синтаксический контроль модулей расширения ..."
$code = Invoke-Designer -LogName 'load.log' -Append -CommandArgs @(
	'/CheckModules', '-ThinClient', '-Server', '-Extension', $EXT_NAME)
if ($code -ne 0) { Write-Host "`n[ОШИБКА] В модулях есть ошибки. Смотрите load.log"; exit 1 }

Write-Host "`n[OK] Расширение загружено, БД обновлена, модули без ошибок."
exit 0
