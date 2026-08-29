<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Activation;

use Magento\Store\Model\StoreManagerInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\LiveActivationRepository;
use UnexpectedValueException;

class LiveQueryApplier
{
    /** @var array<int, LiveActivation|null> */
    private array $currentByStore = [];

    public function __construct(
        private readonly LiveActivationRepository $activationRepository,
        private readonly StoreManagerInterface $storeManager
    ) {
    }

    /**
     * @param array<array-key, mixed> $mappedQuery
     * @return array<array-key, mixed>
     */
    public function apply(array $mappedQuery): array
    {
        $storeId = (int)$this->storeManager->getStore()->getId();

        if (!array_key_exists($storeId, $this->currentByStore)) {
            $this->currentByStore[$storeId] = $this->activationRepository->getCurrent($storeId);
        }

        $activation = $this->currentByStore[$storeId];

        if ($activation === null) {
            return $mappedQuery;
        }

        $transformation = $activation->getTransformation();
        $type = $transformation['type'];

        if ($type === 'STOCK') {
            return $mappedQuery;
        }

        $boosts = $transformation['boosts'] ?? null;

        if ($type !== 'FIELD_BOOST' || !is_array($boosts) || $boosts === []) {
            throw new UnexpectedValueException('Active search transformation is not supported');
        }

        return $this->transform($mappedQuery, $boosts);
    }

    /**
     * @param array<array-key, mixed> $value
     * @param array<string, float> $boosts
     * @return array<array-key, mixed>
     */
    private function transform(array $value, array $boosts): array
    {
        $transformed = [];

        foreach ($value as $key => $item) {
            if ($key === 'fields' && is_array($item) && array_is_list($item)) {
                $transformed[$key] = $this->transformFieldList($item, $boosts);
                continue;
            }

            if (
                is_string($key)
                && in_array($key, ['match', 'match_phrase', 'match_phrase_prefix'], true)
                && is_array($item)
                && !array_is_list($item)
            ) {
                $transformed[$key] = $this->transformMatchFields($item, $boosts);
                continue;
            }

            $transformed[$key] = is_array($item) ? $this->transform($item, $boosts) : $item;
        }

        return $transformed;
    }

    /**
     * @param array<string, mixed> $fields
     * @param array<string, float> $boosts
     * @return array<string, mixed>
     */
    private function transformMatchFields(array $fields, array $boosts): array
    {
        foreach ($fields as $field => $parameters) {
            if (!isset($boosts[$field])) {
                continue;
            }

            if (is_array($parameters) && !array_is_list($parameters)) {
                $parameters['boost'] = $boosts[$field];
            } else {
                $parameters = ['query' => $parameters, 'boost' => $boosts[$field]];
            }

            $fields[$field] = $parameters;
        }

        return $fields;
    }

    /**
     * @param list<mixed> $fields
     * @param array<string, float> $boosts
     * @return list<mixed>
     */
    private function transformFieldList(array $fields, array $boosts): array
    {
        foreach ($fields as $index => $fieldExpression) {
            if (!is_string($fieldExpression)) {
                continue;
            }

            $field = explode('^', $fieldExpression, 2)[0];

            if (isset($boosts[$field])) {
                $fields[$index] = $field . '^' . $this->formatBoost($boosts[$field]);
            }
        }

        return $fields;
    }

    private function formatBoost(float $boost): string
    {
        if (!is_finite($boost) || $boost < 0.1 || $boost > 20.0) {
            throw new UnexpectedValueException('Active field boost is outside the supported range');
        }

        if (floor($boost) === $boost) {
            return (string)(int)$boost;
        }

        return rtrim(rtrim(sprintf('%.4F', $boost), '0'), '.');
    }
}
