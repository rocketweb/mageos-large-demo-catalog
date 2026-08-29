<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Proposal;

class ProposalExport
{
    public function __construct(
        private readonly string $canonicalJson,
        private readonly string $artifactHash,
        private readonly string $filename
    ) {
    }

    public function getCanonicalJson(): string
    {
        return $this->canonicalJson;
    }

    public function getArtifactHash(): string
    {
        return $this->artifactHash;
    }

    public function getFilename(): string
    {
        return $this->filename;
    }
}
