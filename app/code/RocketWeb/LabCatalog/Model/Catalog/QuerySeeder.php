<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Model\Catalog;

class QuerySeeder
{
    public function __construct(
        private readonly \Magento\Framework\App\ResourceConnection $resourceConnection,
        private readonly \Magento\Store\Model\StoreManagerInterface $storeManager,
    ) {
    }

    public function execute(string $sourceFile, string $storeCode): int
    {
        $stream = fopen($sourceFile, 'rb');

        if ($stream === false) {
            throw new \RuntimeException('WANDS query file cannot be opened: ' . $sourceFile);
        }

        try {
            $header = fgetcsv($stream, 0, "\t", '"', '\\');

            if (!is_array($header)) {
                throw new \RuntimeException('WANDS query file has no header.');
            }

            $storeId = (int)$this->storeManager->getStore($storeCode)->getId();
            $rows = $this->readRows($stream, $header, $storeId);
        } finally {
            fclose($stream);
        }

        $connection = $this->resourceConnection->getConnection();
        $connection->beginTransaction();

        try {
            $tableName = $this->resourceConnection->getTableName('search_query');

            foreach (array_chunk($rows, 100) as $chunk) {
                $connection->insertOnDuplicate($tableName, $chunk, array_keys($chunk[0]));
            }

            $connection->commit();
        } catch (\Throwable $exception) {
            $connection->rollBack();
            throw $exception;
        }

        return count($rows);
    }

    private function readRows($stream, array $header, int $storeId): array
    {
        $rows = [];
        $updatedAt = gmdate('Y-m-d H:i:s');

        while (($values = fgetcsv($stream, 0, "\t", '"', '\\')) !== false) {
            if (count($values) !== count($header)) {
                continue;
            }

            $source = array_combine($header, $values);
            $queryText = trim((string)($source['query'] ?? ''));

            if ($queryText === '') {
                continue;
            }

            $queryId = (int)($source['query_id'] ?? count($rows));
            $rows[] = [
                'query_text' => $queryText,
                'num_results' => 1,
                'popularity' => max(1, 1000 - $queryId),
                'redirect' => null,
                'store_id' => $storeId,
                'display_in_terms' => 1,
                'is_active' => 1,
                'is_processed' => 1,
                'updated_at' => $updatedAt,
            ];
        }

        return $rows;
    }
}
