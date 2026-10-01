"""Build the student handout without instructor walkthroughs or live state."""
from pathlib import Path
import hashlib
import json
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ['README.md', 'STUDENT.md', 'notes.md', 'AGENTS.md', 'VALIDATION.md',
         'start.sh', 'shellrc.sh', 'setup.sh', 'windows.ps1', 'orbit.py', 'lessons.py',
         '启动实验.cmd', '安装环境.cmd', '检查环境.cmd',
         'docs/SETUP.md', 'docs/AI-TUTOR.md', 'docs/DESIGN.md', 'research/SOURCES.md',
         'research/video-metadata.json']


def main():
    target = ROOT / 'dist'
    target.mkdir(exist_ok=True)
    package = target / 'orbit-lab-handout.tar.gz'
    hashes = {}
    with tarfile.open(package, 'w:gz', format=tarfile.PAX_FORMAT) as tar:
        for name in FILES:
            p = ROOT / name
            assert p.is_file(), name
            hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
            info = tar.gettarinfo(str(p), arcname='orbit-lab/' + name)
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mode = 0o755 if name.endswith('.sh') else 0o644
            with p.open('rb') as f:
                tar.addfile(info, f)
    windows_package = target / 'orbit-lab-handout.zip'
    with zipfile.ZipFile(windows_package, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            z.write(ROOT / name, 'orbit-lab/' + name)
    manifest = {'package': package.name, 'sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
                'windows_package': windows_package.name,
                'windows_sha256': hashlib.sha256(windows_package.read_bytes()).hexdigest(),
                'files': hashes, 'excluded': ['tests/', 'tools/', 'live sessions', 'research screenshots']}
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{package.name}: {package.stat().st_size} bytes; {len(FILES)} files')
    print(f'{windows_package.name}: {windows_package.stat().st_size} bytes; {len(FILES)} files')
    print('sha256=' + manifest['sha256'])


if __name__ == '__main__':
    main()
