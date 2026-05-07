from __future__ import annotations

from django.conf import settings

from .winrm_client import WinRMClient

def _psq(s: str) -> str:
    # Экранируем одинарные кавычки для PowerShell.
    return (s or "").replace("'", "''")

def client() -> WinRMClient:
    return WinRMClient(
        host=settings.DC_HOST,
        port=settings.DC_WINRM_PORT,
        username=settings.DC_WINRM_USER,
        password=settings.DC_WINRM_PASSWORD,
        transport=settings.DC_WINRM_TRANSPORT,
    )

def run_ps(script: str):
    return client().run_ps(script)

def _ad_user_params(properties: list[str]) -> str:
    props = "@(" + ",".join([f"'{_psq(p)}'" for p in properties]) + ")"
    search_base = _psq(getattr(settings, "AD_USERS_SEARCH_BASE", "") or "")
    return f"""
$adParams = @{{
    Filter = '*'
    Properties = {props}
}}
if ('{search_base}') {{
    $adParams['SearchBase'] = '{search_base}'
}}
""".strip()

def _ad_server_literal() -> str:
    return _psq(getattr(settings, "DC_HOST", "") or "")

def ps_check_login_exists(login: str) -> str:
    l = _psq(login)
    return (
        "Import-Module ActiveDirectory; "
        f"if (Get-ADUser -Filter \"SamAccountName -eq '{l}'\") {{ 'YES' }} else {{ 'NO' }}"
    )

def ps_check_upn_exists(login: str) -> str:
    l = _psq(login)
    suf = _psq(settings.AD_UPN_SUFFIX)
    return (
        "Import-Module ActiveDirectory; "
        f"if (Get-ADUser -Filter \"UserPrincipalName -eq '{l}{suf}'\") {{ 'YES' }} else {{ 'NO' }}"
    )


