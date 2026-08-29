<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource;

use InvalidArgumentException;

class OwnedResourceIdentity
{
    private const UUID_PATTERN = '/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/iD';
    private const SHA256_PATTERN = '/\A[0-9a-f]{64}\z/D';

    public function __construct(
        private readonly string $remoteId,
        private readonly string $resourceType,
        private readonly string $remoteName,
        private readonly string $contentHash
    ) {
        if (preg_match(self::UUID_PATTERN, $remoteId) !== 1) {
            throw new InvalidArgumentException('Owned remote resource ID must be a UUID');
        }

        if ($resourceType === '' || $remoteName === '') {
            throw new InvalidArgumentException('Owned remote resource type and name must not be empty');
        }

        if (preg_match(self::SHA256_PATTERN, $contentHash) !== 1) {
            throw new InvalidArgumentException('Owned remote resource hash must be a lowercase SHA-256 value');
        }
    }

    public function getRemoteId(): string
    {
        return $this->remoteId;
    }

    public function getResourceType(): string
    {
        return $this->resourceType;
    }

    public function getRemoteName(): string
    {
        return $this->remoteName;
    }

    public function getContentHash(): string
    {
        return $this->contentHash;
    }
}
