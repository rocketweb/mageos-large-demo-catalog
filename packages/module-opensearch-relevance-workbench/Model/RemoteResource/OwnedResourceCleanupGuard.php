<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource;

class OwnedResourceCleanupGuard
{
    public function preview(
        OwnedResourceIdentity $ownership,
        RemoteResourceSnapshot $remote
    ): OwnedResourceCleanupDecision {
        $reasonCodes = [];

        if ($ownership->getRemoteId() !== $remote->getRemoteId()) {
            $reasonCodes[] = 'REMOTE_ID_MISMATCH';
        }

        if ($ownership->getResourceType() !== $remote->getResourceType()) {
            $reasonCodes[] = 'RESOURCE_TYPE_MISMATCH';
        }

        if ($ownership->getRemoteName() !== $remote->getRemoteName()) {
            $reasonCodes[] = 'REMOTE_NAME_MISMATCH';
        }

        if ($ownership->getContentHash() !== $remote->getContentHash()) {
            $reasonCodes[] = 'CONTENT_HASH_MISMATCH';
        }

        return new OwnedResourceCleanupDecision(
            $ownership->getRemoteId(),
            $reasonCodes === [],
            $reasonCodes
        );
    }
}
