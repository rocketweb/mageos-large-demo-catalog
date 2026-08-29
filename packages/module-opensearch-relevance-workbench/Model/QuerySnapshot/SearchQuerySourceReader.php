<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\QuerySnapshot;

use DateTimeImmutable;
use InvalidArgumentException;
use Magento\Framework\App\ResourceConnection;

class SearchQuerySourceReader
{
    private const MAXIMUM_SOURCE_ROWS = 100000;

    public function __construct(private readonly ResourceConnection $resourceConnection)
    {
    }

    /**
     * @return list<array<string, int|string|null>>
     */
    public function read(
        int $storeId,
        string $sourceWindowStart,
        string $sourceWindowEnd,
        int $sourceLimit = self::MAXIMUM_SOURCE_ROWS
    ): array {
        if ($storeId < 1) {
            throw new InvalidArgumentException('Query source requires a customer store view');
        }

        $start = new DateTimeImmutable($sourceWindowStart);
        $end = new DateTimeImmutable($sourceWindowEnd);

        if ($start > $end) {
            throw new InvalidArgumentException('Query source window start must not follow its end');
        }

        if ($sourceLimit < 1 || $sourceLimit > self::MAXIMUM_SOURCE_ROWS) {
            throw new InvalidArgumentException('Query source row limit is outside the supported range');
        }

        $connection = $this->resourceConnection->getConnection();
        $select = $connection->select()
            ->from(
                $this->resourceConnection->getTableName('search_query'),
                [
                    'query_id',
                    'query_text',
                    'num_results',
                    'popularity',
                    'redirect',
                    'store_id',
                    'is_active',
                    'updated_at',
                ]
            )
            ->where('store_id = ?', $storeId)
            ->where('is_active = ?', 1)
            ->where('updated_at >= ?', $start->format('Y-m-d H:i:s'))
            ->where('updated_at <= ?', $end->format('Y-m-d H:i:s'))
            ->order(['updated_at ASC', 'query_id ASC'])
            ->limit($sourceLimit);

        return array_values($connection->fetchAll($select));
    }
}
