#!/usr/bin/env bash
# Checks that the stage-1 toolchain of an LLVM prebuilt release, which the
# release's seed compiles from the release's sources, matches the one the
# release build produced.
#
# Usage: check_stage1.sh <release tag>
#
# Reruns the release build at its commit (the current directory) with its
# original seed and --experimental_remote_require_cached, so no action is
# executed: each one either takes the result the release build stored in the
# remote cache or fails. A cache hit means that the action has the same digest,
# i.e. the same command and inputs, as in the release build. The build keeps
# going after misses, so the execution log lists every action whose inputs were
# available, and check_stage1.py fails unless all stage-1 actions were cache
# hits. A miss doesn't tell a stage-1 action that differs from the release build
# apart from one whose cache entry has been evicted.

set -euo pipefail

tag="$1"

cat >> "${HOME}/.bazelrc" <<EOF
common --remote_header=x-buildbuddy-api-key=4jtaxdhxtyu4ylxdEwI7
common --bes_header=x-buildbuddy-api-key=4jtaxdhxtyu4ylxdEwI7
common --remote_accept_cached
common --noremote_upload_local_results
common --experimental_remote_require_cached
common --keep_going
common --execution_log_compact_file=${RUNNER_TEMP}/exec_log.zst
EOF

# Every cache miss fails the build, so its result says nothing on its own.
build_log="${RUNNER_TEMP}/build.log"
GITHUB_REF_NAME="${tag}" bash .github/workflows/llvm-prebuilt.sh > "${build_log}" 2>&1 || true
sed 's/\x1b\[[0-9;]*m//g' "${build_log}" | grep -E 'INFO: [0-9]+ processes: |Build (did NOT )?complete' || true

summary="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
echo "## ${tag} ($(git rev-parse --short HEAD))" >> "${summary}"
zstd -dc "${RUNNER_TEMP}/exec_log.zst" | python3 "${VERIFY_DIR}/.github/verify-prebuilts/check_stage1.py" | tee -a "${summary}"
