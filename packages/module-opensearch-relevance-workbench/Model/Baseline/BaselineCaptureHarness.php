<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\Baseline;

use InvalidArgumentException;
use UnexpectedValueException;

class BaselineCaptureHarness
{
    public function __construct(
        private readonly \MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineCaptureContext $captureContext,
        private readonly \MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplateCompiler $templateCompiler,
        private readonly \MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson $canonicalJson
    ) {
    }

    /**
     * @param callable(string): void $mapQueryText
     * @param array<array-key, string> $validationQueries
     */
    public function capture(
        callable $mapQueryText,
        string $firstSentinel,
        string $secondSentinel,
        array $validationQueries
    ): BaselineCaptureResult {
        $validationQueries = $this->validateQueries($validationQueries);

        $sentinelCaptures = $this->captureContext->capture(
            2,
            static function () use ($mapQueryText, $firstSentinel, $secondSentinel): void {
                $mapQueryText($firstSentinel);
                $mapQueryText($secondSentinel);
            }
        );
        $template = $this->templateCompiler->compile(
            $sentinelCaptures[0],
            $firstSentinel,
            $sentinelCaptures[1],
            $secondSentinel
        );

        $validationCaptures = $this->captureContext->capture(
            count($validationQueries),
            static function () use ($mapQueryText, $validationQueries): void {
                foreach ($validationQueries as $queryText) {
                    $mapQueryText($queryText);
                }
            }
        );
        $validationEvidence = [];

        foreach ($validationQueries as $ordinal => $queryText) {
            $renderedRequest = $template->render($queryText);
            $nativeRequest = $validationCaptures[$ordinal];

            if ($this->canonicalJson->encode($renderedRequest) !== $this->canonicalJson->encode($nativeRequest)) {
                throw new UnexpectedValueException(sprintf(
                    'Baseline round-trip differs at validation sample %d',
                    $ordinal + 1
                ));
            }

            $validationEvidence[] = [
                'query_text_hash' => $this->canonicalJson->hash($queryText),
                'mapped_request_hash' => $this->canonicalJson->hash($nativeRequest),
            ];
        }

        return new BaselineCaptureResult($template, $validationEvidence);
    }

    /**
     * @param array<array-key, string> $validationQueries
     * @return list<string>
     */
    private function validateQueries(array $validationQueries): array
    {
        if (!array_is_list($validationQueries) || count($validationQueries) < 5) {
            throw new InvalidArgumentException(
                'Baseline validation requires at least five distinct non-empty queries'
            );
        }

        foreach ($validationQueries as $queryText) {
            if ($queryText === '') {
                throw new InvalidArgumentException(
                    'Baseline validation requires at least five distinct non-empty queries'
                );
            }
        }

        if (count(array_unique($validationQueries, SORT_STRING)) !== count($validationQueries)) {
            throw new InvalidArgumentException(
                'Baseline validation requires at least five distinct non-empty queries'
            );
        }

        return $validationQueries;
    }
}
