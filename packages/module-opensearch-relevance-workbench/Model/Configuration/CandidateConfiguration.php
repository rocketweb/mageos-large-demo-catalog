<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Configuration;

class CandidateConfiguration
{
    /**
     * @param array<array-key, mixed> $template
     * @param array{type: string, boosts: array<string, float>} $transformation
     */
    public function __construct(
        private readonly array $template,
        private readonly array $transformation,
        private readonly string $configurationHash
    ) {
    }

    /**
     * @return array<array-key, mixed>
     */
    public function getTemplate(): array
    {
        return $this->template;
    }

    /**
     * @return array{type: string, boosts: array<string, float>}
     */
    public function getTransformation(): array
    {
        return $this->transformation;
    }

    public function getConfigurationHash(): string
    {
        return $this->configurationHash;
    }
}
