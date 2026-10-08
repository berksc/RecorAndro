"""Step 1.1 synthetic-fixture qualification only; no user media or engine API.

Run from repository root. JSON evidence goes to stdout; temporary fixtures are removed.
This script never grants Android-capability-validated status automatically.
"""

import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recorandro.config import ConfigError, load_config
from recorandro.diagnostics import doctor, run_tool

RATES = (7350, 8000, 11025, 12000, 16000, 22050, 24000,
         32000, 44100, 48000, 64000, 88200, 96000)
ENTRIES = ("format=format_name,duration,size,bit_rate,start_time:format_tags=creation_time:"
           "stream=index,codec_type,codec_name,sample_rate,channels,channel_layout,bit_rate,"
           "duration,duration_ts,time_base,start_time:stream_tags=creation_time")
LOUDNESS = "loudnorm=I=-26:TP=-3:LRA=50:print_format=json"
QUIET = "asetpts=PTS-STARTPTS,silencedetect=noise=-40dB:duration=1:mono=0"


def make_wav(path, rate=48000, channels=1, seconds=6, active_right=False):
    samples = array("h")
    for i in range(rate * seconds):
        t = i / rate
        quiet = t < 1.25 or 2 <= t < 3.5 or t >= 4.5
        tone = round(1800 * math.sin(2 * math.pi * 440 * t))
        for ch in range(channels):
            samples.append(tone if (not quiet or (active_right and ch == 1)) else 0)
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes(samples.tobytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def faststart(path):
    data = path.read_bytes()
    atoms = []
    offset = 0
    while offset + 8 <= len(data):
        size, name = struct.unpack_from(">I4s", data, offset)
        if size < 8:
            raise AssertionError("Unexpected MP4 atom size")
        atoms.append(name)
        offset += size
    assert b"moov" in atoms and b"mdat" in atoms and atoms.index(b"moov") < atoms.index(b"mdat")


def external_reference(source, target):
    """Build an owned QuickTime alias fixture pointing only to our synthetic M4A.

    Alias layout follows FFmpeg libavformat/mov.c mov_read_dref. This is fixture
    construction, not a general media parser. The source is never modified.
    """
    def atom(name, body):
        return struct.pack(">I4s", len(body) + 8, name) + body
    path = source.resolve().as_posix().encode("utf-8")
    alias = (bytes(10) + bytes(28) + bytes(12) + bytes(64) + bytes(16) +
             bytes(4) + bytes(16) + struct.pack(">HH", 2, len(path)) + path +
             (b"\x00" if len(path) % 2 else b"") + b"\xff\xff\x00\x00")
    reference = atom(b"dref", bytes(4) + struct.pack(">I", 1) + atom(b"alis", bytes(4) + alias))

    def rewrite(data):
        result = bytearray()
        offset = 0
        while offset < len(data):
            size, name = struct.unpack_from(">I4s", data, offset)
            assert 8 <= size <= len(data) - offset
            body = data[offset + 8:offset + size]
            if name == b"dref":
                result.extend(reference)
            elif name in (b"moov", b"trak", b"mdia", b"minf", b"dinf"):
                result.extend(atom(name, rewrite(body)))
            else:
                result.extend(data[offset:offset + size])
            offset += size
        return bytes(result)
    target.write_bytes(rewrite(source.read_bytes()))


class Checks:
    def __init__(self, config):
        self.config = config
        self.commands = []
        self.results = []

    def run(self, args, *, failure=False, timeout=120):
        result = run_tool([str(x) for x in args], timeout)
        self.commands.append(result)
        rc = result["returncode"]
        assert rc is not None, result["output"][-4096:]
        assert (rc != 0 if failure else rc == 0), result["output"][-4096:]
        assert not result["truncated"], "Output exceeded 64 KiB; cannot verify complete evidence"
        return result["output"]

    def case(self, name, action):
        start = len(self.commands)
        try:
            action()
            self.results.append({"name": name, "status": "PASS", "commands": [start, len(self.commands)]})
        except (AssertionError, OSError, ValueError, KeyError, IndexError) as exc:
            self.results.append({"name": name, "status": "FAIL", "error": str(exc),
                                 "commands": [start, len(self.commands)]})

    def input(self, source):
        # MOV-private options apply to MOV fixtures; some builds reject them for WAV/MP3.
        mov_options = ["-enable_drefs", "0", "-use_absolute_path", "0"] if str(source).endswith(".m4a") else []
        return ["-protocol_whitelist", "file", "-format_whitelist", "mov,mp3,wav,aac",
                *mov_options, "-err_detect", "explode",
                "-i", source, "-map", "0:0", "-vn", "-sn", "-dn"]

    def ffmpeg(self, source, output_args, *, failure=False):
        return self.run([self.config.ffmpeg, "-hide_banner", "-nostdin", "-n", "-xerror",
                         *self.input(source), *output_args], failure=failure)

    def probe(self, source):
        mov_options = ["-enable_drefs", "0", "-use_absolute_path", "0"] if str(source).endswith(".m4a") else []
        text = self.run([self.config.ffprobe, "-v", "error", "-protocol_whitelist", "file",
                         "-format_whitelist", "mov,mp3,wav,aac", *mov_options,
                         "-show_entries", ENTRIES, "-of", "json",
                         "-i", source], timeout=30)
        result = json.loads(text)
        assert len(result["streams"]) == 1
        stream = result["streams"][0]
        assert stream["index"] == 0 and stream["codec_type"] == "audio"
        assert int(stream["sample_rate"]) > 0 and int(stream["channels"]) in (1, 2)
        assert float(stream.get("duration", result["format"]["duration"])) > 0
        return result

    def encode(self, source, target, rate, channels, filters=None):
        args = ["-map_metadata", "-1", "-map_chapters", "-1"]
        if filters:
            args += ["-af", filters]
        args += ["-c:a", "aac", "-profile:a", "aac_low", "-b:a",
                 "128000" if channels == 1 else "192000", "-ar", str(rate),
                 "-movflags", "+faststart", "-f", "ipod", target]
        self.ffmpeg(source, args)
        metadata = self.probe(target)
        stream = metadata["streams"][0]
        assert stream["codec_name"] == "aac"
        profile = json.loads(self.run([self.config.ffprobe, "-v", "error", "-protocol_whitelist", "file",
                                      "-show_entries", "stream=profile", "-of", "json", target], timeout=30))
        assert profile["streams"][0]["profile"] == "LC"
        assert int(stream["sample_rate"]) == rate and stream["channels"] == channels
        assert target.stat().st_size > 0
        faststart(target)
        self.ffmpeg(target, ["-f", "null", "-"])
        return stream

    def measure(self, source):
        output = self.ffmpeg(source, ["-af", LOUDNESS, "-f", "null", "-"])
        matches = re.findall(r'\{\s*"input_i".*?\}', output, re.S)
        assert matches, "Missing loudnorm input JSON"
        levels = json.loads(matches[-1])
        for key in ("input_i", "input_tp", "input_lra", "input_thresh"):
            assert math.isfinite(float(levels[key])), levels
        return levels

    def timing(self, stream, seconds, source_rate, output_rate):
        tolerance = max(0.05, 2048 / min(source_rate, output_rate))
        assert abs(float(stream["duration"]) - seconds) <= tolerance, stream
        assert abs(float(stream["start_time"])) <= tolerance, stream


def check_suite(checks, work):
    mono = work / "mono.wav"
    stereo = work / "stereo.wav"
    active = work / "active-right.wav"
    for path, channels, active_right in ((mono, 1, False), (stereo, 2, False), (active, 2, True)):
        make_wav(path, channels=channels, active_right=active_right)
    originals = {path: digest(path) for path in (mono, stereo, active)}
    m4a = work / "aac.m4a"

    def baseline():
        assert checks.probe(mono)["streams"][0]["codec_name"] == "pcm_s16le"
        checks.ffmpeg(mono, ["-f", "null", "-"])
        stream = checks.encode(mono, m4a, 48000, 1)
        checks.timing(stream, 6, 48000, 48000)
        raw = work / "raw.aac"
        checks.ffmpeg(m4a, ["-c:a", "copy", "-f", "adts", raw])
        assert checks.probe(raw)["streams"][0]["codec_name"] == "aac"
        checks.ffmpeg(raw, ["-f", "null", "-"])
    checks.case("PCM WAV, AAC M4A, raw AAC, native AAC-LC, ipod, faststart, probe/decode", baseline)

    def mp3():
        target = work / "input.mp3"
        checks.ffmpeg(mono, ["-c:a", "libmp3lame", "-b:a", "128000", target])
        assert checks.probe(target)["streams"][0]["codec_name"] in ("mp3", "mp3float")
        checks.ffmpeg(target, ["-f", "null", "-"])
    checks.case("MP3 decode (libmp3lame used only to generate synthetic fixture)", mp3)

    def gain():
        checks.measure(mono)
        target = work / "gain-fixture.m4a"
        stream = checks.encode(mono, target, 48000, 1, "volume=1.000dB:precision=double")
        checks.timing(stream, 6, 48000, 48000)
        assert float(checks.measure(target)["input_tp"]) <= -1
    checks.case("Frozen loudnorm input JSON, constant double volume and encoded measurement", gain)

    def silence():
        output = checks.ffmpeg(stereo, ["-af", QUIET, "-f", "null", "-"])
        starts = [float(x) for x in re.findall(r"silence_start: ([0-9.eE+-]+)", output)]
        ends = [float(x) for x in re.findall(r"silence_end: ([0-9.eE+-]+)", output)]
        assert len(starts) == len(ends) == 3, output
        for actual, expected in zip(starts + ends, [0, 2, 4.5, 1.25, 3.5, 6]):
            assert abs(actual - expected) <= max(0.05, 2048 / 48000)
        output = checks.ffmpeg(active, ["-af", QUIET, "-f", "null", "-"])
        assert "silence_start:" not in output, "Active stereo channel must prevent combined silence"
    checks.case("Combined-channel silencedetect, leading/middle/trailing pause positions", silence)

    def trim():
        target = work / "trim.wav"
        filters = "atrim=start_sample=72000:end_sample=168000,asetpts=PTS-STARTPTS"
        checks.ffmpeg(stereo, ["-af", filters, "-c:a", "pcm_s16le", target])
        with wave.open(str(stereo), "rb") as source, wave.open(str(target), "rb") as result:
            source.setpos(72000)
            assert result.getnframes() == 96000
            assert result.readframes(96000) == source.readframes(96000)
        encoded = work / "trim.m4a"
        stream = checks.encode(stereo, encoded, 48000, 2, filters)
        checks.timing(stream, 2, 48000, 48000)
    checks.case("Sample-index atrim, exact PCM span with retained silence, asetpts, encoded timing", trim)

    for rate in RATES + (12345, 192000):
        for channels in (1, 2):
            def rate_case(rate=rate, channels=channels):
                source = work / f"rate-{rate}-{channels}.wav"
                target = work / f"rate-{rate}-{channels}.m4a"
                make_wav(source, rate, channels)
                output_rate = rate if rate in RATES else 48000
                stream = checks.encode(source, target, output_rate, channels)
                checks.timing(stream, 6, rate, output_rate)
            checks.case(f"Rate {rate}, channels {channels}: preserve or convert to 48000", rate_case)

    def copy():
        target = work / "independent.m4a"
        with m4a.open("rb") as source, target.open("xb") as output:
            shutil.copyfileobj(source, output)
        assert digest(m4a) == digest(target) and m4a.stat().st_size == target.stat().st_size
        assert checks.probe(m4a) == checks.probe(target)
        checks.ffmpeg(target, ["-f", "null", "-"])
    checks.case("Independent full-length copy: exact hash, size, duration and decode", copy)

    def overwrite():
        before = digest(m4a)
        # Some versions return zero for -n refusal. Confirm refusal and bytes,
        # independently of exit status; decode-error cases still require nonzero.
        args = [checks.config.ffmpeg, "-hide_banner", "-nostdin", "-n", "-xerror",
                *checks.input(mono), "-c:a", "aac", "-f", "ipod", str(m4a)]
        result = run_tool([str(x) for x in args], 120)
        checks.commands.append(result)
        assert result["returncode"] is not None
        assert "already exists" in result["output"] and "Exiting" in result["output"]
        assert digest(m4a) == before
    checks.case("-n refuses existing output without changing it", overwrite)

    def malformed():
        invalid = work / "invalid.wav"
        invalid.write_bytes(b"not valid media")
        checks.ffmpeg(invalid, ["-f", "null", "-"], failure=True)
        checks.run([checks.config.ffprobe, "-v", "error", "-protocol_whitelist", "file",
                    "-format_whitelist", "mov,mp3,wav,aac", "-of", "json", invalid], failure=True, timeout=30)
        damaged = work / "truncated.wav"
        damaged.write_bytes(mono.read_bytes()[:-101])
        checks.ffmpeg(damaged, ["-f", "null", "-"], failure=True)
    checks.case("Malformed probe and corrupt decode fail under explode/xerror", malformed)

    def restrictions():
        # Both tools must reject a non-file protocol before opening a connection.
        checks.ffmpeg("http://127.0.0.1:9/fixture.wav", ["-f", "null", "-"], failure=True)
        assert "whitelist" in checks.commands[-1]["output"].lower()
        checks.run([checks.config.ffprobe, "-v", "error", "-protocol_whitelist", "file",
                    "-i", "http://127.0.0.1:9/fixture.wav"], failure=True, timeout=30)
        assert "whitelist" in checks.commands[-1]["output"].lower()
        checks.run([checks.config.ffprobe, "-v", "error", "-protocol_whitelist", "file",
                    "-format_whitelist", "mp3", "-i", mono], failure=True, timeout=30)
        assert "whitelist" in checks.commands[-1]["output"].lower()
        checks.run([checks.config.ffmpeg, "-hide_banner", "-nostdin", "-xerror",
                    "-protocol_whitelist", "file", "-format_whitelist", "mp3", "-i", mono,
                    "-f", "null", "-"], failure=True)
        assert "whitelist" in checks.commands[-1]["output"].lower()
    checks.case("File protocol and demuxer allowlists reject prohibited inputs", restrictions)

    def references():
        target = work / "external-reference.m4a"
        external_reference(m4a, target)
        for tool in (checks.config.ffprobe, checks.config.ffmpeg):
            for enabled, message in (("0", "Skipped opening external track"),
                                     ("1", "not tried for security reasons")):
                # enable_drefs=1 is a negative fixture control ONLY, to isolate
                # use_absolute_path=0. It still blocks the owned absolute alias.
                args = [tool, "-v", "warning", "-protocol_whitelist", "file",
                        "-format_whitelist", "mov,mp3,wav,aac", "-enable_drefs", enabled,
                        "-use_absolute_path", "0"]
                if tool == checks.config.ffmpeg:
                    args += ["-nostdin", "-n", "-xerror", "-err_detect", "explode"]
                args += ["-i", str(target)]
                args += (["-show_packets", "-show_entries", "packet=size", "-of", "json"]
                         if tool == checks.config.ffprobe else ["-map", "0:0", "-f", "null", "-"])
                result = run_tool(args, 30 if tool == checks.config.ffprobe else 120)
                checks.commands.append(result)
                assert result["returncode"] is not None and not result["truncated"]
                assert message in result["output"], result["output"]
                if tool == checks.config.ffprobe:
                    match = re.search(r'\{\s*"packets".*', result["output"], re.S)
                    assert match and json.loads(match.group())["packets"] == []
    checks.case("MOV external tracks and absolute external paths blocked by both tools", references)

    def integrity():
        assert all(digest(path) == before for path, before in originals.items())
    checks.case("Synthetic source bytes unchanged", integrity)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    baseline = doctor(config)
    checks = Checks(config)
    if baseline["ok"]:
        with tempfile.TemporaryDirectory(prefix="capability-", dir=config.data_root) as directory:
            check_suite(checks, Path(directory))
    passed = baseline["ok"] and bool(checks.results) and all(x["status"] == "PASS" for x in checks.results)
    print(json.dumps({"environment": baseline, "fixture_checks": "PASS" if passed else "FAIL",
                      "android_validation": "PENDING: actual Redmi/Termux evidence and review required",
                      "manual_checks_required": [
                          "Termux source/version and actual Redmi identity",
                          "User review of complete real-device results"],
                      "checks": checks.results, "commands": checks.commands}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
