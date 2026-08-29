<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch;

use InvalidArgumentException;

class SearchRelevanceRequest
{
    private readonly string $method;
    private readonly string $path;

    /**
     * @var array<string, mixed>|null
     */
    private readonly ?array $body;

    /**
     * @param array<array-key, mixed>|null $body
     */
    public function __construct(
        string $method,
        string $path,
        ?array $body = null
    ) {
        $this->method = $method;
        $this->path = $path;

        if ($body === null) {
            $this->body = null;

            return;
        }

        if (array_is_list($body)) {
            throw new InvalidArgumentException('Search Relevance request body must be a JSON object');
        }

        $objectBody = [];

        foreach ($body as $key => $value) {
            if (!is_string($key)) {
                throw new InvalidArgumentException('Search Relevance request body must be a JSON object');
            }

            $objectBody[$key] = $value;
        }

        $this->body = $objectBody;
    }

    public function getMethod(): string
    {
        return $this->method;
    }

    public function getPath(): string
    {
        return $this->path;
    }

    /**
     * @return array<string, mixed>|null
     */
    public function getBody(): ?array
    {
        return $this->body;
    }
}
