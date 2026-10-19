import copy
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import metadata
import publish


class DebianTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root / 'release'
        self.work = self.release / 'debian'
        self.work.mkdir(parents=True)
        self.identity = dict(tag='v1.2.3', source_commit='a' * 40,
                             source_epoch=1700000000, recipe_digest='b' * 64)
        metadata.write_json(self.release / 'release.json', self.identity)
        (self.release / 'source.tar.gz').write_bytes(b'source')
        (self.release / 'source.sha256').write_text(metadata.sha256(self.release / 'source.tar.gz'))
        self.package = 'epithet_1.2.3-1_amd64.deb'
        (self.work / self.package).write_bytes(b'package fixture')
        self.fields = dict(Package='epithet', Version='1.2.3-1', Architecture='amd64',
                           Filename='./' + self.package, Size='15',
                           SHA256=metadata.sha256(self.work / self.package),
                           Description='SSH authorization\n and host enrollment')
        self.index(self.fields)
        metadata.receipt(self.release, 'debian')
        self.manifest = metadata.verify(self.release, 'debian')
        self.config = dict(public_root=str(self.root / 'public'))

    def index(self, fields):
        (self.work / 'Packages').write_text(''.join(f'{k}: {v}\n' for k, v in fields.items()) + '\n')

    def sign(self, config, stage):
        (stage / 'InRelease').write_bytes(b'signed fixture\n' + (stage / 'Release').read_bytes())

    def test_index_binds_exact_package_identity_path_size_and_hash(self):
        publish.inspect_debian_index(self.work / 'Packages', self.manifest, self.work)
        for field, value in [('Package', 'other'), ('Version', '1.2.2-1'), ('Architecture', 'arm64'),
                             ('Filename', '../escape.deb'), ('Size', '0'), ('SHA256', 'e' * 64)]:
            self.index(dict(self.fields, **{field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                publish.inspect_debian_index(self.work / 'Packages', self.manifest, self.work)
        self.index(self.fields)
        with (self.work / 'Packages').open('a') as stream:
            stream.write('Package: other\n')
        with self.assertRaises(ValueError):
            publish.inspect_debian_index(self.work / 'Packages', self.manifest, self.work)

    def test_receipt_and_transport_require_native_test_and_exact_files(self):
        self.assertEqual(self.manifest['tests'], 'apt')
        changed = dict(self.manifest, tests='not-run')
        metadata.write_json(self.work / 'manifest.json', changed)
        with self.assertRaises(ValueError):
            metadata.verify(self.release, 'debian')
        metadata.write_json(self.work / 'manifest.json', self.manifest)
        result = self.root / 'result.tar'
        with tarfile.open(result, 'w') as tar:
            for path in self.work.iterdir():
                tar.add(path, arcname=path.name)
        shutil.rmtree(self.work)
        metadata.unpack_result(result, self.release, 'debian')
        self.assertEqual(metadata.verify(self.release, 'debian'), self.manifest)
        with self.assertRaises(ValueError):
            metadata.unpack_result(result, self.release, 'arch')
        with tarfile.open(result, 'a') as tar:
            entry = tarfile.TarInfo('../escape')
            entry.type = tarfile.SYMTYPE
            entry.linkname = '/etc/passwd'
            tar.addfile(entry)
        with self.assertRaises(ValueError):
            metadata.unpack_result(result, self.release, 'debian')

    def test_signing_failure_retry_retention_and_no_downgrade(self):
        with patch.object(publish, 'sign_debian', side_effect=RuntimeError('no key')):
            with self.assertRaises(RuntimeError):
                publish.publish_debian(self.config, self.manifest, self.work)
        self.assertIsNone(publish.current(self.config, 'debian')[0])
        with patch.object(publish, 'sign_debian', self.sign):
            publish.publish_debian(self.config, self.manifest, self.work)
        public = self.root / 'public/debian'
        self.assertEqual(publish.current(self.config, 'debian')[0], 'v1.2.3')
        self.assertIn(f'{metadata.sha256(public / "Packages")} {(public / "Packages").stat().st_size} Packages',
                      (public / 'Release').read_text())
        self.assertFalse(publish.needed(self.config, 'debian', self.identity))
        with self.assertRaises(ValueError):
            publish.needed(self.config, 'debian', dict(self.identity, source_commit='c' * 40))
        previous = (public / 'current').readlink()
        with patch.object(publish, 'sign_debian', side_effect=AssertionError('must skip')):
            publish.publish_debian(self.config, self.manifest, self.work)
            publish.publish_debian(self.config, dict(self.manifest, tag='v1.2.2'), self.work)
        self.assertEqual((public / 'current').readlink(), previous)
        self.assertEqual((public / self.package).read_bytes(), b'package fixture')

    def test_failed_promotion_can_retry_and_rejects_immutable_package_change(self):
        with patch.object(publish, 'sign_debian', self.sign), patch.object(publish, 'switch', side_effect=OSError('failed')):
            with self.assertRaises(OSError):
                publish.publish_debian(self.config, self.manifest, self.work)
        self.assertIsNone(publish.current(self.config, 'debian')[0])
        with patch.object(publish, 'sign_debian', self.sign), patch.object(publish, 'verify_debian_signature'):
            publish.publish_debian(self.config, self.manifest, self.work)
        public = self.root / 'public/debian'
        (public / 'current').unlink()
        (self.work / self.package).write_bytes(b'different bytes')
        self.index(dict(self.fields, SHA256=metadata.sha256(self.work / self.package)))
        changed = copy.deepcopy(self.manifest)
        changed['assets'][self.package] = metadata.sha256(self.work / self.package)
        with patch.object(publish, 'sign_debian', self.sign), self.assertRaisesRegex(ValueError, 'immutable file'):
            publish.publish_debian(self.config, changed, self.work)
