<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource;

use InvalidArgumentException;

class OwnedResourceNameFactory
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z/iD';

    public function create(string $kind, string $localUuid): string
    {
        if ($kind === '' || preg_match(self::UUID_PATTERN, $localUuid) !== 1) {
            throw new InvalidArgumentException('Owned resource names require a kind and local UUID');
        }

        $name = 'osrw-' . strtolower($kind) . '-' . substr(strtolower($localUuid), 0, 24);

        if (strlen($name) > 50) {
            $name = 'osrw-' . substr(hash('sha256', strtolower($kind)), 0, 8)
                . '-' . substr(strtolower($localUuid), 0, 24);
        }

        return $name;
    }
}
