<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Test\Unit\Configuration;

use DOMDocument;
use DOMXPath;
use PHPUnit\Framework\TestCase;

class AdminConfigurationTest extends TestCase
{
    public function testRegistersOneAdminRouteAndMonthlyWorkflowMenu(): void
    {
        $routeDocument = new DOMDocument();
        self::assertTrue($routeDocument->load(dirname(__DIR__, 3) . '/etc/adminhtml/routes.xml'));
        $routeXpath = new DOMXPath($routeDocument);
        $routes = $routeXpath->query('/config/router[@id="admin"]/route[@frontName="osrw"]');
        self::assertNotFalse($routes);
        self::assertCount(1, $routes);

        $menuDocument = new DOMDocument();
        self::assertTrue($menuDocument->load(dirname(__DIR__, 3) . '/etc/adminhtml/menu.xml'));
        $menuXpath = new DOMXPath($menuDocument);
        $menuItems = $menuXpath->query(
            '/config/menu/add[@id="MageOS_OpenSearchRelevanceWorkbench::workbench"]'
        );
        self::assertNotFalse($menuItems);
        self::assertCount(1, $menuItems);
    }

    public function testDeclaresSeparatePhaseOneMutationPermissions(): void
    {
        $document = new DOMDocument();
        self::assertTrue($document->load(dirname(__DIR__, 3) . '/etc/acl.xml'));
        $xpath = new DOMXPath($document);

        foreach (
            [
                'view',
                'preview_queries',
                'approve_snapshots',
                'curate_ratings',
                'manage_configurations',
                'run_experiments',
                'export_proposals',
                'apply_live_configuration',
            ] as $permission
        ) {
            $resources = $xpath->query(
                '//resource[@id="MageOS_OpenSearchRelevanceWorkbench::' . $permission . '"]'
            );
            self::assertNotFalse($resources);
            self::assertCount(1, $resources, 'Missing ACL resource ' . $permission);
        }
    }

    public function testRegistersDraftOnlySnapshotCron(): void
    {
        $document = new DOMDocument();
        self::assertTrue($document->load(dirname(__DIR__, 3) . '/etc/crontab.xml'));
        $xpath = new DOMXPath($document);
        $jobs = $xpath->query(
            '/config/group[@id="default"]/job[@name="osrw_prepare_snapshot_drafts"'
            . ' and @instance="MageOS\\OpenSearchRelevanceWorkbench\\Cron\\PrepareSnapshotDrafts"'
            . ' and @method="execute"]'
        );

        self::assertNotFalse($jobs);
        self::assertCount(1, $jobs);
    }

    public function testKeepsRatingQueueHeadingsVisibleDuringLongReviews(): void
    {
        $layout = new DOMDocument();
        self::assertTrue($layout->load(dirname(__DIR__, 3) . '/view/adminhtml/layout/osrw_workbench_index.xml'));
        $layoutXpath = new DOMXPath($layout);
        $stylesheets = $layoutXpath->query(
            '/page/head/css[@src="MageOS_OpenSearchRelevanceWorkbench::css/workbench.css"]'
        );

        self::assertNotFalse($stylesheets);
        self::assertCount(1, $stylesheets);

        $template = $this->readRepositoryFile('view/adminhtml/templates/workbench.phtml');
        self::assertMatchesRegularExpression(
            '/<\?php if \(\$ratingQueue !== \[\]\): \?>.*?'
            . '<table class="data-grid osrw-rating-queue">/s',
            $template
        );

        $stylesheet = $this->readRepositoryFile('view/adminhtml/web/css/workbench.css');
        self::assertStringContainsString('.osrw-rating-queue .data-grid-th', $stylesheet);
        self::assertStringContainsString('position: sticky', $stylesheet);
        self::assertStringContainsString('top: 0', $stylesheet);
    }

    public function testRendersTaskOrientedWorkbenchWithMagentoNativeController(): void
    {
        $template = $this->readRepositoryFile('view/adminhtml/templates/workbench.phtml');

        self::assertStringContainsString(
            'MageOS_OpenSearchRelevanceWorkbench/js/workbench',
            $template
        );

        foreach (['readiness', 'snapshot', 'tune', 'judge', 'compare', 'activate'] as $step) {
            self::assertStringContainsString('id="osrw-panel-' . $step . '"', $template);
            self::assertStringContainsString('data-osrw-step="' . $step . '"', $template);
        }

        $script = $this->readRepositoryFile('view/adminhtml/web/js/workbench.js');
        self::assertStringContainsString('aria-selected', $script);
        self::assertStringContainsString('window.history.replaceState', $script);

        self::assertStringContainsString('getWorkflowProgress', $template);
        self::assertStringContainsString('No exact experiment input set is ready', $template);
        self::assertStringContainsString('No candidate and snapshot pair is ready', $template);
        self::assertStringNotContainsString('osrw-eyebrow', $template);
    }

    public function testEveryWorkflowMutationReturnsToItsOwningStep(): void
    {
        foreach ([
            'Controller/Adminhtml/Preflight/Run.php' => 'readiness',
            'Controller/Adminhtml/Snapshot/Preview.php' => 'snapshot',
            'Controller/Adminhtml/Snapshot/Approve.php' => 'snapshot',
            'Controller/Adminhtml/Snapshot/ApproveDraft.php' => 'snapshot',
            'Controller/Adminhtml/Schedule/Approve.php' => 'snapshot',
            'Controller/Adminhtml/Schedule/Pause.php' => 'snapshot',
            'Controller/Adminhtml/Configuration/CaptureBaseline.php' => 'tune',
            'Controller/Adminhtml/Configuration/CreateCandidate.php' => 'tune',
            'Controller/Adminhtml/Judgment/PrepareQueue.php' => 'judge',
            'Controller/Adminhtml/Judgment/SaveRatings.php' => 'judge',
            'Controller/Adminhtml/Experiment/RunHuman.php' => 'compare',
            'Controller/Adminhtml/Experiment/Accept.php' => 'compare',
            'Controller/Adminhtml/Proposal/Export.php' => 'compare',
            'Controller/Adminhtml/Activation/Apply.php' => 'activate',
            'Controller/Adminhtml/Activation/Rollback.php' => 'activate',
        ] as $path => $step) {
            $source = $this->readRepositoryFile($path);
            self::assertMatchesRegularExpression(
                "/'_fragment'\\s*=>\\s*'" . preg_quote($step, '/') . "'/",
                $source,
                $path . ' must return to the ' . $step . ' workflow step'
            );
        }
    }

    private function readRepositoryFile(string $relativePath): string
    {
        $path = dirname(__DIR__, 3) . '/' . $relativePath;

        self::assertFileExists($path);
        $contents = file_get_contents($path);
        self::assertIsString($contents);

        return $contents;
    }
}
