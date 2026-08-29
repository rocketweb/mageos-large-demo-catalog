<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Model\Judgment;

use InvalidArgumentException;
use MageOS\OpenSearchRelevanceWorkbench\Model\CanonicalJson;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\HumanJudgmentSetFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\ApprovedQuerySnapshot;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\QuerySnapshotEntry;
use MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot\SnapshotPolicy;
use PHPUnit\Framework\TestCase;

class HumanJudgmentSetFactoryTest extends TestCase
{
    public function testBuildsStableImportedJudgmentPayloadFromApprovedSnapshot(): void
    {
        $snapshot = $this->snapshot();
        $factory = new HumanJudgmentSetFactory(new CanonicalJson());
        $ratings = [
            ['query_hash' => hash('sha256', 'red dress'), 'document_id' => '20', 'rating' => 0.5],
            ['query_hash' => hash('sha256', 'winter boots'), 'document_id' => '10', 'rating' => 1.0],
            ['query_hash' => hash('sha256', 'winter boots'), 'document_id' => '11', 'rating' => 0.0],
        ];

        $first = $factory->create($snapshot, str_repeat('e', 64), $ratings, 42, '2026-08-26T13:00:00+00:00');
        $second = $factory->create(
            $snapshot,
            str_repeat('e', 64),
            array_reverse($ratings),
            42,
            '2026-08-26T13:00:00+00:00'
        );

        self::assertSame($first->getJudgmentHash(), $second->getJudgmentHash());
        self::assertSame(
            [
                [
                    'query' => 'red dress',
                    'ratings' => [['docId' => '20', 'rating' => '0.5']],
                ],
                [
                    'query' => 'winter boots',
                    'ratings' => [
                        ['docId' => '10', 'rating' => '1.0'],
                        ['docId' => '11', 'rating' => '0.0'],
                    ],
                ],
            ],
            $first->getRemoteJudgmentRatings()
        );
        self::assertSame(3, $first->getRatingCount());
        self::assertSame(42, $first->getReviewedBy());
    }

    public function testRejectsRatingForQueryOutsideApprovedSnapshot(): void
    {
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Human rating references a query outside the approved snapshot');

        (new HumanJudgmentSetFactory(new CanonicalJson()))->create(
            $this->snapshot(),
            str_repeat('e', 64),
            [['query_hash' => str_repeat('f', 64), 'document_id' => '10', 'rating' => 1.0]],
            42,
            '2026-08-26T13:00:00+00:00'
        );
    }

    public function testRejectsUnsupportedRatingValue(): void
    {
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Human rating must be 0.0, 0.5, or 1.0');

        (new HumanJudgmentSetFactory(new CanonicalJson()))->create(
            $this->snapshot(),
            str_repeat('e', 64),
            [[
                'query_hash' => hash('sha256', 'winter boots'),
                'document_id' => '10',
                'rating' => 0.7,
            ]],
            42,
            '2026-08-26T13:00:00+00:00'
        );
    }

    public function testRejectsEmptyHumanJudgment(): void
    {
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Human judgment requires at least one reviewed rating');

        (new HumanJudgmentSetFactory(new CanonicalJson()))->create(
            $this->snapshot(),
            str_repeat('e', 64),
            [],
            42,
            '2026-08-26T13:00:00+00:00'
        );
    }

    private function snapshot(): ApprovedQuerySnapshot
    {
        return new ApprovedQuerySnapshot(
            1,
            [
                new QuerySnapshotEntry(1, 'winter boots', hash('sha256', 'winter boots'), 20, 5, '2026-08-26 12:00:00'),
                new QuerySnapshotEntry(2, 'red dress', hash('sha256', 'red dress'), 10, 4, '2026-08-26 12:00:00'),
            ],
            new SnapshotPolicy(1, 10, 10, 20, false, 128, 'osrw-privacy-v1'),
            ['updated_at' => '2026-08-26 12:00:00', 'query_id' => 2],
            str_repeat('a', 64),
            42,
            '2026-08-26T12:30:00+00:00'
        );
    }
}
