<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Configuration;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;

class FieldBoostCompiler
{
    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    /**
     * @param array<string, array{searchable: bool, sensitive: bool, dynamic: bool, type: string}> $capabilities
     * @param array<string, float> $boosts
     */
    public function compile(
        BaselineTemplate $baseline,
        array $capabilities,
        array $boosts,
        ?string $baselineConfigurationHash = null
    ): CandidateConfiguration {
        if ($boosts === []) {
            throw new InvalidArgumentException('Candidate must contain at least one field boost');
        }

        ksort($boosts, SORT_STRING);
        $this->validateBoosts($capabilities, $boosts);
        $seenFields = [];
        $template = $this->transformFields($baseline->getTemplate(), $boosts, $seenFields);

        foreach (array_keys($boosts) as $field) {
            if (!isset($seenFields[$field])) {
                throw new InvalidArgumentException(
                    'Candidate boost does not match a captured query field: ' . $field
                );
            }
        }

        $transformation = ['type' => 'FIELD_BOOST', 'boosts' => $boosts];
        $configurationHash = $this->canonicalJson->hash([
            'baseline_configuration_sha256' => $baselineConfigurationHash ?? $baseline->getTemplateHash(),
            'template' => $template,
            'transformation' => $transformation,
        ]);

        return new CandidateConfiguration($template, $transformation, $configurationHash);
    }

    /**
     * @param array<string, array{searchable: bool, sensitive: bool, dynamic: bool, type: string}> $capabilities
     * @param array<string, float> $boosts
     */
    private function validateBoosts(array $capabilities, array $boosts): void
    {
        foreach ($boosts as $field => $boost) {
            if (!isset($capabilities[$field])) {
                throw new InvalidArgumentException(
                    'Candidate field is not in the approved mapping registry: ' . $field
                );
            }

            $capability = $capabilities[$field];
            $eligibleType = in_array($capability['type'], ['text', 'keyword'], true);

            if (
                !$capability['searchable']
                || $capability['sensitive']
                || $capability['dynamic']
                || !$eligibleType
            ) {
                throw new InvalidArgumentException('Candidate field is not eligible for boosting: ' . $field);
            }

            if (!is_finite($boost) || $boost < 0.1 || $boost > 20.0) {
                throw new InvalidArgumentException('Candidate field boost must be between 0.1 and 20.0');
            }
        }
    }

    /**
     * @param array<string, float> $boosts
     * @param array<string, true> $seenFields
     */
    private function transformFields(mixed $value, array $boosts, array &$seenFields): mixed
    {
        if (!is_array($value)) {
            return $value;
        }

        $transformed = [];

        foreach ($value as $key => $item) {
            if ($key === 'fields' && is_array($item) && array_is_list($item)) {
                $transformed[$key] = $this->transformFieldList($item, $boosts, $seenFields);
                continue;
            }

            if (
                is_string($key)
                && in_array($key, ['match', 'match_phrase', 'match_phrase_prefix'], true)
                && is_array($item)
                && !array_is_list($item)
            ) {
                $transformed[$key] = $this->transformMatchFields($item, $boosts, $seenFields);
                continue;
            }

            $transformed[$key] = $this->transformFields($item, $boosts, $seenFields);
        }

        return $transformed;
    }

    /**
     * @param array<string, mixed> $fields
     * @param array<string, float> $boosts
     * @param array<string, true> $seenFields
     * @return array<string, mixed>
     */
    private function transformMatchFields(array $fields, array $boosts, array &$seenFields): array
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
            $seenFields[$field] = true;
        }

        return $fields;
    }

    /**
     * @param list<mixed> $fields
     * @param array<string, float> $boosts
     * @param array<string, true> $seenFields
     * @return list<mixed>
     */
    private function transformFieldList(array $fields, array $boosts, array &$seenFields): array
    {
        foreach ($fields as $index => $fieldExpression) {
            if (!is_string($fieldExpression)) {
                continue;
            }

            $field = explode('^', $fieldExpression, 2)[0];

            if (!isset($boosts[$field])) {
                continue;
            }

            $fields[$index] = $field . '^' . $this->formatBoost($boosts[$field]);
            $seenFields[$field] = true;
        }

        return $fields;
    }

    private function formatBoost(float $boost): string
    {
        if (floor($boost) === $boost) {
            return (string)(int)$boost;
        }

        return rtrim(rtrim(sprintf('%.4F', $boost), '0'), '.');
    }
}
