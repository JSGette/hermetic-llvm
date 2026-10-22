GLIBC_VERSIONS = [
    "2.17",
    "2.23",
    "2.28",
    "2.29",
    "2.30",
    "2.31",
    "2.32",
    "2.33",
    "2.34",
    "2.35",
    "2.36",
    "2.37",
    "2.38",
    "2.39",
    "2.40",
    "2.41",
    "2.42",
    "2.43",
    "2.44",
]

# glibc versions older than 2.28 are only provided for these targets.
LEGACY_GLIBC_TARGETS = {
    "gnu.2.17": [("linux", "x86_64")],
    "gnu.2.23": [("linux", "aarch64")],
}

def libc_supports_target(libc, target_os, target_cpu):
    targets = LEGACY_GLIBC_TARGETS.get(libc)
    return targets == None or (target_os, target_cpu) in targets

GLIBCS = ["gnu.{}".format(glibc) for glibc in GLIBC_VERSIONS]

LIBCS = ["musl"] + GLIBCS

DEFAULT_LIBC = "gnu.2.28"

# compile-rt from LLVM requires kernel headers >= 5.10 for RISC-V.
# Keep RISC-V on a libc whose default linux UAPI headers satisfy that.
DEFAULT_LIBCS = {
    ("linux", "riscv64"): "gnu.2.33",
}

def default_libc(target_os, target_cpu):
    return DEFAULT_LIBCS.get((target_os, target_cpu), DEFAULT_LIBC)
