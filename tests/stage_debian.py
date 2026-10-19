"""Exercise the production apt publisher with native packages and a test key."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import publish
from metadata import asset_names, sha256

artifacts, root, gnupg, fingerprint, tag = sys.argv[1:]
artifacts = Path(artifacts)
manifest = {'tag': tag, 'source_epoch': int(os.environ['SOURCE_DATE_EPOCH']),
            'assets': {name: sha256(artifacts / name) for name in asset_names('debian', tag)}}
config = {'public_root': root, 'debian_gnupg_home': gnupg, 'debian_key_fingerprint': fingerprint}
publish.publish_debian(config, manifest, artifacts)
