<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Console\Command;

use Magento\Framework\Console\Cli;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Input\InputOption;
use Symfony\Component\Console\Output\OutputInterface;

class CurateNavigationCommand extends Command
{
    public function __construct(
        private readonly \RocketWeb\LabCatalog\Model\Catalog\NavigationCurator $navigationCurator,
    ) {
        parent::__construct('lab:wands:curate-navigation');
    }

    protected function configure(): void
    {
        $this->setDescription('Curate nine WANDS departments, with Lighting and Rugs under Decor.');
        $this->addOption('dry-run', null, InputOption::VALUE_NONE, 'Show category changes without writing them.');
        parent::configure();
    }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        try {
            $output->writeln(json_encode(
                $this->navigationCurator->execute((bool)$input->getOption('dry-run')),
                JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR
            ));
            return Cli::RETURN_SUCCESS;
        } catch (\Throwable $exception) {
            $output->writeln('<error>' . $exception->getMessage() . '</error>');
            return Cli::RETURN_FAILURE;
        }
    }
}
