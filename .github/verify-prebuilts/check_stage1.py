"""Checks that all stage-1 actions of a release build were remote cache hits.

Reads a decompressed compact Bazel execution log from stdin, written by a build
with --experimental_remote_require_cached, and prints a Markdown summary.

Stage-1 actions are those with outputs in a configuration in which the seed's
compiler runs. Bazel logs actions that the flag denies, so a stage-1 action
missing from the log can only be one whose inputs are produced by a denied
stage-1 action. Hence stage 1 matches the release build if no stage-1 action
was denied and the stage-1 compiler went on to compile stage 2.

The format is a stream of length-delimited ExecLogEntry messages, see
https://github.com/bazelbuild/bazel/blob/9.1.1/src/main/protobuf/spawn.proto.
"""

import collections
import re
import sys

SEED_TOOL = re.compile(r"^external/[^/]*llvm-toolchain-minimal-[^/]*/bin/")
STAGE1_TOOL = re.compile(r"/bin/toolchain/stage1_[^/]*/bin/")
CONFIG = re.compile(r"^bazel-out/([^/]+)/")

# ExecLogEntry field numbers.
ENTRY_ID = 1
ENTRY_FILE = 3
ENTRY_DIRECTORY = 4
ENTRY_UNRESOLVED_SYMLINK = 5
ENTRY_SPAWN = 7
PATH = 1
SPAWN_ARGS = 1
SPAWN_OUTPUTS = 6
SPAWN_TARGET_LABEL = 7
SPAWN_MNEMONIC = 8
SPAWN_EXIT_CODE = 9
SPAWN_STATUS = 10
SPAWN_RUNNER = 11
SPAWN_CACHE_HIT = 12
SPAWN_REMOTABLE = 13
OUTPUT_INVALID_PATH = 4
OUTPUT_ID = 5


def varint(buf, pos):
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def fields(buf):
    pos = 0
    while pos < len(buf):
        key, pos = varint(buf, pos)
        number, wire_type = key >> 3, key & 7
        if wire_type == 0:
            value, pos = varint(buf, pos)
        elif wire_type == 1:
            value, pos = buf[pos:pos + 8], pos + 8
        elif wire_type == 2:
            length, pos = varint(buf, pos)
            value, pos = buf[pos:pos + length], pos + length
        elif wire_type == 5:
            value, pos = buf[pos:pos + 4], pos + 4
        else:
            raise ValueError(f"unsupported wire type {wire_type}")
        yield number, value


def entries(stream):
    while True:
        length = shift = 0
        while True:
            b = stream.read(1)
            if not b:
                if shift:
                    raise ValueError("truncated execution log")
                return
            length |= (b[0] & 0x7F) << shift
            if not b[0] & 0x80:
                break
            shift += 7
        data = stream.read(length)
        if len(data) != length:
            raise ValueError("truncated execution log")
        yield memoryview(data)


def text(value):
    return bytes(value).decode()


def path_of(value):
    for number, v in fields(value):
        if number == PATH:
            return text(v)
    return ""


def parse_spawn(value, paths):
    spawn = {"args": [], "outputs": [], "label": "", "mnemonic": "", "exit_code": 0,
             "status": "", "runner": "", "cache_hit": False, "remotable": False}
    for number, v in fields(value):
        if number == SPAWN_ARGS:
            spawn["args"].append(text(v))
        elif number == SPAWN_OUTPUTS:
            for n, ov in fields(v):
                if n == OUTPUT_ID:
                    spawn["outputs"].append(paths.get(ov, ""))
                elif n == OUTPUT_INVALID_PATH:
                    spawn["outputs"].append(text(ov))
        elif number == SPAWN_TARGET_LABEL:
            spawn["label"] = text(v)
        elif number == SPAWN_MNEMONIC:
            spawn["mnemonic"] = text(v)
        elif number == SPAWN_EXIT_CODE:
            spawn["exit_code"] = v
        elif number == SPAWN_STATUS:
            spawn["status"] = text(v)
        elif number == SPAWN_RUNNER:
            spawn["runner"] = text(v)
        elif number == SPAWN_CACHE_HIT:
            spawn["cache_hit"] = bool(v)
        elif number == SPAWN_REMOTABLE:
            spawn["remotable"] = bool(v)
    return spawn


def configs(spawn):
    return {m.group(1) for m in map(CONFIG.match, spawn["outputs"]) if m}


def missed(spawn):
    """Whether a spawn didn't take its result from the cache even though it could have."""
    return not spawn["cache_hit"] and (spawn["remotable"] or spawn["exit_code"] != 0)


def outcome(spawn):
    if spawn["cache_hit"]:
        return "cache hit"
    if spawn["exit_code"] == 0:
        return f"executed ({spawn['runner']})"
    return "denied" if spawn["status"] == "EXECUTION_DENIED" else "failed"


def main():
    paths = {}
    spawns = []
    for entry in entries(sys.stdin.buffer):
        entry_id = 0
        for number, value in fields(entry):
            if number == ENTRY_ID:
                entry_id = value
            elif number in (ENTRY_FILE, ENTRY_DIRECTORY, ENTRY_UNRESOLVED_SYMLINK):
                paths[entry_id] = path_of(value)
            elif number == ENTRY_SPAWN:
                spawns.append(parse_spawn(value, paths))

    stage1_configs = set()
    for spawn in spawns:
        if spawn["args"] and SEED_TOOL.match(spawn["args"][0]):
            stage1_configs |= configs(spawn)
    stage1 = [s for s in spawns if configs(s) & stage1_configs]
    stage2 = [s for s in spawns if s["args"] and STAGE1_TOOL.search(s["args"][0])]

    print(f"- {len(spawns)} spawns in the execution log")
    for name, group in [("Stage 1", stage1), ("Compiled by stage 1", stage2), ("All", spawns)]:
        counts = collections.Counter(outcome(s) for s in group)
        print(f"- {name}: " + ", ".join(f"{n} {o}" for o, n in sorted(counts.items())))
    stage1_ids = {id(s) for s in stage1}
    frontier = collections.Counter(s["mnemonic"] for s in spawns if id(s) not in stage1_ids and missed(s))
    if frontier:
        print("- Missed outside stage 1: " + ", ".join(f"{n} {m}" for m, n in frontier.most_common(8)))

    stage1_missed = [s for s in stage1 if missed(s)]
    for spawn in stage1_missed[:20]:
        output = spawn["outputs"][0] if spawn["outputs"] else ""
        print(f"::error::Stage-1 action missed the cache ({outcome(spawn)}): "
              f"{spawn['mnemonic']} {spawn['label']} {output}", file=sys.stderr)
    if not stage1:
        print("- ❌ found no action run by the seed's compiler")
        sys.exit(1)
    if stage1_missed:
        print(f"- ❌ {len(stage1_missed)} stage-1 actions missed the cache")
        sys.exit(1)
    if not stage2:
        print("- ❌ the stage-1 compiler never ran, so stage 1 is incomplete")
        sys.exit(1)
    print("- ✅ every stage-1 action matched the release build")


if __name__ == "__main__":
    main()
