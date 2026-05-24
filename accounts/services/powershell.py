from __future__ import annotations

from django.conf import settings

from .winrm_client import WinRMClient


def _psq(s: str) -> str:
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


def _ad_server_literal() -> str:
    return _psq(getattr(settings, "DC_HOST", "") or "")


def _server_params_block() -> str:
    return f"""
$serverHost = '{_ad_server_literal()}'
$adServerParams = @{{}}
if ($serverHost) {{
    $adServerParams['Server'] = $serverHost
}}
""".strip()


def _ad_user_params(properties: list[str], search_base: str | None = None) -> str:
    props = "@(" + ",".join([f"'{_psq(p)}'" for p in properties]) + ")"
    search_base = _psq(search_base if search_base is not None else (getattr(settings, "AD_USERS_SEARCH_BASE", "") or ""))
    return f"""
$adParams = @{{
    Filter = '*'
    Properties = {props}
}}
if ('{search_base}') {{
    $adParams['SearchBase'] = '{search_base}'
}}
""".strip()


def ps_check_login_exists(login: str) -> str:
    escaped_login = _psq(login)
    return f"""
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory
{_server_params_block()}
if (Get-ADUser -Filter "SamAccountName -eq '{escaped_login}'" @adServerParams) {{ 'YES' }} else {{ 'NO' }}
""".strip()


def ps_check_upn_exists(login: str) -> str:
    escaped_login = _psq(login)
    suf = _psq(settings.AD_UPN_SUFFIX)
    return f"""
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory
{_server_params_block()}
if (Get-ADUser -Filter "UserPrincipalName -eq '{escaped_login}{suf}'" @adServerParams) {{ 'YES' }} else {{ 'NO' }}
""".strip()


def ps_check_login_candidates(logins: list[str]) -> str:
    candidates = []
    seen = set()
    for login in logins:
        value = (login or "").strip().lower()
        if value and value not in seen:
            candidates.append(value)
            seen.add(value)

    if not candidates:
        candidates_ps = "@()"
    else:
        candidates_ps = "@( " + ",".join([f"'{_psq(c)}'" for c in candidates]) + " )"

    suffix = _psq(settings.AD_UPN_SUFFIX)
    return f"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Import-Module ActiveDirectory
{_server_params_block()}

$Candidates = {candidates_ps}
$Suffix = '{suffix}'
$result = @{{}}
foreach ($c in $Candidates) {{ $result[$c] = $false }}

if ($Candidates.Count -gt 0) {{
    $filterParts = New-Object System.Collections.Generic.List[string]
    foreach ($c in $Candidates) {{
        $safe = $c.Replace("'", "''")
        $safeUpn = ($c + $Suffix).Replace("'", "''")
        $filterParts.Add("SamAccountName -eq '$safe'")
        $filterParts.Add("UserPrincipalName -eq '$safeUpn'")
    }}
    $filter = $filterParts -join ' -or '
    $users = @(Get-ADUser -Filter $filter -Properties SamAccountName,UserPrincipalName @adServerParams)
    foreach ($u in $users) {{
        foreach ($c in $Candidates) {{
            if (($u.SamAccountName -ieq $c) -or ($u.UserPrincipalName -ieq ($c + $Suffix))) {{
                $result[$c] = $true
            }}
        }}
    }}
}}

