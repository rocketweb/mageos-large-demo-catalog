<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Console\Command;

use Magento\Framework\Console\Cli;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Input\InputOption;
use Symfony\Component\Console\Output\OutputInterface;

class ProvisionCommand extends Command
{
    private const COMMAND_NAME = 'lab:wands:provision';

    public function __construct(
        private readonly \RocketWeb\LabCatalog\Model\Catalog\StoreProvisioner $storeProvisioner,
    ) {
        parent::__construct();
    }

    protected function configure(): void
    {
        $this->setName(self::COMMAND_NAME);
        $this->setDescription('Create or update the isolated WANDS website, store, root category, and Hyva theme.');
        $this->addOption(
            'base-url',
            null,
            InputOption::VALUE_REQUIRED,
            'Base URL for the WANDS store view.',
            'http://relevance.comtom.lab:8080/'
        );
        parent::configure();
    }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        try {
            $result = $this->storeProvisioner->provision((string)$input->getOption('base-url'));
            $output->writeln(json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES));
            return Cli::RETURN_SUCCESS;
        } catch (\Throwable $exception) {
            $output->writeln('<error>' . $exception->getMessage() . '</error>');
            if ($output->isVerbose()) {
                $output->writeln($exception->getTraceAsString());
            }
            return Cli::RETURN_FAILURE;
        }
    }
}
