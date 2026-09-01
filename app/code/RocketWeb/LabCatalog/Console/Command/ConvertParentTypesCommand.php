<?php

declare(strict_types=1);

namespace RocketWeb\LabCatalog\Console\Command;

use Magento\Framework\Console\Cli;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Input\InputOption;
use Symfony\Component\Console\Output\OutputInterface;

class ConvertParentTypesCommand extends Command
{
    private const COMMAND_NAME = 'lab:wands:convert-parents';

    public function __construct(
        private readonly \RocketWeb\LabCatalog\Model\Catalog\ParentTypeConverter $parentTypeConverter,
    ) {
        parent::__construct();
    }

    protected function configure(): void
    {
        $this->setName(self::COMMAND_NAME);
        $this->setDescription('Validate or apply a bounded batch of WANDS parent product type conversions.');
        $this->addOption('file', null, InputOption::VALUE_REQUIRED, 'JSON Lines manifest inside the Mage-OS root.');
        $this->addOption('offset', null, InputOption::VALUE_REQUIRED, 'Zero-based manifest record offset.', '0');
        $this->addOption('limit', null, InputOption::VALUE_REQUIRED, 'Batch size from 1 to 500.', '100');
        $this->addOption('dry-run', null, InputOption::VALUE_NONE, 'Validate without changing product types.');
        $this->addOption(
            'reverse',
            null,
            InputOption::VALUE_NONE,
            'Remove configurable relations and restore simple types.'
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
            $result = $this->parentTypeConverter->execute(
                $sourceFile,
                filter_var($input->getOption('offset'), FILTER_VALIDATE_INT, FILTER_NULL_ON_FAILURE) ?? -1,
                filter_var($input->getOption('limit'), FILTER_VALIDATE_INT, FILTER_NULL_ON_FAILURE) ?? -1,
                (bool)$input->getOption('dry-run'),
                (bool)$input->getOption('reverse'),
            );
            $output->writeln(json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR));
            return Cli::RETURN_SUCCESS;
        } catch (\InvalidArgumentException $exception) {
            $output->writeln('<error>' . $exception->getMessage() . '</error>');
            return Cli::RETURN_INVALID;
        } catch (\Throwable $exception) {
            $output->writeln('<error>' . $exception->getMessage() . '</error>');
            return Cli::RETURN_FAILURE;
        }
    }
}
