#!/usr/bin/env bash

set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
module_root="$(CDPATH= cd -- "${script_dir}/../.." && pwd)"
fixture_parent="${RUNNER_TEMP:-/private/tmp}"
fixture_root="${MAGEOS_FIXTURE_ROOT:-${fixture_parent}/osrw-mageos-large-catalog}"
php_binary="${MAGEOS_PHP_BINARY:-$(command -v php)}"
source_profile_path="${fixture_root}/setup/performance-toolkit/profiles/ce/small.xml"
profile_path="${fixture_root}/setup/performance-toolkit/profiles/ce/osrw-catalog-small.xml"

export MAGEOS_FIXTURE_ROOT="${fixture_root}"

"${module_root}/dev/ci/run.sh"

if [[ ! -f "${source_profile_path}" ]]; then
    echo "Mage-OS small performance profile not found: ${source_profile_path}" >&2
    exit 2
fi

"${php_binary}" "${script_dir}/prepare-large-catalog-profile.php" \
    "${source_profile_path}" \
    "${profile_path}"
"${fixture_root}/bin/magento" setup:perf:generate-fixtures "${profile_path}"
"${fixture_root}/bin/magento" indexer:reindex catalogsearch_fulltext
"${php_binary}" "${script_dir}/assert-large-catalog.php" "${fixture_root}"
