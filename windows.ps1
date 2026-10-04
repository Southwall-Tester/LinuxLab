param(
    [ValidateSet('Start', 'Setup', 'Check')]
    [string]$Mode = 'Start',
    [string]$Distro = ''
)
# Windows PowerShell 5.1: distributed as UTF-8 with BOM.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

function Read-Distros {
    # WSL may emit UTF-16 NUL characters when captured by Windows PowerShell.
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = @(& $script:Wsl --list --quiet 2>$null)
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedPreference
    }
    if ($code -ne 0) { return @() }
    return @($lines | ForEach-Object { ($_ -replace "`0", '').Trim().Trim([char]0xFEFF) } | Where-Object { $_ })
}

function Install-Wsl {
    Write-Host '未找到可用的 Ubuntu/Debian。将调用 Windows 官方安装命令安装 Ubuntu。'
    Write-Host '如出现管理员授权窗口，请确认。下载可能需要几分钟；此步骤不修改已有 Linux 发行版。'
    # Arguments are constant. Keep the elevated helper hidden; status remains here.
    $installer = Start-Process -FilePath $script:Wsl -ArgumentList @('--install', '-d', 'Ubuntu', '--no-launch') -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    if ($installer.ExitCode -notin @(0, 3010)) {
        throw "WSL 安装未成功（退出码 $($installer.ExitCode)）。可在管理员 PowerShell 中运行 wsl --install -d Ubuntu 查看详细错误；参见 docs/SETUP.md。"
    }
    Write-Host ''
    Write-Host 'WSL 安装命令已完成，但首次配置还需要你参与：'
    Write-Host '1. 若 Windows 要求重启，先保存工作并自行重启。'
    Write-Host '2. 从开始菜单打开 Ubuntu，按提示创建 Linux 用户名和密码。'
    Write-Host '3. 再次双击安装环境.cmd，继续检查并安装实验依赖。'
    Write-Host '本次不会自动重启电脑；完成上面步骤前，不表示实验环境已就绪。'
}

try {
    $wslCommand = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $wslCommand) {
        throw '未找到 wsl.exe。请先按 docs/SETUP.md 安装 WSL；推荐 Windows 11，或 Windows 10 版本 2004/内部版本 19041 及以上。'
    }
    $script:Wsl = $wslCommand.Source
    $distros = @(Read-Distros)
    if ($Distro) {
        if ($Distro -notin $distros) { throw "未找到发行版 $Distro。请用 wsl --list --quiet 核对名称。" }
    } elseif ('Ubuntu' -in $distros) {
        $Distro = 'Ubuntu'
    } else {
        $preferred = @($distros | Where-Object { $_ -match '^Ubuntu-' })
        if ($preferred.Count -gt 0) { $Distro = $preferred[0] }
        elseif ('Debian' -in $distros) { $Distro = 'Debian' }
    }
    if (-not $Distro) {
        if ($Mode -eq 'Setup') {
            Install-Wsl
            exit 0
        }
        throw '没有找到 Ubuntu/Debian。请先双击安装环境.cmd。已有其他发行版可用 windows.ps1 -Distro 名称 显式选择。'
    }
    Write-Host "使用 WSL 发行版：$Distro"
    $setupOption = '--check'
    if ($Mode -eq 'Setup') { $setupOption = '--install' }
    # Pass paths as separate native arguments, never interpolate them into shell code.
    & $script:Wsl -d $Distro --cd $PSScriptRoot -- bash ./setup.sh $setupOption
    if ($LASTEXITCODE -ne 0) {
        throw '环境尚未就绪，请查看上方提示。首次使用需先打开 Ubuntu 创建用户；缺少软件请运行安装环境.cmd，其他问题见 docs/SETUP.md。'
    }
    if ($Mode -eq 'Start') {
        & $script:Wsl -d $Distro --cd $PSScriptRoot -- bash ./start.sh
        exit $LASTEXITCODE
    }
    if ($Mode -eq 'Setup') { Write-Host '准备完成。现在可以双击启动实验.cmd。' }
    exit 0
} catch {
    Write-Host "[LinuxLab] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
