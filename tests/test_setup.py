"""Exercise dependency installation branches with fake apt/sudo in an isolated PATH."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

APP = Path(__file__).resolve().parents[1]


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='orbit-setup-test-')
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls.log'
        self.env = dict(os.environ, PATH=str(self.bin),
                        ORBIT_DATA_DIR=str(self.root / 'unused-data'),
                        TEST_BIN=str(self.bin), TEST_LOG=str(self.log))
        self.bash = shutil.which('bash')
        self.python = shutil.which('python3')
        self.vim = shutil.which('vim')
        for cmd in ['uname', 'dirname', 'env', 'python3', 'bash', 'ls', 'mkdir', 'cp', 'mv',
                    'rm', 'tar', 'gzip', 'cat', 'tail', 'chmod', 'top', 'vim']:
            (self.bin / cmd).symlink_to(shutil.which(cmd))
        self.script('sudo', 'printf "sudo %s\\n" "$*" >> "$TEST_LOG"\nexec "$@"\n')
        self.script('apt-get', '''printf 'apt-get %s\n' "$*" >> "$TEST_LOG"
if [[ "${TEST_APT_FAIL:-}" == "$1" ]]; then exit 42; fi
if [[ "$1" == install ]]; then
  /bin/ln -sf "$TEST_VIM" "$TEST_BIN/vim"
fi
''')
        self.env['TEST_VIM'] = self.vim

    def tearDown(self):
        self.temp.cleanup()

    def script(self, name, body):
        path = self.bin / name
        if path.is_symlink():
            path.unlink()
        path.write_text('#!' + self.bash + '\nset -eu\n' + body)
        path.chmod(0o755)

    def run_setup(self, mode, expected):
        p = subprocess.run([self.bash, str(APP / 'setup.sh'), mode], env=self.env,
                           text=True, capture_output=True, timeout=10)
        self.assertEqual(p.returncode, expected, p.stdout + p.stderr)
        self.assertFalse((self.root / 'unused-data').exists())
        return p.stdout + p.stderr

    def test_ready_install_does_not_invoke_apt_or_sudo(self):
        out = self.run_setup('--install', 0)
        self.assertIn('无需下载或安装', out)
        self.assertFalse(self.log.exists())

    def test_missing_check_only_has_no_install_side_effects(self):
        (self.bin / 'vim').unlink()
        self.assertIn('vim', self.run_setup('--check', 1))
        self.assertFalse(self.log.exists())

    def test_installs_missing_package_then_checks_again(self):
        (self.bin / 'vim').unlink()
        out = self.run_setup('--install', 0)
        lines = self.log.read_text()
        self.assertIn('apt-get update', lines)
        self.assertIn('apt-get install -y vim', lines)
        self.assertNotIn('coreutils', lines)
        self.assertIn('环境准备完成', out)

    def test_network_failure_does_not_claim_success(self):
        (self.bin / 'vim').unlink()
        self.env['TEST_APT_FAIL'] = 'update'
        out = self.run_setup('--install', 1)
        self.assertIn('软件源更新失败', out)
        self.assertNotIn('apt-get install', self.log.read_text())
        self.assertNotIn('环境准备完成', out)

    def test_package_failure_does_not_claim_success(self):
        (self.bin / 'vim').unlink()
        self.env['TEST_APT_FAIL'] = 'install'
        out = self.run_setup('--install', 1)
        self.assertIn('安装未完成', out)
        self.assertNotIn('环境准备完成', out)

    def test_missing_python_check_is_actionable(self):
        (self.bin / 'python3').unlink()
        out = self.run_setup('--check', 1)
        self.assertIn('python3', out)
        self.assertIn('setup.sh --install', out)
        self.assertFalse(self.log.exists())

    def test_old_python_is_not_reported_as_ready_after_apt(self):
        self.script('python3', 'exit 1\n')
        out = self.run_setup('--install', 1)
        self.assertIn('安装后仍不满足要求', out)
        self.assertIn('Python>=3.9', out)
        self.assertIn('apt-get install -y python3', self.log.read_text())
        self.assertNotIn('环境准备完成', out)

    def test_invalid_option_does_not_install(self):
        self.run_setup('--wrong', 2)
        self.assertFalse(self.log.exists())


if __name__ == '__main__':
    unittest.main()
