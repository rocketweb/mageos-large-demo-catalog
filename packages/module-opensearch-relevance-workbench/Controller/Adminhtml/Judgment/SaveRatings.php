<?php

declare(strict_types=1);

namespace MageOS\OpenSearchRelevanceWorkbench\Controller\Adminhtml\Judgment;

use InvalidArgumentException;
use Magento\Backend\App\Action;
use Magento\Backend\App\Action\Context;
use Magento\Backend\Model\Auth\Session;
use Magento\Framework\App\Action\HttpPostActionInterface;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\HumanJudgmentSetFactory;
use MageOS\OpenSearchRelevanceWorkbench\Model\Judgment\HumanRatingQueueService;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\BaselineConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\CandidateConfigurationRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\HumanJudgmentRepository;
use MageOS\OpenSearchRelevanceWorkbench\Model\Persistence\QuerySnapshotRepository;
use Throwable;

class SaveRatings extends Action implements HttpPostActionInterface
{
    public const ADMIN_RESOURCE = 'MageOS_OpenSearchRelevanceWorkbench::curate_ratings';

    public function __construct(
        Context $context,
        private readonly BaselineConfigurationRepository $baselineRepository,
        private readonly CandidateConfigurationRepository $candidateRepository,
        private readonly QuerySnapshotRepository $snapshotRepository,
        private readonly HumanRatingQueueService $queueService,
        private readonly HumanJudgmentSetFactory $judgmentSetFactory,
        private readonly HumanJudgmentRepository $judgmentRepository,
        private readonly Session $authSession
    ) {
        parent::__construct($context);
    }

    public function execute()
    {
        try {
            $candidate = $this->candidateRepository->get(
                (string)$this->getRequest()->getParam('candidate_uuid', '')
            );
            $baseline = $this->baselineRepository->get($candidate->getParentBaselineUuid());
            $snapshotUuid = (string)$this->getRequest()->getParam('snapshot_uuid', '');
            $snapshot = $this->snapshotRepository->getApproved($snapshotUuid);
            $queue = $this->queueService->build($baseline, $candidate, $snapshot);
            $allowedPairs = [];

            foreach ($queue as $item) {
                $allowedPairs[$item['query_hash'] . "\0" . $item['document_id']] = true;
            }

            $submittedRatings = $this->getRequest()->getParam('ratings', []);

            if (!is_array($submittedRatings)) {
                throw new InvalidArgumentException('Human ratings payload must be an array');
            }

            $ratings = [];

            foreach ($submittedRatings as $submittedRating) {
                if (!is_array($submittedRating)) {
                    throw new InvalidArgumentException('Human rating entry must be an array');
                }

                $queryHash = (string)($submittedRating['query_hash'] ?? '');
                $documentId = (string)($submittedRating['document_id'] ?? '');
                $ratingValue = $submittedRating['rating'] ?? null;

                if (!isset($allowedPairs[$queryHash . "\0" . $documentId]) || !is_numeric($ratingValue)) {
                    throw new InvalidArgumentException('Human rating references a pair outside the frozen queue');
                }

                $ratings[] = [
                    'query_hash' => $queryHash,
                    'document_id' => $documentId,
                    'rating' => (float)$ratingValue,
                ];
            }

            $userId = (int)($this->authSession->getUser()?->getId() ?? 0);
            $judgmentSet = $this->judgmentSetFactory->create(
                $snapshot,
                $baseline->getIndexEvidenceHash(),
                $ratings,
                $userId,
                gmdate(DATE_RFC3339)
            );
            $judgmentUuid = $this->judgmentRepository->save(
                $judgmentSet,
                $snapshotUuid,
                $baseline->getIndexEvidenceUuid(),
                bin2hex(random_bytes(16))
            );
            $this->messageManager->addSuccessMessage(
                __('Saved immutable human judgment set %1.', $judgmentUuid)
            );
        } catch (Throwable) {
            $this->messageManager->addErrorMessage(
                __('Human ratings were not saved. Rebuild the queue and review every submitted pair.')
            );
        }

        return $this->resultRedirectFactory->create()->setPath('osrw/workbench/index', [
            '_fragment' => 'judge',
        ]);
    }
}