def ps_create_user(payload: dict) -> str:
    p = {k: _psq(str(v)) if v is not None else "" for k, v in payload.items()}
    groups = payload.get("groups", [])
    groups_ps = "@( " + ",".join([f"'{_psq(g)}'" for g in groups]) + ")"

    exp = payload.get("expiration_date")
    if exp:
        exp_ps = f"([datetime]'{_psq(exp)}').AddDays(1)"

        exp_block = f"Set-ADUser -Identity '{p['login']}' -AccountExpirationDate {exp_ps}"
    else:
        exp_block = "# Срок действия не задан"

    fileshares = "1" if settings.FILESHARES_ENABLED else "0"
    logging = "1" if settings.LOGGING_ENABLED else "0"
    exchange = "1" if settings.EXCHANGE_ENABLED else "0"

    script = f"""
$ErrorActionPreference = 'Stop'
# Включаем UTF-8, чтобы PowerShell корректно возвращал кириллицу.
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Import-Module ActiveDirectory

$Login = '{p['login']}'
$FullName = '{p['full_name']}'
$FirstName = '{p['first_name']}'
$LastName = '{p['last_name']}'
$MiddleName = '{p['middle_name']}'
$Gender = '{p['gender']}'
$BirthDate = '{p['birth_date']}'
$Position = '{p['position']}'
$Department = '{p['department']}'
$Branch = '{p['branch_label']}'
$UPN = '{p['upn']}'
$PasswordPlain = '{p['password']}'
$ChangePasswordAtLogon = [bool]::Parse('{str(payload.get('change_password_at_logon', False)).lower()}')
$HomePage = '{_psq(settings.AD_HOME_PAGE)}'

if (Get-ADUser -Filter "SamAccountName -eq '$Login'") {{ throw "Логин уже существует: $Login" }}

$SecurePass = ConvertTo-SecureString $PasswordPlain -AsPlainText -Force

$NewUser = New-ADUser -Name $FullName `
 `
    -GivenName $FirstName `
    -Surname $LastName `
    -DisplayName $FullName `
    -HomePage $HomePage `
    -SamAccountName $Login `
    -Company $Branch `
    -Department $Department `
    -Title $Position `
    -UserPrincipalName $UPN `
    -AccountPassword $SecurePass `
    -Enabled $true `
    -ChangePasswordAtLogon $ChangePasswordAtLogon `
    -PassThru

# Заполняем Exchange extensionAttribute*, если такие атрибуты есть в схеме AD.
$extOk = $false
try {{
    # Если extensionAttribute10 отсутствует в схеме — следующий вызов упадёт
    Get-ADUser $NewUser -Properties extensionAttribute10 | Out-Null
    $extOk = $true
}} catch {{
    $extOk = $false
}}

if ($extOk) {{
    Set-ADUser $NewUser -Add @{{extensionAttribute10 = $FirstName}}
    Set-ADUser $NewUser -Add @{{extensionAttribute11 = $MiddleName}}
    if ($BirthDate -ne '') {{ Set-ADUser $NewUser -Add @{{extensionAttribute12 = $BirthDate}} }}
    Set-ADUser $NewUser -Add @{{extensionAttribute13 = $Gender}}
    Set-ADUser $NewUser -Add @{{extensionAttribute14 = $Department}}
    Set-ADUser $NewUser -Add @{{extensionAttribute15 = $Position}}
}}
Set-ADUser $NewUser -Replace @{{"msDS-SupportedEncryptionTypes"=([System.Int64]$NewUser."msDS-SupportedEncryptionTypes" -bor 0x10)}}

$TargetOU = '{p['target_ou_dn']}'
$ProfilePath = '{p['profile_path']}'

if ('{p['branch_key']}' -eq 'hq') {{
    $HomeDirectory = '{p['home_directory']}'
    $DomainUser = '{_psq(settings.AD_DOMAIN_NETBIOS)}\\' + $Login

    Set-ADUser -Identity $NewUser.DistinguishedName -ProfilePath $ProfilePath -HomeDrive 'Z:' -HomeDirectory $HomeDirectory

    if ({fileshares} -eq 1) {{
        # Создание папки и права доступа (опционально). Пробуем через UNC, затем через локальный путь шара.
        try {{
            New-Item -Path $HomeDirectory -ItemType Directory -Force | Out-Null
        }} catch {{
            # Если UNC-путь недоступен, пробуем создать папку через локальный путь сетевой шары.
        }}

        if (-not (Test-Path -LiteralPath $HomeDirectory)) {{
            try {{
                # Определяем локальный путь сетевой шары на сервере.
                $shareName = ($HomeDirectory -split '\\')[3]
                $subPath = ($HomeDirectory -split '\\', 4)[3]
                $share = Get-SmbShare -Name $shareName -ErrorAction Stop
                $localPath = Join-Path $share.Path $subPath
                New-Item -Path $localPath -ItemType Directory -Force | Out-Null
                $HomeDirectory = $localPath
            }} catch {{
                throw "Не удалось создать домашнюю папку: $HomeDirectory. $($_.Exception.Message)"
            }}
        }}

        icacls $HomeDirectory /grant "${{DomainUser}}:(OI)(CI)(F)" | Out-Null
    }}
}} else {{
    Set-ADUser -Identity $NewUser.DistinguishedName -ProfilePath $ProfilePath
}}

Move-ADObject -Identity $NewUser.DistinguishedName -TargetPath $TargetOU

{exp_block}

$Groups = {groups_ps}
foreach ($g in $Groups) {{
    Add-ADGroupMember -Identity $g -Members $Login
}}

$Mailbox = ''
if ({exchange} -eq 1) {{
    $Session = $null
    try {{
        $exUser = '{_psq(settings.EXCHANGE_USER)}'
        $exPass = '{_psq(settings.EXCHANGE_PASSWORD)}' | ConvertTo-SecureString -AsPlainText -Force
        $cred = New-Object System.Management.Automation.PSCredential($exUser, $exPass)

        $Session = New-PSSession -ConfigurationName Microsoft.Exchange `
            -ConnectionUri '{_psq(settings.EXCHANGE_URI)}' `
            -Authentication '{_psq(settings.EXCHANGE_AUTH)}' `
            -Credential $cred
        Import-PSSession $Session -DisableNameChecking | Out-Null

        $SelectedMailbox = '{_psq(settings.MAILBOX_DB_BRANCH)}'
        if ('{p['branch_key']}' -eq 'hq' -or $Position -in @('Директор','Директор филиала')) {{
            $SelectedMailbox = '{_psq(settings.MAILBOX_DB_HQ)}'
        }}

        if ('{p['branch_key']}' -eq 'hq') {{
            Enable-Mailbox -Identity $Login -Database $SelectedMailbox
        }} else {{
            Enable-Mailbox -Identity $Login -Database $SelectedMailbox -PrimarySmtpAddress ($Login + '{_psq(settings.SMTP_SUFFIX_BRANCH)}')
        }}

        $MailboxObject = Get-Mailbox -Identity $Login
        $Mailbox = $MailboxObject.PrimarySmtpAddress.ToString()
    }} finally {{
        if ($Session) {{ Remove-PSSession $Session }}
    }}
}}

if ({logging} -eq 1) {{
    $executor = $env:USERNAME
    $entry = "$(Get-Date -Format 'dd.MM.yyyy HH:mm') - Выполнил: $executor, Создан: $FullName, Логин: $Login, Отдел: $Department, Филиал: $Branch"
    Add-Content -Path '{_psq(settings.LOG_FILE1)}' -Value $entry
    Add-Content -Path '{_psq(settings.LOG_FILE2)}' -Value $entry
}}

"OK|$Login|$UPN|$Mailbox"
"""
    return script.strip()



