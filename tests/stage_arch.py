"""Exercise the real host publisher with local CI artifacts and a throwaway key."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import publish
from metadata import sha256

artifacts, root, gnupg, fingerprint, tag = sys.argv[1:]
artifacts = Path(artifacts)
package = f"epithet-{tag[1:]}-1-x86_64.pkg.tar.zst"
manifest = {"tag": tag, "package": package,
            "assets": {name: sha256(artifacts / name) for name in
                       (package, "epithet.db.tar.gz", "epithet.files.tar.gz")}}
config = {"public_root": root, "arch_gnupg_home": gnupg, "arch_key_fingerprint": fingerprint}


publish.publish_arch(config, manifest, artifacts)
