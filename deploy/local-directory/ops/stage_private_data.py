"""仅复制已批准的两个文件，校验后交给运行用户，只用于隔离验收。"""

import hashlib
import json
import os
from pathlib import Path

SOURCE = Path("/input")
TARGET = Path("/run/bizbase-directory")
ALLOWED = ("snapshot-s01.json", "snapshot-s01.manifest.json")

payload = (SOURCE / ALLOWED[0]).read_bytes()
manifest = json.loads((SOURCE / ALLOWED[1]).read_bytes())
if manifest["snapshot_file"] != ALLOWED[0]:
    raise SystemExit("Manifest does not name the approved source snapshot")
if hashlib.sha256(payload).hexdigest() != manifest["sha256"]:
    raise SystemExit("Source snapshot digest mismatch")
if json.loads(payload)["data_as_of"] != manifest["data_as_of"]:
    raise SystemExit("Source snapshot date mismatch")
TARGET.mkdir(parents=True, exist_ok=True)
TARGET.chmod(0o700)
os.chown(TARGET, 1000, 1000)
for filename in ALLOWED:
    content = (SOURCE / filename).read_bytes()
    destination = TARGET / filename
    if destination.exists():
        if destination.read_bytes() != content:
            raise SystemExit("Refusing to replace immutable source data")
        continue
    temporary = TARGET / (filename + ".tmp")
    temporary.write_bytes(content)
    temporary.chmod(0o400)
    os.chown(temporary, 1000, 1000)
    os.replace(temporary, destination)
print("Approved private files staged; no source activation performed")
