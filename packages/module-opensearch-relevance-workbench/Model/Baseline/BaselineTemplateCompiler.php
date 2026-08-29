<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Baseline;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use UnexpectedValueException;

class BaselineTemplateCompiler
{
    public function __construct(private readonly CanonicalJson $canonicalJson)
    {
    }

    /**
     * @param array<array-key, mixed> $firstCapture
     * @param array<array-key, mixed> $secondCapture
     */
    public function compile(
        array $firstCapture,
        string $firstSentinel,
        array $secondCapture,
        string $secondSentinel
    ): BaselineTemplate {
        if ($firstSentinel === '' || $secondSentinel === '' || $firstSentinel === $secondSentinel) {
            throw new InvalidArgumentException('Baseline sentinels must be non-empty and distinct');
        }

        if (
            $firstSentinel === BaselineTemplate::QUERY_TEXT_VARIABLE
            || $secondSentinel === BaselineTemplate::QUERY_TEXT_VARIABLE
        ) {
            throw new InvalidArgumentException('Baseline sentinels must not use the reserved query variable');
        }

        $queryTextPaths = [];
        $template = $this->compileValue(
            $firstCapture,
            $secondCapture,
            $firstSentinel,
            $secondSentinel,
            '',
            $queryTextPaths
        );

        if (!is_array($template)) {
            throw new UnexpectedValueException('Baseline capture root must be an array');
        }

        if ($queryTextPaths === []) {
            throw new UnexpectedValueException('Baseline captures contain no exact query sentinel change');
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
    private function compileValue(
        mixed $first,
        mixed $second,
        string $firstSentinel,
        string $secondSentinel,
        string $path,
        array &$queryTextPaths
    ): mixed {
        if ($first === $firstSentinel && $second === $secondSentinel) {
            $queryTextPaths[] = $path;

            return BaselineTemplate::QUERY_TEXT_VARIABLE;
        }

        if ($first === BaselineTemplate::QUERY_TEXT_VARIABLE || $second === BaselineTemplate::QUERY_TEXT_VARIABLE) {
            $this->throwPathError('Baseline capture contains reserved query variable', $path);
        }

        if (
            $first === $firstSentinel
            || $first === $secondSentinel
            || $second === $firstSentinel
            || $second === $secondSentinel
        ) {
            $this->throwPathError('Baseline sentinel collision', $path);
        }

        if (is_array($first) || is_array($second)) {
            if (!is_array($first) || !is_array($second)) {
                $this->throwDifference($path);
            }

            return $this->compileArray(
                $first,
                $second,
                $firstSentinel,
                $secondSentinel,
                $path,
                $queryTextPaths
            );
        }

        if ($first !== $second) {
            $this->throwDifference($path);
        }

        return $first;
    }

    /**
     * @param array<array-key, mixed> $first
     * @param array<array-key, mixed> $second
     * @param list<string> $queryTextPaths
     * @return array<array-key, mixed>
     */
    private function compileArray(
        array $first,
        array $second,
        string $firstSentinel,
        string $secondSentinel,
        string $path,
        array &$queryTextPaths
    ): array {
        if (array_is_list($first) !== array_is_list($second) || count($first) !== count($second)) {
            $this->throwDifference($path);
        }

        foreach ($first as $key => $value) {
            if (!array_key_exists($key, $second)) {
                $this->throwDifference($path);
            }
        }

        $template = [];

        foreach ($first as $key => $value) {
            $template[$key] = $this->compileValue(
                $value,
                $second[$key],
                $firstSentinel,
                $secondSentinel,
                $this->appendPath($path, $key),
                $queryTextPaths
            );
        }

        return $template;
    }

    private function throwDifference(string $path): never
    {
        $this->throwPathError('Baseline captures differ', $path);
    }

    private function throwPathError(string $message, string $path): never
    {
        throw new UnexpectedValueException(sprintf(
            '%s at path %s',
            $message,
            $path === '' ? '/' : $path
        ));
    }

    private function appendPath(string $path, int|string $key): string
    {
        $token = str_replace(['~', '/'], ['~0', '~1'], (string)$key);

        return $path . '/' . $token;
    }
}
