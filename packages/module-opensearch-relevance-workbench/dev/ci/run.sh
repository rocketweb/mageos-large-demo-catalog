#!/usr/bin/env bash

set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
module_root="$(CDPATH= cd -- "${script_dir}/../.." && pwd)"
fixture_parent="${RUNNER_TEMP:-/private/tmp}"
fixture_root="${MAGEOS_FIXTURE_ROOT:-${fixture_parent}/osrw-mageos-ci}"
module_mirror="${fixture_root}/.osrw-module-source"
php_binary="${MAGEOS_PHP_BINARY:-$(command -v php)}"
php_bin_dir="$(dirname -- "${php_binary}")"
mysql_port="${OSRW_MAGEOS_MYSQL_PORT:-13308}"
opensearch_port="${OSRW_MAGEOS_OPENSEARCH_PORT:-19218}"
hyva_repository_url="${OSRW_HYVA_REPOSITORY_URL:-}"
hyva_version="${OSRW_HYVA_VERSION:-}"
expected_theme=""

if [[ -e "${fixture_root}" ]]; then
    echo "Refusing to overwrite existing fixture path: ${fixture_root}" >&2
    exit 2
fi

if [[ "$("${php_binary}" -r 'echo PHP_MAJOR_VERSION . "." . PHP_MINOR_VERSION;')" != "8.4" ]]; then
    echo "The Mage-OS qualification fixture requires PHP 8.4 exactly." >&2
    exit 2
fi

if [[ -n "${hyva_repository_url}" || -n "${hyva_version}" ]]; then
    if [[ -z "${hyva_repository_url}" || ! "${hyva_version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Hyvä qualification requires an HTTPS repository URL and an exact x.y.z version." >&2
        exit 2
    fi

    if ! "${php_binary}" -r '
        $url = $argv[1];
        $parts = parse_url($url);
        exit(
            is_array($parts)
            && ($parts["scheme"] ?? null) === "https"
            && isset($parts["host"])
            && !isset($parts["user"])
            && !isset($parts["pass"])
                ? 0
                : 1
        );
    ' "${hyva_repository_url}"; then
        echo "The Hyvä repository URL must use HTTPS and must not contain credentials." >&2
        exit 2
    fi

    expected_theme="Hyva/default"
fi

export PATH="${php_bin_dir}:${PATH}"

composer create-project \
    --no-interaction \
    --no-progress \
    --quiet \
    --repository-url=https://repo.mage-os.org/ \
    mage-os/project-community-edition \
    "${fixture_root}" \
    "3.4.0"

mkdir "${module_mirror}"
rsync -a \
    --exclude='.git/' \
    --exclude='.phpunit.cache/' \
    --exclude='vendor/' \
    --exclude='__pycache__/' \
    "${module_root}/" \
    "${module_mirror}/"

composer --working-dir="${fixture_root}" config \
    repositories.osrw \
    path \
    "${module_mirror}"
COMPOSER_MIRROR_PATH_REPOS=1 composer --working-dir="${fixture_root}" require \
    --no-interaction \
    --no-progress \
    --quiet \
    mage-os/module-opensearch-relevance-workbench:@dev

if [[ -n "${expected_theme}" ]]; then
    composer --working-dir="${fixture_root}" config \
        repositories.hyva-private \
        composer \
        "${hyva_repository_url}"
    composer --working-dir="${fixture_root}" require \
        --no-interaction \
        --no-progress \
        --quiet \
        "hyva-themes/magento2-default-theme:${hyva_version}"
fi

"${fixture_root}/bin/magento" setup:install \
    --no-interaction \
    --no-ansi \
    --quiet \
    --base-url=http://osrw-mageos.test/ \
    --db-host="127.0.0.1:${mysql_port}" \
    --db-name=osrw_ci \
    --db-user=mageos \
    --db-password=osrw_ci_only \
    --admin-firstname=Fixture \
    --admin-lastname=Operator \
    --admin-email=fixture@example.invalid \
    --admin-user=fixture \
    --admin-password='MageosCi1!' \
    --language=en_US \
    --currency=USD \
    --timezone=UTC \
    --use-rewrites=1 \
    --search-engine=opensearch \
    --opensearch-host=127.0.0.1 \
    --opensearch-port="${opensearch_port}" \
    --opensearch-enable-auth=0

"${fixture_root}/bin/magento" module:status MageOS_OpenSearchRelevanceWorkbench
"${fixture_root}/bin/magento" setup:upgrade --keep-generated --no-interaction --no-ansi --quiet

if [[ -n "${expected_theme}" ]]; then
    "${fixture_root}/bin/magento" module:status Hyva_Theme
    "${php_binary}" "${script_dir}/activate-theme.php" "${fixture_root}" "${expected_theme}"
    "${fixture_root}/bin/magento" cache:clean config layout block_html full_page
fi

"${fixture_root}/bin/magento" setup:db:status
"${fixture_root}/bin/magento" setup:di:compile
"${fixture_root}/bin/magento" indexer:reindex catalogsearch_fulltext
"${php_binary}" "${script_dir}/assert-baseline-capture.php" "${fixture_root}" "${expected_theme}"
"${php_binary}" "${script_dir}/assert-phase-one-snapshot.php" "${fixture_root}"
"${php_binary}" "${script_dir}/assert-phase-one-baseline.php" "${fixture_root}"
"${php_binary}" "${script_dir}/assert-live-activation.php" "${fixture_root}"
"${php_binary}" "${script_dir}/assert-phase-three.php" "${fixture_root}"
