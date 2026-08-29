<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\RemoteResource;

use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\RemoteResource\QuerySetContentIdentityFactory;
use PHPUnit\Framework\TestCase;

class QuerySetContentIdentityFactoryTest extends TestCase
{
    public function testRequestAndStoredRepresentationsHaveTheSameIdentity(): void
    {
        $factory = new QuerySetContentIdentityFactory(new CanonicalJson());
        $request = [
            'name' => 'owned-query-set',
            'description' => '  Disposable fixture  ',
            'sampling' => 'manual',
            'querySetQueries' => [
                ['queryText' => 'winter boots'],
                [
                    'queryText' => 'red shoes',
                    'referenceAnswer' => 'Red running shoes',
                    'category' => 'shoes',
                ],
            ],
        ];
        $stored = [
            'id' => 'remote-id',
            'name' => 'owned-query-set',
            'description' => 'Disposable fixture',
            'sampling' => 'manual',
            'timestamp' => '2026-08-26T12:00:00Z',
            'querySetQueries' => [
                ['queryText' => 'winter boots', 'customFields' => []],
                [
                    'queryText' => 'red shoes',
                    'customFields' => [
                        'category' => 'shoes',
                        'referenceAnswer' => 'Red running shoes',
                    ],
                ],
            ],
        ];

        self::assertSame($factory->hash($request), $factory->hash($stored));
    }

    public function testContentMutationChangesTheIdentity(): void
    {
        $factory = new QuerySetContentIdentityFactory(new CanonicalJson());
        $before = [
            'description' => 'Disposable fixture',
            'sampling' => 'manual',
            'querySetQueries' => [['queryText' => 'winter boots']],
        ];
        $after = $before;
        $after['querySetQueries'][0]['queryText'] = 'summer boots';

        self::assertNotSame($factory->hash($before), $factory->hash($after));
    }
}
