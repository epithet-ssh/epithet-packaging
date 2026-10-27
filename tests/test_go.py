"""Check security release boundaries and prevent automatic toolchain switching."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / 'freebsd/port/files/go.sh'


class GoToolchainTests(unittest.TestCase):
    def run_go(self, version):
        with tempfile.TemporaryDirectory() as directory:
            compiler = Path(directory) / 'go'
            compiler.write_text('''#!/bin/sh
[ "$GOTOOLCHAIN" = local ] || exit 90
if [ "$*" = 'env GOVERSION' ]; then
    printf '%s\\n' "$TEST_GO_VERSION"
else
    printf 'ran:'
    printf ' <%s>' "$@"
    exit 23
fi
''')
            compiler.chmod(0o755)
            return subprocess.run(
                ['sh', str(CHECK), str(compiler), 'build', '-ldflags', '-s -w'],
                env={**os.environ, 'GOTOOLCHAIN': 'go1.26.0+auto',
                     'TEST_GO_VERSION': version}, text=True, capture_output=True)

    def test_patched_stable_compilers_preserve_arguments_and_exit_status(self):
        for version in ('go1.26.10', 'go1.26.11', 'go1.27.3', 'go1.27.10', 'go1.28.0',
                        'go1.27.3-X:nodwarf5'):
            with self.subTest(version=version):
                result = self.run_go(version)
                self.assertEqual(result.returncode, 23, result.stderr)
                self.assertEqual(result.stdout, 'ran: <build> <-ldflags> <-s -w>')

    def test_unpatched_or_unverified_compilers_never_build(self):
        for version in ('go1.25.14', 'go1.26.0', 'go1.26.9', 'go1.27.0',
                        'go1.27.2', 'go1.27.2-X:nodwarf5', 'go1.28rc1', 'devel go1.28', '', 'go1.27.3-custom'):
            with self.subTest(version=version):
                result = self.run_go(version)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, '')
                self.assertIn('requires Go 1.26.10+', result.stderr)

    def test_compiler_failure_cannot_pass_the_check(self):
        result = subprocess.run(['sh', str(CHECK), '/usr/bin/false', 'build'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
