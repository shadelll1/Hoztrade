# Общие функции для скриптов 1С-части проекта Hoztrade (расширение к УНФ 3.0).
# Хранить в UTF-8 С BOM: Windows PowerShell 5.1 читает .ps1 без BOM как ANSI и портит кириллицу.

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Корень проекта — на уровень выше папки tools
$Root = Split-Path -Parent $PSScriptRoot

# --- Настройки ---------------------------------------------------------------
$cfgFile = Join-Path $Root '.1c-devbase.ps1'
if (-not (Test-Path -LiteralPath $cfgFile)) {
	Write-Host "[ОШИБКА] Не найден $cfgFile"
	Write-Host 'Скопируйте .1c-devbase.ps1.example в .1c-devbase.ps1 и проверьте пути.'
	exit 1
}
. $cfgFile

if (-not $EXT_NAME) { $EXT_NAME = 'ХозтрейдСайт' }

# --- Поиск платформы -----------------------------------------------------------
# Сначала путь из настроек; если его нет — самая новая установленная учебная (1cv8t),
# затем обычная (1cv8). Учебная конфигурация может поставить свою версию платформы — так она найдётся сама.
function Find-Platform {
	if ($ONEC_PATH -and (Test-Path -LiteralPath $ONEC_PATH)) { return $ONEC_PATH }
	$candidates = @()
	foreach ($pair in @(@('1cv8t', '1cv8t.exe'), @('1cv8', '1cv8.exe'))) {
		foreach ($pf in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
			if (-not $pf) { continue }
			$dir = Join-Path $pf $pair[0]
			if (-not (Test-Path -LiteralPath $dir)) { continue }
			Get-ChildItem -LiteralPath $dir -Directory |
				Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } |
				ForEach-Object {
					$exe = Join-Path $_.FullName ('bin\' + $pair[1])
					if (Test-Path -LiteralPath $exe) {
						$candidates += [pscustomobject]@{ Ver = [version]$_.Name; Exe = $exe }
					}
				}
		}
		if ($candidates.Count -gt 0) { break }   # учебная найдена — обычную не ищем
	}
	if ($candidates.Count -eq 0) {
		Write-Host '[ОШИБКА] Платформа 1С не найдена. Укажите $ONEC_PATH в .1c-devbase.ps1'
		exit 1
	}
	return ($candidates | Sort-Object Ver -Descending | Select-Object -First 1).Exe
}

$V8 = Find-Platform

function Assert-Base {
	# Проверяет, что файловая база существует.
	if (-not (Test-Path -LiteralPath (Join-Path $ONEC_FILEBASE_PATH '1Cv8.1CD'))) {
		Write-Host "[ОШИБКА] База не найдена: $ONEC_FILEBASE_PATH\1Cv8.1CD"
		Write-Host 'Путь к базе виден внизу окна запуска 1С при выделенной базе. Исправьте $ONEC_FILEBASE_PATH в .1c-devbase.ps1'
		exit 1
	}
}

function Format-ArgList {
	# Квотирует элементы с пробелами — Start-Process склеивает массив через пробел без кавычек.
	param([Parameter(Mandatory)][string[]]$Items)
	return ($Items | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } })
}

function Invoke-Designer {
	# Запускает Конфигуратор в пакетном режиме и ждёт завершения.
	# Параметры:
	#   CommandArgs - аргументы команды (/DumpConfigToFiles ... и т.п.)
	#   LogName     - имя лога в корне проекта (dump.log, load.log ...)
	#   Append      - дописать лог к существующему, а не перезаписать
	# Возвращает код возврата Конфигуратора (0 - успех).
	param(
		[Parameter(Mandatory)][string[]]$CommandArgs,
		[Parameter(Mandatory)][string]$LogName,
		[switch]$Append
	)
	$logFile = Join-Path $Root $LogName
	$tmpLog  = Join-Path $env:TEMP ('1c_' + [Guid]::NewGuid().ToString('N') + '.log')
	# Пароли учебная версия не поддерживает — /P не передаём никогда.
	# Имя пользователя (/N) нужно, если в базе заведены пользователи (в демо-базах они есть сразу).
	$auth = @()
	if ($ONEC_USER) { $auth = @('/N' + $ONEC_USER) }
	$all = @('DESIGNER', '/F', $ONEC_FILEBASE_PATH) + $auth + @('/DisableStartupDialogs', '/DisableStartupMessages') +
		$CommandArgs + @('/Out', $tmpLog, '-NoTruncate')
	$proc = Start-Process -FilePath $V8 -ArgumentList (Format-ArgList $all) -NoNewWindow -Wait -PassThru
	$text = ''
	if (Test-Path -LiteralPath $tmpLog) {
		$text = Get-Content -LiteralPath $tmpLog -Raw -Encoding UTF8
		Remove-Item -LiteralPath $tmpLog -Force -ErrorAction SilentlyContinue
	}
	if (-not $text) { $text = '' }
	$header = "===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  " + ($CommandArgs -join ' ') + "  (код $($proc.ExitCode))`r`n"
	if ($Append -and (Test-Path -LiteralPath $logFile)) {
		[System.IO.File]::AppendAllText($logFile, $header + $text + "`r`n", (New-Object System.Text.UTF8Encoding $true))
	} else {
		[System.IO.File]::WriteAllText($logFile, $header + $text + "`r`n", (New-Object System.Text.UTF8Encoding $true))
	}
	if ($text.Trim()) {
		Write-Host '--- Лог конфигуратора ---'
		Write-Host $text.TrimEnd()
		Write-Host '--- Конец лога ---'
	}
	return $proc.ExitCode
}

Write-Host "Платформа:  $V8"
Write-Host "База:       $ONEC_FILEBASE_PATH"
