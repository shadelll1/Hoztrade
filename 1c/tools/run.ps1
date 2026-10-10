# Запуск Конфигуратора или 1С:Предприятия на базе проекта (без ожидания завершения).
# Использование: run.ps1 -Mode DESIGNER | ENTERPRISE
param([ValidateSet('DESIGNER', 'ENTERPRISE')][string]$Mode = 'ENTERPRISE')
. "$PSScriptRoot\common.ps1"
Assert-Base
$auth = @()
if ($ONEC_USER) { $auth = @('/N' + $ONEC_USER) }
$all = @($Mode, '/F', $ONEC_FILEBASE_PATH) + $auth
Start-Process -FilePath $V8 -ArgumentList (Format-ArgList $all)
exit 0