$result.GetEnumerator() | Sort-Object Name | ForEach-Object {{
    [PSCustomObject]@{{ login = [string]$_.Key; exists = [bool]$_.Value }}
}} | ConvertTo-Json -Compress
""".strip()


def ps_check_ou_exists(ou_dn: str) -> str:
    dn = _psq(ou_dn)
    return f"""
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory
{_server_params_block()}
$identity = '{dn}'
try {{
    if ([string]::IsNullOrWhiteSpace($identity) -or ($identity -notmatch '^OU=.*?,DC=.*')) {{
        'NO|Укажите полный DistinguishedName OU'
        exit
    }}
    $ou = Get-ADOrganizationalUnit -Identity $identity @adServerParams -ErrorAction Stop
    if ($null -eq $ou) {{
        'NO|OU не найдена в Active Directory'
    }} else {{
        'YES|' + $ou.DistinguishedName
    }}
}} catch {{
    'NO|OU не найдена в Active Directory: ' + $_.Exception.Message
}}
""".strip()


def ps_check_ad_group_exists(identity: str) -> str:
    i = _psq(identity)
    return f"""
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory
{_server_params_block()}
try {{
  $obj = Get-ADGroup -Identity '{i}' -Properties sAMAccountName @adServerParams
  Write-Output ("YES|" + $obj.DistinguishedName + "|" + $obj.SamAccountName)
  exit 0
}} catch {{
  Write-Output ("NO|" + $_.Exception.Message)
  exit 1
}}
""".strip()


def ps_create_user(payload: dict) -> str:
    p = {k: _psq(str(v)) if v is not None else "" for k, v in payload.items()}
    groups = payload.get("groups", [])
    groups_ps = "@( " + ",".join([f"'{_psq(g)}'" for g in groups if str(g).strip()]) + ")"

    exp = payload.get("expiration_date")
    if exp:
        exp_ps = f"([datetime]'{_psq(exp)}').AddDays(1)"
        exp_block = f"Set-ADUser -Identity $NewUser.DistinguishedName -AccountExpirationDate {exp_ps} @adServerParams"
    else:
        exp_block = "# Срок действия не задан"

    fileshares = "1" if settings.FILESHARES_ENABLED else "0"
    logging = "1" if settings.LOGGING_ENABLED else "0"
    exchange = "1" if settings.EXCHANGE_ENABLED else "0"
    change_password_at_logon = "true" if payload.get("change_password_at_logon", False) else "false"

    script = f"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Import-Module ActiveDirectory
{_server_params_block()}

$Login = '{p['login']}'
$FullName = '{p['full_name']}'
$FirstName = '{p['first_name']}'
$LastName = '{p['last_name']}'
$MiddleName = '{p['middle_name']}'
$BirthDate = '{p['birth_date']}'
$Position = '{p['position']}'
$Department = '{p['department']}'
$Branch = '{p['branch_label']}'
$UPN = '{p['upn']}'
$PasswordPlain = '{p['password']}'
$ChangePasswordAtLogon = [bool]::Parse('{change_password_at_logon}')
$HomePage = '{_psq(settings.AD_HOME_PAGE)}'

if (Get-ADUser -Filter "SamAccountName -eq '$Login'" @adServerParams) {{ throw "Логин уже существует: $Login" }}
if (Get-ADUser -Filter "UserPrincipalName -eq '$UPN'" @adServerParams) {{ throw "UPN уже существует: $UPN" }}

$SecurePass = ConvertTo-SecureString $PasswordPlain -AsPlainText -Force
$TargetOU = '{p['target_ou_dn']}'
if ([string]::IsNullOrWhiteSpace($TargetOU)) {{ throw "Целевая OU не задана" }}
try {{
    Get-ADOrganizationalUnit -Identity $TargetOU @adServerParams | Out-Null
}} catch {{
    throw "Целевая OU не найдена в AD: $TargetOU. $($_.Exception.Message)"
}}

$CnName = "$FullName ($Login)"

$NewUser = New-ADUser -Name $CnName `
    -Path $TargetOU `
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
    -PassThru @adServerParams

# Отдельно устанавливаем флаг смены пароля на созданном объекте. Это важно,
# когда итоговый логин подобран автоматически и отличается от первого варианта.
if ($ChangePasswordAtLogon) {{
    Set-ADUser -Identity $Login -ChangePasswordAtLogon $true @adServerParams
}} else {{
    Set-ADUser -Identity $Login -ChangePasswordAtLogon $false @adServerParams
}}

$extOk = $false
try {{
    Get-ADUser $NewUser -Properties extensionAttribute10 @adServerParams | Out-Null
    $extOk = $true
}} catch {{
    $extOk = $false
}}

if ($extOk) {{
    Set-ADUser $NewUser -Add @{{extensionAttribute10 = $FirstName}} @adServerParams
    Set-ADUser $NewUser -Add @{{extensionAttribute11 = $MiddleName}} @adServerParams
    if ($BirthDate -ne '') {{ Set-ADUser $NewUser -Add @{{extensionAttribute12 = $BirthDate}} @adServerParams }}
    Set-ADUser $NewUser -Add @{{extensionAttribute14 = $Department}} @adServerParams
    Set-ADUser $NewUser -Add @{{extensionAttribute15 = $Position}} @adServerParams
}}
Set-ADUser $NewUser -Replace @{{"msDS-SupportedEncryptionTypes"=([System.Int64]$NewUser."msDS-SupportedEncryptionTypes" -bor 0x10)}} @adServerParams

$ProfilePath = '{p['profile_path']}'

if ('{p['branch_key']}' -eq 'hq') {{
    $HomeDirectory = '{p['home_directory']}'
    $DomainUser = '{_psq(settings.AD_DOMAIN_NETBIOS)}\' + $Login

    Set-ADUser -Identity $NewUser.DistinguishedName -ProfilePath $ProfilePath -HomeDrive 'Z:' -HomeDirectory $HomeDirectory @adServerParams

    if ({fileshares} -eq 1) {{
        try {{
            New-Item -Path $HomeDirectory -ItemType Directory -Force | Out-Null
        }} catch {{ }}

        if (-not (Test-Path -LiteralPath $HomeDirectory)) {{
            try {{
                $parts = $HomeDirectory -split [regex]::Escape('\')
            $shareName = $parts[3]
                $subPath = ($HomeDirectory -split [regex]::Escape('\'), 4)[3]
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
    Set-ADUser -Identity $NewUser.DistinguishedName -ProfilePath $ProfilePath @adServerParams
}}

{exp_block}

$Groups = {groups_ps}
foreach ($g in $Groups) {{
    if ([string]::IsNullOrWhiteSpace($g)) {{ continue }}
    try {{
        Get-ADGroup -Identity $g @adServerParams | Out-Null
    }} catch {{
        throw "AD-группа не найдена: $g. Укажите DN или sAMAccountName группы в настройках веб-сервиса. $($_.Exception.Message)"
    }}
    Add-ADGroupMember -Identity $g -Members $NewUser.DistinguishedName @adServerParams
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


def ps_get_inactive_users(days: int, search_base: str | None = None) -> str:
    days = int(days)
    return f"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Import-Module ActiveDirectory
{_server_params_block()}
{_ad_user_params(['DisplayName','SamAccountName','Enabled','lastLogon','whenCreated'], search_base)}

$today = (Get-Date).Date
$users = Get-ADUser @adParams @adServerParams |
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
""".strip()


