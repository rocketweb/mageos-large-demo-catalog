<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Baseline;

use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplate;
use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineTemplateHydrator;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use PHPUnit\Framework\TestCase;

class BaselineTemplateHydratorTest extends TestCase
{
    public function testReconstructsCanonicalTemplateAndEscapedQueryPaths(): void
    {
        $template = [
            'index' => 'magento2_product_1',
            'body' => [
                'query' => [
                    'match' => [
                        'name/primary' => ['query~text' => BaselineTemplate::QUERY_TEXT_VARIABLE],
                    ],
                ],
            ],
        ];

        $hydrated = (new BaselineTemplateHydrator(new CanonicalJson()))->hydrate($template);

        self::assertSame(['/body/query/match/name~1primary/query~0text'], $hydrated->getQueryTextPaths());
        self::assertSame($template, $hydrated->getTemplate());
        self::assertSame((new CanonicalJson())->hash($template), $hydrated->getTemplateHash());
    }
}
