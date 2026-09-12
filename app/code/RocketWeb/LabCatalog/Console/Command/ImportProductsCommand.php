<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Console\Command;

use Magento\Framework\Console\Cli;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Input\InputOption;
use Symfony\Component\Console\Output\OutputInterface;

class ImportProductsCommand extends Command
{
    private const COMMAND_NAME = 'lab:wands:import';

    public function __construct(
        private readonly \RocketWeb\LabCatalog\Model\Catalog\ProductImporter $productImporter,
    ) {
        parent::__construct();
    }

    protected function configure(): void
    {
        $this->setName(self::COMMAND_NAME);
        $this->setDescription('Validate and import a prepared WANDS Magento product CSV.');
        $this->addOption('file', null, InputOption::VALUE_REQUIRED, 'CSV path inside the Mage-OS project root.');
        $this->addOption(
            'validate-only',
            null,
            InputOption::VALUE_NONE,
            'Validate the CSV without changing products.'
        );
        $this->addOption(
            'reconcile-bundles',
            null,
            InputOption::VALUE_NONE,
            'Atomically remove existing options for a bounded WANDS bundle CSV before importing its exact assortment.'
        );
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
            $result = $this->productImporter->execute(
                $sourceFile,
                (bool)$input->getOption('validate-only'),
                (bool)$input->getOption('reconcile-bundles')
            );
            $output->writeln(json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR));
            return Cli::RETURN_SUCCESS;
        } catch (\Throwable $exception) {
            $output->writeln('<error>' . $exception->getMessage() . '</error>');
            return Cli::RETURN_FAILURE;
        }
    }
}
