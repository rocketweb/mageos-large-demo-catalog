<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Plugin\OpenSearch;

use MageOS\OpenSearchRelevanceWorkbench\Model\Baseline\BaselineCaptureContext;
use MageOS\OpenSearchRelevanceWorkbench\Model\Activation\LiveQueryApplier;
use MageOS\OpenSearchRelevanceWorkbench\Plugin\OpenSearch\CaptureMappedQuery;
use Magento\Framework\Search\RequestInterface;
use Magento\OpenSearch\SearchAdapter\Mapper;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;
use RuntimeException;

class CaptureMappedQueryTest extends TestCase
{
    public function testReturnsMappedQueryUnchangedAndRecordsItInActiveContext(): void
    {
        $context = new BaselineCaptureContext();
        $applier = $this->createMock(LiveQueryApplier::class);
        $applier->expects(self::once())->method('apply')->willReturnArgument(0);
        $plugin = new CaptureMappedQuery($context, $applier, $this->createStub(LoggerInterface::class));
        $mapper = $this->createStub(Mapper::class);
        $mappedQuery = [
            'index' => 'catalogsearch_fulltext',
            'body' => ['query' => ['match_all' => (object)[]]],
            'track_total_hits' => true,
        ];
        $returnedQuery = null;
        $request = $this->quickSearchRequest();

        $captures = $context->capture(1, static function () use (
            $plugin,
            $mapper,
            $mappedQuery,
            $request,
            &$returnedQuery
        ): void {
            $returnedQuery = $plugin->afterBuildQuery($mapper, $mappedQuery, $request);
        });

        self::assertSame($mappedQuery, $returnedQuery);
        self::assertSame([$mappedQuery], $captures);
    }

    public function testLeavesOrdinaryInactiveMapperCallsUntouched(): void
    {
        $context = new BaselineCaptureContext();
        $applier = $this->createMock(LiveQueryApplier::class);
        $applier->expects(self::once())->method('apply')->willReturnArgument(0);
        $plugin = new CaptureMappedQuery($context, $applier, $this->createStub(LoggerInterface::class));
        $mappedQuery = ['body' => ['size' => 20]];

        self::assertSame(
            $mappedQuery,
            $plugin->afterBuildQuery(
                $this->createStub(Mapper::class),
                $mappedQuery,
                $this->quickSearchRequest()
            )
        );

        $captures = $context->capture(1, static function () use ($context): void {
            $context->record(['body' => ['size' => 10]]);
        });
        self::assertSame([['body' => ['size' => 10]]], $captures);
    }

    public function testFailsOpenAndCapturesStockQueryWhenLiveStateCannotBeRead(): void
    {
        $context = new BaselineCaptureContext();
        $applier = $this->createStub(LiveQueryApplier::class);
        $applier->method('apply')->willThrowException(new RuntimeException('database unavailable'));
        $logger = $this->createMock(LoggerInterface::class);
        $logger->expects(self::once())->method('error');
        $plugin = new CaptureMappedQuery($context, $applier, $logger);
        $mappedQuery = ['body' => ['query' => ['match_all' => []]]];
        $mapper = $this->createStub(Mapper::class);
        $request = $this->quickSearchRequest();

        $captures = $context->capture(1, static function () use ($plugin, $mapper, $mappedQuery, $request): void {
            self::assertSame(
                $mappedQuery,
                $plugin->afterBuildQuery($mapper, $mappedQuery, $request)
            );
        });

        self::assertSame([$mappedQuery], $captures);
    }

    public function testKeepsBaselineCaptureStockWhileReturningTheLiveQuery(): void
    {
        $context = new BaselineCaptureContext();
        $stockQuery = ['body' => ['query' => ['match' => ['name' => 'shoe']]]];
        $liveQuery = ['body' => ['query' => ['match' => ['name' => ['query' => 'shoe', 'boost' => 6.0]]]]];
        $applier = $this->createMock(LiveQueryApplier::class);
        $applier->method('apply')->with($stockQuery)->willReturn($liveQuery);
        $plugin = new CaptureMappedQuery($context, $applier, $this->createStub(LoggerInterface::class));
        $mapper = $this->createStub(Mapper::class);
        $request = $this->quickSearchRequest();
        $returned = [];

        $captures = $context->capture(1, static function () use (
            $plugin,
            $mapper,
            $stockQuery,
            $request,
            &$returned
        ): void {
            $returned = $plugin->afterBuildQuery($mapper, $stockQuery, $request);
        });

        self::assertSame($liveQuery, $returned);
        self::assertSame([$stockQuery], $captures);
    }

    public function testDoesNotApplyAStorefrontCandidateToGraphqlSearch(): void
    {
        $context = new BaselineCaptureContext();
        $applier = $this->createMock(LiveQueryApplier::class);
        $applier->expects(self::never())->method('apply');
        $plugin = new CaptureMappedQuery($context, $applier, $this->createStub(LoggerInterface::class));
        $request = $this->createStub(RequestInterface::class);
        $request->method('getName')->willReturn('graphql_product_search');
        $mappedQuery = ['body' => ['query' => ['match_all' => []]]];

        self::assertSame(
            $mappedQuery,
            $plugin->afterBuildQuery($this->createStub(Mapper::class), $mappedQuery, $request)
        );
    }

    private function quickSearchRequest(): RequestInterface
    {
        $request = $this->createStub(RequestInterface::class);
        $request->method('getName')->willReturn('quick_search_container');

        return $request;
    }
}
