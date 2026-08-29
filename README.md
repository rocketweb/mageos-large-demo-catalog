# Mage-OS Hyva development store

Local Mage-OS development environment with the Hyva default theme and Koti sample data.

## Installed stack

- Mage-OS 3.4
- Hyva default theme 1.5
- Tailwind CSS 4
- Koti sample data 1.0
- MySQL 8.4 and OpenSearch 3.8 through Docker
- PHP 8.4 through Magebox

## Local URLs

- Storefront: <http://mageos-latest.localhost:8080/>
- Admin: <http://mageos-latest.localhost:8080/admin>

## Restore dependencies

```sh
docker compose -f docker-compose.mageos.yaml up -d
composer install
```

Composer authentication for the Hyva private repository must be configured in the local Composer credential store. Do not commit `auth.json` or `app/etc/env.php`.
