<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Configuration;

use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;

class MappedFieldCapabilityRegistry
{
    /**
     * @param array<string, mixed> $mapping
     * @param list<string> $approvedAttributeCodes
     * @return array<string, array{searchable: bool, sensitive: bool, dynamic: bool, type: string}>
     */
    public function build(
        BaselineTemplate $template,
        array $mapping,
        array $approvedAttributeCodes
    ): array {
        $templateArray = $template->getTemplate();
        $query = $templateArray['body']['query'] ?? [];
        $capturedFields = [];
        $this->collectQueryFields($query, $capturedFields);
        $properties = $mapping['properties'] ?? [];

        if (!is_array($properties)) {
            return [];
        }

        $approved = array_fill_keys($approvedAttributeCodes, true);
        $capabilities = [];

        foreach (array_keys($capturedFields) as $field) {
            $attributeCode = str_ends_with($field, '_value')
                ? substr($field, 0, -strlen('_value'))
                : $field;
            $definition = $properties[$field] ?? null;

            if (!isset($approved[$attributeCode]) || !is_array($definition)) {
                continue;
            }

            $type = $definition['type'] ?? null;
            $searchable = in_array($type, ['text', 'keyword'], true)
                && ($definition['index'] ?? true) !== false;
            $sensitive = preg_match(
                '/(?:^|_)(?:email|phone|address|password|token|secret)(?:_|$)/i',
                $field
            ) === 1;

            if (!$searchable || $sensitive) {
                continue;
            }

            $capabilities[$field] = [
                'searchable' => true,
                'sensitive' => false,
                'dynamic' => false,
                'type' => (string)$type,
            ];
        }

        ksort($capabilities, SORT_STRING);

        return $capabilities;
    }

    /**
     * @param array<string, true> $fields
     */
    private function collectQueryFields(mixed $value, array &$fields): void
    {
        if (!is_array($value)) {
            return;
        }

        foreach ($value as $key => $item) {
            if (
                is_string($key)
                && in_array($key, ['match', 'match_phrase', 'match_phrase_prefix'], true)
                && is_array($item)
                && !array_is_list($item)
            ) {
                foreach (array_keys($item) as $field) {
                    if (is_string($field)) {
                        $fields[$field] = true;
                    }
                }
            }

            if ($key === 'fields' && is_array($item) && array_is_list($item)) {
                foreach ($item as $fieldExpression) {
                    if (is_string($fieldExpression)) {
                        $fields[explode('^', $fieldExpression, 2)[0]] = true;
                    }
                }
            }

            $this->collectQueryFields($item, $fields);
        }
    }
}
