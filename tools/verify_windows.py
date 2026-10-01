"""Windows entry smoke tests; privileged install paths are mocked, never executed."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    records = []
    with tempfile.TemporaryDirectory(prefix='orbit-win-entry-') as temp:
        fake = Path(temp) / 'wsl-empty.cmd'
        fake.write_bytes(b'@echo off\r\nexit /b 0\r\n')
        env = dict(os.environ, ORBIT_SCRIPT=str(ROOT / 'windows.ps1'), ORBIT_FAKE_WSL=str(fake))
        cases = [
            ('missing_wsl', "function Get-Command { $null }; & $env:ORBIT_SCRIPT -Mode Check", 1, '未找到 wsl.exe'),
            ('no_distro_check', "function Get-Command { [pscustomobject]@{Source=$env:ORBIT_FAKE_WSL} }; & $env:ORBIT_SCRIPT -Mode Check", 1, '没有找到 Ubuntu/Debian'),
            ('install_needs_reboot', "function Get-Command { [pscustomobject]@{Source=$env:ORBIT_FAKE_WSL} }; function Start-Process { [pscustomobject]@{ExitCode=3010} }; & $env:ORBIT_SCRIPT -Mode Setup", 0, '首次配置还需要你参与'),
            ('install_failed', "function Get-Command { [pscustomobject]@{Source=$env:ORBIT_FAKE_WSL} }; function Start-Process { [pscustomobject]@{ExitCode=42} }; & $env:ORBIT_SCRIPT -Mode Setup", 1, 'WSL 安装未成功'),
            ('uac_denied', "function Get-Command { [pscustomobject]@{Source=$env:ORBIT_FAKE_WSL} }; function Start-Process { throw 'UAC denied' }; & $env:ORBIT_SCRIPT -Mode Setup", 1, 'UAC denied'),
        ]
        for name, code, expected, needle in cases:
            p = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', code],
                               env=env, capture_output=True, timeout=15)
            text = (p.stdout + p.stderr).decode('utf-8', errors='replace')
            assert p.returncode == expected and needle in text, (name, p.returncode, text)
            assert '准备完成。现在可以' not in text
            records.append({'name': name, 'passed': True, 'mode': 'mocked'})
        # Start the actual CMD in a temporary Linux data directory, then leave at phase 1.
        env['ORBIT_DATA_DIR'] = '/tmp/orbit-win-launch-' + uuid.uuid4().hex
        env['WSLENV'] = (env.get('WSLENV', '') + ':ORBIT_DATA_DIR/u').lstrip(':')
        launcher = ROOT / '启动实验.cmd'
        p = subprocess.run(['cmd.exe', '/d', '/c', str(launcher)], env=env, input=b'exit\r\n',
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=35)
        text = p.stdout.decode('utf-8', errors='replace')
        assert p.returncode == 0 and '本关工具' in text, (p.returncode, text)
        records.append({'name': 'actual_cmd_to_wsl_launch_and_exit', 'passed': True, 'mode': 'live'})
    target = ROOT / 'research/windows-setup-validation.json'
    target.write_text(json.dumps({'tests': records, 'fresh_wsl_install_tested': False},
                                 ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(records, indent=2))


if __name__ == '__main__':
    main()
