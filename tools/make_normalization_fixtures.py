"""Create small synthetic WAV fixtures only, in a new directory; never user media."""

import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import sys
import wave


def create_fixtures(root):
    root = Path(root).expanduser().absolute()
    root.mkdir(parents=True, exist_ok=False)
    fixtures = {}
    for name, amplitude in (("quiet", 0.01), ("usable", 0.065), ("loud", 0.3), ("silent", 0)):
        samples = array("h")
        rate, seconds = 44100, 8
        for index in range(rate * seconds):
            t = index / rate
            quiet = t < 0.5 or 3 <= t < 3.5 or t >= 7.5
            samples.append(0 if quiet else round(32767 * amplitude * math.sin(2 * math.pi * 440 * t)))
        if sys.byteorder != "little":
            samples.byteswap()
        path = root / (name + ".wav")
        with path.open("xb") as stream, wave.open(stream, "wb") as output:
            output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            output.writeframes(samples.tobytes())
        fixtures[name] = {"path": str(path), "size_bytes": path.stat().st_size,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "synthetic": True, "duration_seconds": seconds, "sample_rate": rate, "channels": 1}
    return fixtures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", help="New directory; existing locations are refused")
    args = parser.parse_args()
    try:
        print(json.dumps(create_fixtures(args.output_directory), indent=2))
    except OSError:
        print("Cannot exclusively create fixture directory/files; choose a new owned directory.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
