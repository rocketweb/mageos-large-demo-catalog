<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Model\OpenSearch;

use OpenSearch\Exception\HttpExceptionInterface;
use RuntimeException;
use Throwable;

class SearchRelevanceTransportException extends RuntimeException
{
    public const INVALID_REQUEST = 'INVALID_REQUEST';
    public const AUTHENTICATION_FAILED = 'AUTHENTICATION_FAILED';
    public const AUTHORIZATION_FAILED = 'AUTHORIZATION_FAILED';
    public const REMOTE_NOT_FOUND = 'REMOTE_NOT_FOUND';
    public const REMOTE_CONFLICT = 'REMOTE_CONFLICT';
    public const REMOTE_TIMEOUT = 'REMOTE_TIMEOUT';
    public const REMOTE_THROTTLED = 'REMOTE_THROTTLED';
    public const REMOTE_FAILURE = 'REMOTE_FAILURE';
    public const REMOTE_UNAVAILABLE = 'REMOTE_UNAVAILABLE';
    public const TRANSPORT_FAILURE = 'TRANSPORT_FAILURE';

    private function __construct(
        string $message,
        private readonly string $reasonCode,
        private readonly ?int $statusCode,
        private readonly bool $retryable,
        Throwable $previous
    ) {
        parent::__construct($message, 0, $previous);
    }

    public static function fromOpenSearch(Throwable $exception): self
    {
        $statusCode = self::resolveStatusCode($exception);
        [$reasonCode, $message, $retryable] = self::classify($exception, $statusCode);

        return new self($message, $reasonCode, $statusCode, $retryable, $exception);
    }

    public function getReasonCode(): string
    {
        return $this->reasonCode;
    }

    public function getStatusCode(): ?int
    {
        return $this->statusCode;
    }

    public function isRetryable(): bool
    {
        return $this->retryable;
    }

    private static function resolveStatusCode(Throwable $exception): ?int
    {
        if ($exception instanceof HttpExceptionInterface) {
            return $exception->getStatusCode();
        }

        return match ($exception::class) {
            'OpenSearch\Common\Exceptions\BadRequest400Exception' => 400,
            'OpenSearch\Common\Exceptions\RequestTimeout408Exception' => 408,
            'OpenSearch\Common\Exceptions\Conflict409Exception' => 409,
            'OpenSearch\Common\Exceptions\ServerErrorResponseException' => 500,
            default => null,
        };
    }

    /**
     * @return array{0: string, 1: string, 2: bool}
     */
    private static function classify(Throwable $exception, ?int $statusCode): array
    {
        if ($exception::class === 'OpenSearch\Common\Exceptions\NoNodesAvailableException') {
            return [
                self::REMOTE_UNAVAILABLE,
                'OpenSearch Search Relevance is temporarily unavailable',
                true,
            ];
        }

        return match (true) {
            $statusCode === 400 => [
                self::INVALID_REQUEST,
                'OpenSearch rejected the Search Relevance request',
                false,
            ],
            $statusCode === 401 => [
                self::AUTHENTICATION_FAILED,
                'OpenSearch authentication failed',
                false,
            ],
            $statusCode === 403 => [
                self::AUTHORIZATION_FAILED,
                'OpenSearch denied the Search Relevance operation',
                false,
            ],
            $statusCode === 404 => [
                self::REMOTE_NOT_FOUND,
                'The OpenSearch Search Relevance resource is unavailable',
                false,
            ],
            $statusCode === 408 => [
                self::REMOTE_TIMEOUT,
                'OpenSearch Search Relevance timed out',
                true,
            ],
            $statusCode === 409 => [
                self::REMOTE_CONFLICT,
                'OpenSearch rejected the operation because the resource changed',
                false,
            ],
            $statusCode === 429 => [
                self::REMOTE_THROTTLED,
                'OpenSearch Search Relevance is temporarily throttled',
                true,
            ],
            $statusCode === 503 => [
                self::REMOTE_UNAVAILABLE,
                'OpenSearch Search Relevance is temporarily unavailable',
                true,
            ],
            $statusCode !== null && $statusCode >= 500 => [
                self::REMOTE_FAILURE,
                'OpenSearch Search Relevance returned a server error',
                true,
            ],
            default => [
                self::TRANSPORT_FAILURE,
                'OpenSearch Search Relevance could not be reached',
                true,
            ],
        };
    }
}
