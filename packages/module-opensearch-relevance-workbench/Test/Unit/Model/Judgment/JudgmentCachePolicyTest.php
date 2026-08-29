<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Judgment;

use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\JudgmentCacheIdentityFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\JudgmentCachePolicy;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class JudgmentCachePolicyTest extends TestCase
{
    private JudgmentCacheIdentityFactory $identityFactory;
    private JudgmentCachePolicy $policy;

    protected function setUp(): void
    {
        $canonicalJson = new CanonicalJson();
        $this->identityFactory = new JudgmentCacheIdentityFactory($canonicalJson);
        $this->policy = new JudgmentCachePolicy();
    }

    public function testRequiresOverwriteWithoutAnAcceptedPriorRun(): void
    {
        $decision = $this->policy->decide($this->createIdentity(), null);

        self::assertTrue($decision->shouldOverwriteCache());
        self::assertSame(['NO_ACCEPTED_PRIOR_RUN'], $decision->getReasonCodes());
    }

    public function testAllowsReuseOnlyForAnIdenticalAcceptedIdentity(): void
    {
        $current = $this->createIdentity();
        $previous = $this->createIdentity();
        $decision = $this->policy->decide($current, $previous);

        self::assertFalse($decision->shouldOverwriteCache());
        self::assertSame([], $decision->getReasonCodes());
        self::assertSame($current->getIdentityHash(), $previous->getIdentityHash());
    }

    /**
     * @param array<string, mixed> $change
     */
    #[DataProvider('changedIdentityProvider')]
    public function testRequiresOverwriteWhenAnyProtectedIdentityChanges(
        array $change,
        string $reasonCode
    ): void {
        $previous = $this->createIdentity();
        $current = $this->createIdentity($change);
        $decision = $this->policy->decide($current, $previous);

        self::assertTrue($decision->shouldOverwriteCache());
        self::assertSame([$reasonCode], $decision->getReasonCodes());
        self::assertNotSame($current->getIdentityHash(), $previous->getIdentityHash());
    }

    /**
     * @return array<string, array{array<string, mixed>, string}>
     */
    public static function changedIdentityProvider(): array
    {
        return [
            'model' => [['modelId' => 'model-b'], 'MODEL_CHANGED'],
            'prompt' => [['prompt' => 'Rate exact product usefulness'], 'PROMPT_CHANGED'],
            'rating type' => [['ratingType' => 'RELEVANT'], 'RATING_TYPE_CHANGED'],
            'context fields' => [[
                'contextFields' => ['title', 'sku', 'description'],
            ], 'CONTEXT_FIELDS_CHANGED'],
            'context values' => [[
                'contextValues' => [['id' => 'sku-1', 'title' => 'Changed title', 'sku' => 'SKU-1']],
            ], 'CONTEXT_VALUES_CHANGED'],
            'query snapshot' => [[
                'querySnapshotHash' => str_repeat('1', 64),
            ], 'QUERY_SNAPSHOT_CHANGED'],
            'configuration' => [[
                'searchConfigurationHash' => str_repeat('2', 64),
            ], 'SEARCH_CONFIGURATION_CHANGED'],
            'index evidence' => [[
                'indexEvidenceHash' => str_repeat('3', 64),
            ], 'INDEX_EVIDENCE_CHANGED'],
        ];
    }

    public function testContextValueOrderDoesNotChangeIdentity(): void
    {
        $previous = $this->createIdentity([
            'contextValues' => [
                ['id' => 'sku-1', 'title' => 'Winter boots', 'sku' => 'SKU-1'],
                ['id' => 'sku-2', 'title' => 'Hiking boots', 'sku' => 'SKU-2'],
            ],
        ]);
        $current = $this->createIdentity([
            'contextValues' => [
                ['sku' => 'SKU-1', 'title' => 'Winter boots', 'id' => 'sku-1'],
                ['title' => 'Hiking boots', 'id' => 'sku-2', 'sku' => 'SKU-2'],
            ],
        ]);

        self::assertSame($previous->getContextValuesHash(), $current->getContextValuesHash());
        self::assertFalse($this->policy->decide($current, $previous)->shouldOverwriteCache());
    }

    /**
     * @param array<string, mixed> $change
     */
    private function createIdentity(array $change = []): \MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\JudgmentCacheIdentity
    {
        $values = array_replace([
            'modelId' => 'model-a',
            'prompt' => 'Rate product usefulness',
            'ratingType' => 'SCORE0_1',
            'contextFields' => ['title', 'sku'],
            'contextValues' => [['id' => 'sku-1', 'title' => 'Winter boots', 'sku' => 'SKU-1']],
            'querySnapshotHash' => str_repeat('a', 64),
            'searchConfigurationHash' => str_repeat('b', 64),
            'indexEvidenceHash' => str_repeat('c', 64),
        ], $change);

        return $this->identityFactory->create(
            $values['modelId'],
            $values['prompt'],
            $values['ratingType'],
            $values['contextFields'],
            $values['contextValues'],
            $values['querySnapshotHash'],
            $values['searchConfigurationHash'],
            $values['indexEvidenceHash']
        );
    }
}
