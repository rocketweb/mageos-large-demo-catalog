<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Console\Command;

use Magento\Framework\Console\Cli;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Input\InputOption;
use Symfony\Component\Console\Output\OutputInterface;

class SeedQueriesCommand extends Command
{
    private const COMMAND_NAME = 'lab:wands:seed-queries';

    public function __construct(
        private readonly \RocketWeb\LabCatalog\Model\Catalog\QuerySeeder $querySeeder,
    ) {
        parent::__construct();
    }

    protected function configure(): void
    {
        $this->setName(self::COMMAND_NAME);
        $this->setDescription('Seed the WANDS queries into search history for Workbench snapshots.');
        $this->addOption('file', null, InputOption::VALUE_REQUIRED, 'Path to the pinned WANDS query.csv file.');
        $this->addOption('store', null, InputOption::VALUE_REQUIRED, 'Target store-view code.', 'wands');
        parent::configure();
    }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        $sourceFile = (string)$input->getOption('file');

        if ($sourceFile === '') {
            $output->writeln('<error>--file is required.</error>');
            return Cli::RETURN_INVALID;
        }

        try {
            $count = $this->querySeeder->execute($sourceFile, (string)$input->getOption('store'));
            $output->writeln(json_encode(['seeded_queries' => $count], JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR));
            return Cli::RETURN_SUCCESS;
        } catch (\Throwable $exception) {
            $output->writeln('<error>' . $exception->getMessage() . '</error>');
            return Cli::RETURN_FAILURE;
        }
    }
}