def ps_unlock_user(login: str) -> str:
    escaped_login = _psq(login)
    return f"""
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory
{_server_params_block()}

$login = '{escaped_login}'
$u = Get-ADUser -Identity $login -Properties DisplayName,LockedOut @adServerParams
if (-not $u) {{ throw ('Пользователь не найден: ' + $login) }}

if ($u.LockedOut -eq $true) {{
    Unlock-ADAccount -Identity $u.DistinguishedName @adServerParams
    'OK|unlocked|' + $login
}} else {{
    'OK|not_locked|' + $login
}}
""".strip()


def ps_get_blocked_users(search_base: str | None = None) -> str:
    return f"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Import-Module ActiveDirectory
{_server_params_block()}
{_ad_user_params(['DisplayName','SamAccountName','Enabled','LockedOut','lockoutTime','lastLogon','whenCreated'], search_base)}

$users = Get-ADUser @adParams @adServerParams |
    Where-Object {{
        $_.Enabled -ne $false -and (
            $_.LockedOut -eq $true -or
            ($_.lockoutTime -and [int64]$_.lockoutTime -gt 0)
        )
    }}

$result = foreach ($u in $users) {{
    $locked = $false
    try {{
        $freshUser = Get-ADUser -Identity $u.DistinguishedName -Properties LockedOut,lockoutTime @adServerParams
        $locked = ($freshUser.LockedOut -eq $true) -or ($freshUser.lockoutTime -and [int64]$freshUser.lockoutTime -gt 0)
    }} catch {{
        $locked = ($u.LockedOut -eq $true) -or ($u.lockoutTime -and [int64]$u.lockoutTime -gt 0)
    }}
    if (-not $locked) {{ continue }}

    [PSCustomObject]@{{
        login = [string]$u.SamAccountName
        name = if ($u.DisplayName) {{ [string]$u.DisplayName }} else {{ [string]$u.SamAccountName }}
        status = 'Заблокирован'
        color = 'red'
        last_logon = if ($u.lastLogon -and [int64]$u.lastLogon -gt 0) {{ ([datetime]::FromFileTime([int64]$u.lastLogon)).ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
        created_at = if ($u.whenCreated) {{ ([datetime]$u.whenCreated).ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
    }}
}}

$result | Sort-Object status, login | ConvertTo-Json -Compress
""".strip()


def ps_get_ad_analytics(max_days: int = 10, search_base: str | None = None) -> str:
    max_days = int(max_days)
    return f"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Import-Module ActiveDirectory
{_server_params_block()}
{_ad_user_params(['DisplayName','SamAccountName','Enabled','PasswordNeverExpires','msDS-UserPasswordExpiryTimeComputed','lastLogon','whenCreated','LockedOut','lockoutTime'], search_base)}

$users = @(Get-ADUser @adParams @adServerParams)
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

    if ($u.Enabled -ne $false -and (($u.LockedOut -eq $true) -or ($u.lockoutTime -and [int64]$u.lockoutTime -gt 0))) {{
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
        search_base = '{_psq(search_base if search_base is not None else (getattr(settings, 'AD_USERS_SEARCH_BASE', '') or ''))}'
        inactive_source = 'lastLogon'
        inactive_scope = if ($serverHost) {{ $serverHost }} else {{ 'default_dc_context' }}
    }}
    expiry_users = @($expiryUsers | Sort-Object days, login)
    inactive_users = @($inactiveUsers | Sort-Object @{{Expression='days_inactive';Descending=$true}}, login)
    blocked_users = @($blockedUsers | Sort-Object login)
}}

$result | ConvertTo-Json -Depth 5 -Compress
""".strip()
