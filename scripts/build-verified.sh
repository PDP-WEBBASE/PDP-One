#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${SITES_ENV_READY:-}" != "1" ]]; then
  exec "${script_dir}/sites-env.sh" -- "$0" "$@"
fi

command -v timeout >/dev/null || {
  echo "build-verified.sh requires GNU timeout." >&2
  exit 69
}

diagnose_build_failure() {
  status=$?
  trap - EXIT
  if [[ "${status}" -ne 0 ]]; then
    echo "[sites] build failed; recording bounded source diagnostics" >&2
    git -C "${SITES_PROJECT_ROOT}" status --short --untracked-files=all >&2 || true
    reports_dir="${SITES_PROJECT_ROOT}/src/components/reports"
    if [[ -d "${reports_dir}" ]]; then
      echo "[sites] unexpected reports source tree exists:" >&2
      find "${reports_dir}" -maxdepth 2 -type f -print | sort >&2 || true
      for diagnostic_file in \
        "${reports_dir}/sessionComparisonRows.ts" \
        "${reports_dir}/V13CompatWorkspace.ts" \
        "${reports_dir}/V13CompatWorkspace.tsx"; do
        if [[ -f "${diagnostic_file}" ]]; then
          echo "[sites] diagnostic file: ${diagnostic_file#${SITES_PROJECT_ROOT}/}" >&2
          sed -n '1,180p' "${diagnostic_file}" >&2 || true
        fi
      done
    else
      echo "[sites] src/components/reports does not exist at failure time" >&2
    fi
  fi
  exit "${status}"
}
trap diagnose_build_failure EXIT

vinext="${SITES_PROJECT_ROOT}/node_modules/.bin/vinext"
if [[ ! -x "${vinext}" ]]; then
  echo "vinext is unavailable. Run npm run install:ci and wait for it to finish before building." >&2
  exit 69
fi

echo "Running bounded vinext build..."
timeout \
  --signal=TERM \
  --kill-after="${SITES_BUILD_KILL_AFTER:-10s}" \
  "${SITES_BUILD_TIMEOUT:-3m}" \
  "${vinext}" build

"${script_dir}/validate-artifact.sh"
