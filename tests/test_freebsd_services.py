"""Exercise rc.d startup preparation without FreeBSD, root, or a running daemon."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("server", "ca", "control", "directory", "inventory")


class FreeBSDStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "var/db/epithet"
        self.log = self.root / "install.jsonl"
        # Simulate install's file effects and record ownership requests. Real
        # account ownership and rc.subr integration still require FreeBSD.
        installer = self.root / "install.py"
        installer.write_text('''import json, os, pathlib, shutil, sys
args = sys.argv[1:]
with open(os.environ["INSTALL_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if os.environ.get("FAIL_STATE") and any("/var/db/epithet" in a for a in args):
    sys.exit(1)
mode = int(args[args.index("-m") + 1], 8)
paths = args[args.index("-g") + 2:]
if "-d" in args:
    for value in paths:
        path = pathlib.Path(value)
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
else:
    shutil.copyfile(*paths)
    pathlib.Path(paths[-1]).chmod(mode)
''')
        self.shim = self.root / "rc.subr"
        self.shim.write_text('''load_rc_config() { :; }
checkyesno() { eval "test \\"\\${$1:-NO}\\" = YES"; }
run_rc_command() { "$start_precmd"; }
install() { ''' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(installer)) + ' "$@"; }\n')

    def prepare(self, service, **environment):
        script = (ROOT / f"freebsd/port/files/epithet_{service}.in").read_text()
        script = script.replace("/var/", str(self.root) + "/var/")
        script = script.replace(". /etc/rc.subr", ". " + shlex.quote(str(self.shim)))
        return subprocess.run(["sh", "-c", script], text=True, capture_output=True,
                              env={**os.environ, "INSTALL_LOG": str(self.log), **environment})

    def test_fresh_state_and_existing_data(self):
        for service, directories in (("server", ("directory", "inventory")),
                                     ("directory", ("directory",)),
                                     ("inventory", ("inventory",))):
            with self.subTest(service=service):
                result = self.prepare(service)
                self.assertEqual(result.returncode, 0, result.stderr)
                for name in directories:
                    self.assertEqual((self.state / name).stat().st_mode & 0o777, 0o700)
                self.assertEqual({p.name for p in self.state.iterdir()}, set(directories))
                shutil.rmtree(self.state)
        result = self.prepare("server")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.state.chmod(0o751)
        fixtures = {self.state / "domain": b"host enrollment",
                    self.state / "directory/directory.db": b"directory data",
                    self.state / "inventory/record": b"inventory data"}
        for path, value in fixtures.items():
            path.write_bytes(value)
        before = {path: path.stat() for path in fixtures}
        self.log.write_text("")
        for service in ("server", "directory", "inventory"):
            result = self.prepare(service)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o751)
        for path, value in fixtures.items():
            self.assertEqual(path.read_bytes(), value)
            for field in ("st_mode", "st_uid", "st_gid", "st_mtime_ns"):
                self.assertEqual(getattr(path.stat(), field), getattr(before[path], field))
        for line in self.log.read_text().splitlines():
            self.assertNotIn(str(self.state), json.loads(line))

    def test_conflicting_services_stop_before_preparation(self):
        for standalone in SERVICES[1:]:
            for service, enabled in (("server", standalone), (standalone, "server")):
                with self.subTest(service=service, enabled=enabled):
                    result = self.prepare(service, **{f"epithet_{enabled}_enable": "YES"})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("cannot run", result.stderr)
                    self.assertFalse(self.log.exists())

    def test_state_preparation_failure_stops_startup(self):
        for service in ("server", "directory", "inventory"):
            with self.subTest(service=service):
                self.assertNotEqual(self.prepare(service, FAIL_STATE="1").returncode, 0)
                self.assertFalse((self.root / "var/log/epithet").exists())


if __name__ == "__main__":
    unittest.main()
