<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Controller\Adminhtml;

use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Configuration\CaptureBaseline;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Configuration\CreateCandidate;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Preflight\Run;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Snapshot\Approve;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Snapshot\Preview;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Snapshot\ApproveDraft;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Schedule\Approve as ApproveSchedule;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Schedule\Pause as PauseSchedule;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Judgment\PrepareQueue;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Judgment\SaveRatings;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Experiment\Accept;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Experiment\RunHuman;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Proposal\Export;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Activation\Apply;
use MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Activation\Rollback;
use PHPUnit\Framework\TestCase;
use ReflectionClass;

class AdminControllerSecurityTest extends TestCase
{
    /**
     * @return iterable<string, array{class-string, string}>
     */
    public static function postActions(): iterable
    {
        yield 'preflight' => [Run::class, 'MageOS_OpenSearchRelevanceWorkbench::view'];
        yield 'snapshot preview' => [
            Preview::class,
            'MageOS_OpenSearchRelevanceWorkbench::preview_queries',
        ];
        yield 'snapshot approval' => [
            Approve::class,
            'MageOS_OpenSearchRelevanceWorkbench::approve_snapshots',
        ];
        yield 'scheduled draft approval' => [
            ApproveDraft::class,
            'MageOS_OpenSearchRelevanceWorkbench::approve_snapshots',
        ];
        yield 'snapshot schedule approval' => [
            ApproveSchedule::class,
            'MageOS_OpenSearchRelevanceWorkbench::manage_settings',
        ];
        yield 'snapshot schedule pause' => [
            PauseSchedule::class,
            'MageOS_OpenSearchRelevanceWorkbench::manage_settings',
        ];
        yield 'baseline capture' => [
            CaptureBaseline::class,
            'MageOS_OpenSearchRelevanceWorkbench::manage_configurations',
        ];
        yield 'candidate creation' => [
            CreateCandidate::class,
            'MageOS_OpenSearchRelevanceWorkbench::manage_configurations',
        ];
        yield 'human rating queue' => [
            PrepareQueue::class,
            'MageOS_OpenSearchRelevanceWorkbench::curate_ratings',
        ];
        yield 'human rating save' => [
            SaveRatings::class,
            'MageOS_OpenSearchRelevanceWorkbench::curate_ratings',
        ];
        yield 'human experiment run' => [
            RunHuman::class,
            'MageOS_OpenSearchRelevanceWorkbench::run_experiments',
        ];
        yield 'human experiment acceptance' => [
            Accept::class,
            'MageOS_OpenSearchRelevanceWorkbench::run_experiments',
        ];
        yield 'review only proposal export' => [
            Export::class,
            'MageOS_OpenSearchRelevanceWorkbench::export_proposals',
        ];
        yield 'live configuration activation' => [
            Apply::class,
            'MageOS_OpenSearchRelevanceWorkbench::apply_live_configuration',
        ];
        yield 'live configuration rollback' => [
            Rollback::class,
            'MageOS_OpenSearchRelevanceWorkbench::apply_live_configuration',
        ];
    }

    #[\PHPUnit\Framework\Attributes\DataProvider('postActions')]
    public function testEveryAdminActionIsPostOnlyAndHasExactAcl(
        string $controllerClass,
        string $expectedAcl
    ): void {
        self::assertTrue(is_subclass_of($controllerClass, HttpPostActionInterface::class));
        $reflection = new ReflectionClass($controllerClass);

        self::assertSame($expectedAcl, $reflection->getConstant('ADMIN_RESOURCE'));
    }
}