def ps_get_inactive_users(days: int) -> str:
    days = int(days)
    return f"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Import-Module ActiveDirectory
{_ad_user_params(['DisplayName','SamAccountName','Enabled','lastLogon','whenCreated'])}

$serverHost = '{_ad_server_literal()}'
if ($serverHost) {{
    $adParams['Server'] = $serverHost
}}

$today = (Get-Date).Date
$users = Get-ADUser @adParams |
    Where-Object {{
        $_.Enabled -eq $true -and
        $_.lastLogon -and [int64]$_.lastLogon -gt 0
    }}

$result = foreach ($u in $users) {{
    $lastLogon = [datetime]::FromFileTime([int64]$u.lastLogon)
    $daysInactive = ($today - $lastLogon.Date).Days
    if ($daysInactive -lt {days}) {{ continue }}

    [PSCustomObject]@{{
        login = [string]$u.SamAccountName
        name = if ($u.DisplayName) {{ [string]$u.DisplayName }} else {{ [string]$u.SamAccountName }}
        last_logon = $lastLogon.ToString('yyyy-MM-dd HH:mm:ss')
        days_inactive = $daysInactive
        created_at = if ($u.whenCreated) {{ ([datetime]$u.whenCreated).ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
    }}
}}

$result | Sort-Object @{{Expression='days_inactive';Descending=$true}}, login | ConvertTo-Json -Compress
"""

def ps_unlock_user(login: str) -> str:
    l = _psq(login)
    return f"""
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory

$login = '{l}'
$u = Get-ADUser -Identity $login -Properties DisplayName,LockedOut
if (-not $u) {{ throw ('Пользователь не найден: ' + $login) }}

if ($u.LockedOut -eq $true) {{
    Unlock-ADAccount -Identity $u.DistinguishedName
    'OK|unlocked|' + $login
}} else {{
    'OK|not_locked|' + $login
}}
""".strip()
def ps_get_blocked_users() -> str:
    return f"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Import-Module ActiveDirectory
{_ad_user_params(['DisplayName','SamAccountName','Enabled','LockedOut','lastLogon','whenCreated'])}

$serverHost = '{_ad_server_literal()}'
if ($serverHost) {{
    $adParams['Server'] = $serverHost
}}

$users = Get-ADUser @adParams |
    Where-Object {{ $_.Enabled -ne $false -and $_.LockedOut -eq $true }}

$result = foreach ($u in $users) {{
    $status = 'Заблокирован'
    $state = 'red'

    [PSCustomObject]@{{
        login = [string]$u.SamAccountName
        name = if ($u.DisplayName) {{ [string]$u.DisplayName }} else {{ [string]$u.SamAccountName }}
        status = $status
        color = $state
        last_logon = if ($u.lastLogon -and [int64]$u.lastLogon -gt 0) {{ ([datetime]::FromFileTime([int64]$u.lastLogon)).ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
        created_at = if ($u.whenCreated) {{ ([datetime]$u.whenCreated).ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
    }}
}}

$result | Sort-Object status, login | ConvertTo-Json -Compress
""".strip()

def ps_get_ad_analytics(max_days: int = 10) -> str:
    max_days = int(max_days)
    return f"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Import-Module ActiveDirectory
{_ad_user_params(['DisplayName','SamAccountName','Enabled','PasswordNeverExpires','msDS-UserPasswordExpiryTimeComputed','lastLogon','whenCreated','LockedOut'])}

$serverHost = '{_ad_server_literal()}'
if ($serverHost) {{
    $adParams['Server'] = $serverHost
}}

$users = @(Get-ADUser @adParams)
$now = Get-Date
$today = $now.Date

$expiryUsers = New-Object System.Collections.Generic.List[object]
$inactiveUsers = New-Object System.Collections.Generic.List[object]
$blockedUsers = New-Object System.Collections.Generic.List[object]

foreach ($u in $users) {{
    $login = [string]$u.SamAccountName
    $name = if ($u.DisplayName) {{ [string]$u.DisplayName }} else {{ $login }}

    if ($u.Enabled -eq $true -and $u.PasswordNeverExpires -ne $true -and $u."msDS-UserPasswordExpiryTimeComputed") {{
        $expiry = [datetime]::FromFileTime($u."msDS-UserPasswordExpiryTimeComputed")
        $days = [int][Math]::Floor(($expiry - $now).TotalDays)
        if ($days -le {max_days}) {{
            $expiryUsers.Add([PSCustomObject]@{{
                login = $login
                name = $name
                days = $days
                expiry_date = $expiry.ToString('yyyy-MM-dd HH:mm:ss')
            }})
        }}
    }}

    if ($u.Enabled -eq $true -and $u.lastLogon -and [int64]$u.lastLogon -gt 0) {{
        $lastLogon = [datetime]::FromFileTime([int64]$u.lastLogon)
        $daysInactive = ($today - $lastLogon.Date).Days
        if ($daysInactive -ge 6) {{
            $inactiveUsers.Add([PSCustomObject]@{{
                login = $login
                name = $name
                last_logon = $lastLogon.ToString('yyyy-MM-dd HH:mm:ss')
                days_inactive = $daysInactive
                created_at = if ($u.whenCreated) {{ ([datetime]$u.whenCreated).ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
            }})
        }}
    }}

    if ($u.Enabled -ne $false -and $u.LockedOut -eq $true) {{
        $blockedUsers.Add([PSCustomObject]@{{
            login = $login
            name = $name
            status = 'Заблокирован'
            color = 'red'
            last_logon = if ($u.lastLogon -and [int64]$u.lastLogon -gt 0) {{ ([datetime]::FromFileTime([int64]$u.lastLogon)).ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
            created_at = if ($u.whenCreated) {{ ([datetime]$u.whenCreated).ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
        }})
    }}
}}

$result = [PSCustomObject]@{{
    meta = [PSCustomObject]@{{
        scanned_users = $users.Count
        search_base = '{_psq(getattr(settings, 'AD_USERS_SEARCH_BASE', '') or '')}'
        inactive_source = 'lastLogon'
        inactive_scope = if ($serverHost) {{ $serverHost }} else {{ 'default_dc_context' }}
    }}
    expiry_users = @($expiryUsers | Sort-Object days, login)
    inactive_users = @($inactiveUsers | Sort-Object @{{Expression='days_inactive';Descending=$true}}, login)
    blocked_users = @($blockedUsers | Sort-Object login)
}}

$result | ConvertTo-Json -Depth 5 -Compress
""".strip()
