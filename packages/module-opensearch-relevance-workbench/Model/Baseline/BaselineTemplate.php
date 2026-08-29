<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Baseline;

use LogicException;

class BaselineTemplate
{
    public const QUERY_TEXT_VARIABLE = '{{queryText}}';

    /**
     * @param array<array-key, mixed> $template
     * @param list<string> $queryTextPaths
     */
    public function __construct(
        private readonly array $template,
        private readonly array $queryTextPaths,
        private readonly string $templateHash
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
     * @return list<string>
     */
    public function getQueryTextPaths(): array
    {
        return $this->queryTextPaths;
    }

    public function getTemplateHash(): string
    {
        return $this->templateHash;
    }

    /**
     * @return array<array-key, mixed>
     */
    public function render(string $queryText): array
    {
        $queryTextPaths = array_fill_keys($this->queryTextPaths, true);
        $rendered = $this->renderValue($this->template, '', $queryText, $queryTextPaths);

        if (!is_array($rendered)) {
            throw new LogicException('Baseline template root must remain an array');
        }

        return $rendered;
    }

    /**
     * @param array<string, true> $queryTextPaths
     */
    private function renderValue(
        mixed $value,
        string $path,
        string $queryText,
        array $queryTextPaths
    ): mixed {
        if (isset($queryTextPaths[$path])) {
            if ($value !== self::QUERY_TEXT_VARIABLE) {
                throw new LogicException('Baseline query text path does not contain the expected variable');
            }

            return $queryText;
        }

        if (!is_array($value)) {
            return $value;
        }

        $rendered = [];

        foreach ($value as $key => $item) {
            $rendered[$key] = $this->renderValue(
                $item,
                $this->appendPath($path, $key),
                $queryText,
                $queryTextPaths
            );
        }

        return $rendered;
    }

    private function appendPath(string $path, int|string $key): string
    {
        $token = str_replace(['~', '/'], ['~0', '~1'], (string)$key);

        return $path . '/' . $token;
    }
}
