# База -> src: выгрузка РАСШИРЕНИЯ в XML.
# Первый запуск (нет src\ConfigDumpInfo.xml) — полная выгрузка, дальше инкрементальная.
# Ключ -Full принудительно делает полную.
param([switch]$Full)
. "$PSScriptRoot\common.ps1"
Assert-Base

$src = Join-Path $Root 'src'
if (-not (Test-Path -LiteralPath $src)) { New-Item -ItemType Directory -Path $src | Out-Null }

$cmd = @('/DumpConfigToFiles', $src, '-Extension', $EXT_NAME, '-format', 'Hierarchical')
if (-not $Full -and (Test-Path -LiteralPath (Join-Path $src 'ConfigDumpInfo.xml'))) {
	$cmd += @('-update', '-force')
	Write-Host "Инкрементальная выгрузка расширения «$EXT_NAME» в $src ..."
} else {
	Write-Host "Полная выгрузка расширения «$EXT_NAME» в $src ..."
}

$code = Invoke-Designer -CommandArgs $cmd -LogName 'dump.log'
if ($code -ne 0) {
	Write-Host "`n[ОШИБКА] Выгрузка не удалась (код $code). Подробности в dump.log"
	exit 1
}
Write-Host "`n[OK] Расширение выгружено: $src"
exit 0
