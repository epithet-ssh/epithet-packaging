import copy
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import metadata
import publish


def identity():
    return dict(tag='v1.2.3', source_commit='a' * 40, source_epoch=1700000000, recipe_digest='b' * 64)


def index(path, data, extra=None, files=False):
    prefix = 'epithet-1.2.3-1'
    package = metadata.asset_names('arch', data['tag'])[0]
    values = {'NAME': 'epithet', 'VERSION': '1.2.3-1', 'ARCH': 'x86_64',
              'FILENAME': package, 'SHA256SUM': data['assets'][package]}
    desc = '\n\n'.join(f'%{key}%\n{value}' for key, value in values.items()).encode()
    with tarfile.open(path, 'w:gz') as tar:
        entries = [(prefix + '/desc', desc)]
        if files:
            entries.append((prefix + '/files', b'%FILES%\nusr/bin/epithet\n'))
        for name, body in entries:
            member = tarfile.TarInfo(name)
            member.size = len(body)
            tar.addfile(member, io.BytesIO(body))
        if extra:
            tar.addfile(extra)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root / 'work/v1.2.3'
        self.release.mkdir(parents=True)
        metadata.write_json(self.release / 'release.json', identity())
        (self.release / 'source.tar.gz').write_bytes(b'source fixture')
        (self.release / 'source.sha256').write_text(metadata.sha256(self.release / 'source.tar.gz'))
        self.config = dict(public_root=str(self.root / 'public'), freebsd_abi='FreeBSD:15:amd64',
                           repository_url='https://packages.invalid', homepage='https://project.invalid',
                           arch_gnupg_home=str(self.root / 'key'))

    def artifacts(self, target):
        output = self.release / target
        output.mkdir(exist_ok=True)
        for name in metadata.asset_names(target, 'v1.2.3'):
            (output / name).write_bytes(name.encode())
        if target == 'arch':
            package = metadata.asset_names(target, 'v1.2.3')[0]
            data = dict(identity(), assets={package: metadata.sha256(output / package)})
            index(output / 'epithet.db.tar.gz', data)
            index(output / 'epithet.files.tar.gz', data, files=True)
        metadata.receipt(self.release, target)
        return metadata.verify(self.release, target)

    def test_versions_and_monotonic_publication(self):
        self.assertTrue(publish.should_publish('v1.9.0', 'v1.10.0'))
        self.assertFalse(publish.should_publish('v2.0.0', 'v1.10.0'))
        self.assertFalse(publish.should_publish('v1.2.3', 'v1.2.3'))
        for tag in ('1.2.3', 'v01.2.3', 'v1.2.3-rc1', '../../x', None):
            with self.assertRaises(ValueError):
                metadata.version(tag)

    def test_receipt_rejects_changed_source_artifact_and_identity(self):
        data = self.artifacts('arch')
        path = self.release / 'arch/manifest.json'
        for field, value in [('source_commit', 'c' * 40), ('recipe_digest', 'c' * 64),
                             ('tests', 'not-run'), ('target', 'macos')]:
            metadata.write_json(path, dict(data, **{field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                metadata.verify(self.release, 'arch')
        metadata.write_json(path, data)
        (self.release / 'arch/epithet.db.tar.gz').write_bytes(b'damaged')
        with self.assertRaises(ValueError):
            metadata.verify(self.release, 'arch')
        self.artifacts('arch')
        (self.release / 'source.tar.gz').write_bytes(b'changed source')
        with self.assertRaises(ValueError):
            metadata.verify(self.release, 'arch')

    def test_archive_is_reproducible_and_rejects_symlinks(self):
        source = self.root / 'source'
        source.mkdir()
        (source / 'file').write_bytes(b'source')
        for name in ('one.tar.gz', 'two.tar.gz'):
            metadata.archive(source, self.root / name, 1700000000)
            os.utime(source / 'file', (12345, 12345))
        self.assertEqual(metadata.sha256(self.root / 'one.tar.gz'), metadata.sha256(self.root / 'two.tar.gz'))
        (source / 'link').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):
            metadata.archive(source, self.root / 'bad.tar.gz', 1700000000)

    def test_worker_result_only_accepts_expected_regular_files(self):
        self.artifacts('arch')
        result = self.root / 'result.tar'
        with tarfile.open(result, 'w') as tar:
            for path in (self.release / 'arch').iterdir():
                tar.add(path, arcname=path.name)
        shutil.rmtree(self.release / 'arch')
        metadata.unpack_result(result, self.release)
        for name in ('../escape', 'manifest.json'):
            with tarfile.open(result, 'w') as tar:
                member = tarfile.TarInfo(name)
                member.type = tarfile.SYMTYPE
                member.linkname = '/etc/passwd'
                tar.addfile(member)
            with self.assertRaises(ValueError):
                metadata.unpack_result(result, self.release)
        self.assertFalse((self.root / 'escape').exists())

    def test_index_rejects_links_extra_packages_and_wrong_hash(self):
        data = self.artifacts('arch')
        path = self.release / 'arch/epithet.db.tar.gz'
        changed = copy.deepcopy(data)
        changed['assets'][metadata.asset_names('arch', data['tag'])[0]] = 'e' * 64
        with self.assertRaises(ValueError):
            publish.inspect_index(path, changed)
        for name in ('../escape', 'other-1/desc', 'epithet-1.2.3-1/desc'):
            member = tarfile.TarInfo(name)
            member.type = tarfile.SYMTYPE
            member.linkname = '/etc/passwd'
            index(path, data, extra=member)
            with self.assertRaises(ValueError):
                publish.inspect_index(path, data)

    def test_lock_excludes_another_process(self):
        lock = self.root / 'lock'
        with lock.open('w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            result = subprocess.run([sys.executable, str(ROOT / 'tools/lock.py'), str(lock), 'true'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        result = subprocess.run([sys.executable, str(ROOT / 'tools/lock.py'), str(lock), 'true'])
        self.assertEqual(result.returncode, 0)

    def test_immutable_package_cannot_be_replaced(self):
        source, target = self.root / 'source', self.root / 'package'
        source.write_bytes(b'one')
        publish.immutable_copy(source, target)
        source.unlink()
        source.write_bytes(b'two')
        with self.assertRaises(ValueError):
            publish.immutable_copy(source, target)
        self.assertEqual(target.read_bytes(), b'one')

    def test_failed_signing_preserves_current_then_retry_succeeds(self):
        data = self.artifacts('arch')
        work = self.release / 'arch'
        public = self.root / 'public/arch/x86_64'
        with patch.object(publish, 'sign', side_effect=RuntimeError('key unavailable')):
            with self.assertRaises(RuntimeError):
                publish.publish_arch(self.config, data, work)
            self.assertIsNone(publish.current_arch(public))
        def sign(config, path):
            Path(str(path) + '.sig').write_bytes(b'test signature')
        with patch.object(publish, 'sign', sign):
            publish.publish_arch(self.config, data, work)
        self.assertEqual(publish.current_arch(public), 'v1.2.3')
        self.assertTrue((public / 'epithet.db.sig').is_file())
        self.assertFalse(publish.needed(self.config, 'arch', identity()))
        with self.assertRaises(ValueError):
            publish.needed(self.config, 'arch', dict(identity(), source_commit='c' * 40))
        with patch.object(publish, 'sign', side_effect=AssertionError('must skip')):
            publish.publish_arch(self.config, data, work)

    def test_macos_failed_tap_push_does_not_promote_and_retry_reuses_bytes(self):
        data = self.artifacts('macos')
        work = self.release / 'macos'
        with patch.object(publish, 'run', side_effect=RuntimeError('tap push failed')):
            with self.assertRaises(RuntimeError):
                publish.publish_macos(self.config, data, work)
        self.assertIsNone(publish.current(self.config, 'macos')[0])
        archive = self.root / 'public/macos/releases/v1.2.3' / next(iter(data['assets']))
        before = archive.stat().st_ino
        with patch.object(publish, 'run'):
            publish.publish_macos(self.config, data, work)
        self.assertEqual(archive.stat().st_ino, before)
        self.assertEqual(publish.current(self.config, 'macos')[0], 'v1.2.3')
        self.assertTrue(publish.needed(self.config, 'arch', identity()))
        self.assertTrue(publish.needed(self.config, 'freebsd', identity()))
        self.assertEqual(data['tests'], 'not-run')

    def test_formula_urls_hashes_and_version_guard(self):
        data = self.artifacts('macos')
        formula = publish.formula(data, self.config['repository_url'], self.config['homepage'])
        self.assertNotIn('@@', formula)
        for name, digest in data['assets'].items():
            self.assertIn('/macos/releases/v1.2.3/' + name, formula)
            self.assertIn(digest, formula)
        path = self.root / 'epithet.rb'
        path.write_text(formula)
        metadata.check_tap(path, 'v1.2.3')
        with self.assertRaises(ValueError):
            metadata.check_tap(path, 'v1.2.2')
        if shutil.which('ruby'):
            subprocess.run(['ruby', '-c', str(path)], check=True, capture_output=True)

    def test_completed_poll_survives_recipe_update_but_rejects_moved_tag(self):
        with patch.object(publish, 'current', return_value=('v1.2.3', identity())):
            self.assertFalse(publish.pending(self.config, 'v1.2.3', 'a' * 40))
            with self.assertRaises(ValueError):
                publish.pending(self.config, 'v1.2.3', 'c' * 40)

    def git(self, directory, *args):
        return subprocess.check_output(['git', '-C', str(directory), *args], text=True, stderr=subprocess.DEVNULL).strip()

    def test_prepare_pins_tag_and_recipe_with_local_git(self):
        source = self.root / 'git'
        source.mkdir()
        self.git(source, 'init')
        self.git(source, 'config', 'user.name', 'Test')
        self.git(source, 'config', 'user.email', 'test@example.invalid')
        (source / 'file').write_text('one')
        self.git(source, 'add', '.')
        self.git(source, 'commit', '-m', 'initial')
        self.git(source, 'tag', 'v1.2.3')
        commit = self.git(source, 'rev-parse', 'HEAD')
        env = dict(SOURCE_CACHE=str(source / '.git'), WORK_ROOT=str(self.root / 'prepared'))
        with patch.dict(os.environ, env):
            metadata.prepare('v1.2.3', commit)
            metadata.prepare('v1.2.3', commit)
            with self.assertRaises(ValueError):
                metadata.prepare('v1.2.3', '0' * 40)
            with patch.object(metadata, 'recipe_digest', return_value='c' * 64), self.assertRaises(ValueError):
                metadata.prepare('v1.2.3', commit)

    def test_shell_targets_start_together_and_failure_does_not_block_others(self):
        # Real coordinator with fake target commands. Each job waits for all
        # three start markers; serialized execution fails the bounded wait.
        root = self.root / 'pipeline'
        for directory in ('bin', 'scripts', 'tools'):
            (root / directory).mkdir(parents=True)
        shutil.copy(ROOT / 'bin/epithet-release', root / 'bin/epithet-release')
        shutil.copy(ROOT / 'scripts/common.sh', root / 'scripts/common.sh')
        shutil.copy(ROOT / 'tools/lock.py', root / 'tools/lock.py')
        (root / 'tools/publish.py').write_text('import sys\n')
        source = root / 'scripts/source.sh'
        source.write_text('#!/bin/sh\nexit 0\n')
        source.chmod(0o755)
        for target in ('freebsd', 'arch', 'macos'):
            script = root / f'scripts/{target}.sh'
            script.write_text('''#!/bin/sh
set -eu
name=$(basename "$0" .sh)
touch "$WORK_ROOT/$name.started"
n=0
while [ ! -f "$WORK_ROOT/freebsd.started" ] || [ ! -f "$WORK_ROOT/arch.started" ] || [ ! -f "$WORK_ROOT/macos.started" ]; do
    n=$((n+1)); [ "$n" -lt 100 ] || exit 99
    sleep .02
done
[ "$name" != arch ] || exit 23
touch "$WORK_ROOT/$name.finished"
''')
            script.chmod(0o755)
        env = dict(os.environ, WORK_ROOT=str(self.root / 'work'), PYTHON=sys.executable,
                   EPITHET_PACKAGING_CONFIG=str(self.root / 'absent'))
        env.pop('PACKAGING_ROOT', None)
        result = subprocess.run(['sh', str(root / 'bin/epithet-release'), 'release', 'v1.2.3', 'a' * 40],
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('arch FAILED', result.stdout)
        for target in ('freebsd', 'macos'):
            self.assertTrue((self.root / f'work/{target}.finished').exists(), result.stdout + result.stderr)

    def test_tap_retry_pushes_existing_commit_without_duplicate_commit(self):
        origin = self.root / 'tap.git'
        subprocess.run(['git', 'init', '--bare', str(origin)], check=True, capture_output=True)
        checkout = self.root / 'tap'
        self.git(self.root, 'clone', str(origin), str(checkout))
        self.git(checkout, 'config', 'user.name', 'Test')
        self.git(checkout, 'config', 'user.email', 'test@example.invalid')
        self.git(checkout, 'checkout', '-b', 'main')
        (checkout / 'Formula').mkdir()
        (checkout / 'Formula/epithet.rb').write_text('class Epithet < Formula\n  version "1.2.2"\nend\n')
        self.git(checkout, 'add', '.')
        self.git(checkout, 'commit', '-m', 'initial')
        self.git(checkout, 'push', 'origin', 'main')
        before = self.git(checkout, 'rev-parse', 'HEAD')
        data = self.artifacts('macos')
        (self.release / 'macos/epithet.rb').write_text(publish.formula(data, self.config['repository_url'], self.config['homepage']))
        hook = origin / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        env = dict(os.environ, TAP_URL=str(origin), TAP_CHECKOUT=str(checkout), TAP_BRANCH='main',
                   PYTHON=sys.executable, EPITHET_PACKAGING_CONFIG=str(self.root / 'absent'))
        env.pop('PACKAGING_ROOT', None)
        command = ['sh', str(ROOT / 'scripts/tap.sh'), str(self.release)]
        first = subprocess.run(command, env=env, text=True, capture_output=True)
        self.assertNotEqual(first.returncode, 0)
        committed = self.git(checkout, 'rev-parse', 'HEAD')
        self.assertNotEqual(committed, before)
        self.assertEqual(self.git(origin, 'rev-parse', 'refs/heads/main'), before)
        hook.unlink()
        retry = subprocess.run(command, env=env, text=True, capture_output=True)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(self.git(checkout, 'rev-parse', 'HEAD'), committed)
        self.assertEqual(self.git(origin, 'rev-parse', 'refs/heads/main'), committed)

    def test_native_build_failure_uses_frozen_source_without_promotion(self):
        commands = self.root / 'commands'
        commands.mkdir()
        for name, body in {'id': 'echo 0', 'make': 'exit 0',
                           'poudriere': 'echo native-build-failed >&2; exit 23'}.items():
            script = commands / name
            script.write_text('#!/bin/sh\n' + body + '\n')
            script.chmod(0o755)
        env = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ['PATH'],
                   PYTHON=sys.executable, EPITHET_PACKAGING_CONFIG=str(self.root / 'absent'),
                   EPITHET_PKG_LOCKED='1', ABI='FreeBSD:15:amd64', POUDRIERE_JAIL='test',
                   POUDRIERE_PORTS='test', PORT_ORIGIN='security/epithet',
                   PORT_DIR=str(self.root / 'port'), POUDRIERE_PACKAGES=str(self.root / 'packages'),
                   POUDRIERE_PACKAGE_BRANCH='latest', DISTFILES_CACHE=str(self.root / 'distfiles'),
                   PUBLIC_ROOT=self.config['public_root'], SIGNING_KEY=str(self.root / 'unused-key'),
                   REPOSITORY_URL=self.config['repository_url'])
        result = subprocess.run(['sh', str(ROOT / 'freebsd/ops/epithet-pkg-publish'), 'publish', str(self.release)],
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIn('native-build-failed', result.stderr)
        cached = self.root / ('distfiles/epithet-1.2.3-' + 'a' * 40 + '.tar.gz')
        self.assertEqual(cached.read_bytes(), (self.release / 'source.tar.gz').read_bytes())
        self.assertIn('EPITHET_COMMIT= ' + 'a' * 40, (self.root / 'port/Makefile').read_text())
        self.assertFalse((self.root / 'public/FreeBSD:15:amd64/latest').exists())
        self.assertEqual(list((self.root / 'public/FreeBSD:15:amd64/releases').iterdir()), [])


if __name__ == '__main__':
    unittest.main()
