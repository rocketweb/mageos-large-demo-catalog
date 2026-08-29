<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Baseline;

use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use UnexpectedValueException;

class BaselineTemplateHydrator
{
    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    /**
     * @param array<array-key, mixed> $template
     */
    public function hydrate(array $template): BaselineTemplate
    {
        $queryTextPaths = [];
        $this->collectQueryTextPaths($template, '', $queryTextPaths);

        if ($queryTextPaths === []) {
            throw new UnexpectedValueException('Persisted baseline contains no query-text variable');
        }

        sort($queryTextPaths, SORT_STRING);

        return new BaselineTemplate(
            $template,
            $queryTextPaths,
            $this->canonicalJson->hash($template)
        );
    }

    /**
     * @param list<string> $queryTextPaths
     */
    private function collectQueryTextPaths(mixed $value, string $path, array &$queryTextPaths): void
    {
        if ($value === BaselineTemplate::QUERY_TEXT_VARIABLE) {
            $queryTextPaths[] = $path;

            return;
        }

        if (!is_array($value)) {
            return;
        }

        foreach ($value as $key => $item) {
            $this->collectQueryTextPaths($item, $this->appendPath($path, $key), $queryTextPaths);
        }
    }

    private function appendPath(string $path, int|string $key): string
    {
        $token = str_replace(['~', '/'], ['~0', '~1'], (string)$key);

        return $path . '/' . $token;
    }
}
