<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\RemoteResource;

use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\OwnedResourceCleanupGuard;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\OwnedResourceIdentity;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\RemoteResourceSnapshot;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class OwnedResourceCleanupGuardTest extends TestCase
{
    public function testAllowsExactOwnedResourceInDryRunWithoutDeletingAnything(): void
    {
        $ownership = $this->ownership();
        $remote = $this->remote();
        $decision = (new OwnedResourceCleanupGuard())->preview($ownership, $remote);

        self::assertTrue($decision->isEligible());
        self::assertSame([], $decision->getReasonCodes());
        self::assertSame($ownership->getRemoteId(), $decision->getRemoteId());
    }

    #[DataProvider('mismatchProvider')]
    public function testFailsClosedWhenRemoteIdentityDoesNotExactlyMatch(
        OwnedResourceIdentity $ownership,
        RemoteResourceSnapshot $remote,
        string $reasonCode
    ): void {
        $decision = (new OwnedResourceCleanupGuard())->preview($ownership, $remote);

        self::assertFalse($decision->isEligible());
        self::assertSame([$reasonCode], $decision->getReasonCodes());
    }

    /**
     * @return array<string, array{OwnedResourceIdentity, RemoteResourceSnapshot, string}>
     */
    public static function mismatchProvider(): array
    {
        $hash = str_repeat('a', 64);
        $name = 'osrw-installation-1-store-1-query-set-' . $hash;
        $ownership = new OwnedResourceIdentity(
            '7f9af483-a45a-4f1f-9d76-a7dff9715e38',
            'QUERY_SET',
            $name,
            $hash
        );

        return [
            'remote id' => [
                $ownership,
                new RemoteResourceSnapshot(
                    '55b673d1-5342-42ee-bb85-4ba8103a14d0',
                    'QUERY_SET',
                    $name,
                    $hash
                ),
                'REMOTE_ID_MISMATCH',
            ],
            'resource type' => [
                $ownership,
                new RemoteResourceSnapshot(
                    $ownership->getRemoteId(),
                    'EXPERIMENT',
                    $name,
                    $hash
                ),
                'RESOURCE_TYPE_MISMATCH',
            ],
            'remote name' => [
                $ownership,
                new RemoteResourceSnapshot(
                    $ownership->getRemoteId(),
                    'QUERY_SET',
                    'foreign-resource',
                    $hash
                ),
                'REMOTE_NAME_MISMATCH',
            ],
            'content hash' => [
                $ownership,
                new RemoteResourceSnapshot(
                    $ownership->getRemoteId(),
                    'QUERY_SET',
                    $name,
                    str_repeat('b', 64)
                ),
                'CONTENT_HASH_MISMATCH',
            ],
        ];
    }

    private function ownership(): OwnedResourceIdentity
    {
        $hash = str_repeat('a', 64);

        return new OwnedResourceIdentity(
            '7f9af483-a45a-4f1f-9d76-a7dff9715e38',
            'QUERY_SET',
            'osrw-installation-1-store-1-query-set-' . $hash,
            $hash
        );
    }

    private function remote(): RemoteResourceSnapshot
    {
        $ownership = $this->ownership();

        return new RemoteResourceSnapshot(
            $ownership->getRemoteId(),
            $ownership->getResourceType(),
            $ownership->getRemoteName(),
            $ownership->getContentHash()
        );
    }
}
