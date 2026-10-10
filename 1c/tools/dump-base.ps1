# База -> base-src: выгрузка ОСНОВНОЙ конфигурации (УНФ 3.0) в XML — только для чтения.
# Нужна как справочник: структура типовых объектов, API БСП и УНФ, эталоны форм и модулей.
# В git не идёт (см. .gitignore). Запускать один раз и после каждого обновления УНФ.
# Полная выгрузка типовой занимает от 10 до 40 минут и 1-2 ГБ на диске.
. "$PSScriptRoot\common.ps1"
Assert-Base

$dst = Join-Path $Root 'base-src'
if (Test-Path -LiteralPath (Join-Path $dst 'ConfigDumpInfo.xml')) {
	$cmd = @('/DumpConfigToFiles', $dst, '-format', 'Hierarchical', '-update', '-force')
	Write-Host "Инкрементальная выгрузка основной конфигурации в $dst ..."
} else {
	if (-not (Test-Path -LiteralPath $dst)) { New-Item -ItemType Directory -Path $dst | Out-Null }
	$cmd = @('/DumpConfigToFiles', $dst, '-format', 'Hierarchical')
	Write-Host "Полная выгрузка основной конфигурации в $dst ..."
	Write-Host 'Это долго (10-40 минут). Окно не закрывать.'
}

$code = Invoke-Designer -CommandArgs $cmd -LogName 'dump-base.log'
if ($code -ne 0) {
	Write-Host "`n[ОШИБКА] Выгрузка не удалась (код $code). Подробности в dump-base.log"
	exit 1
}
Write-Host "`n[OK] Основная конфигурация выгружена: $dst"
exit 0
