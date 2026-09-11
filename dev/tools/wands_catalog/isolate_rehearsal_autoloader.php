<?php
declare(strict_types=1);

function isolateRehearsalAutoloader(\Composer\Autoload\ClassLoader $sourceLoader, string $source, string $root): \Composer\Autoload\ClassLoader
{
    $normalize = static function (string $path): string {
        $parts = [];
        foreach (explode('/', $path) as $part) {
            if ($part === '' || $part === '.') {continue;}
            if ($part === '..') {array_pop($parts);} else {$parts[] = $part;}
        }
        return '/'.implode('/', $parts);
    };
    $generated = $normalize(realpath($source.'/generated') ?: $source.'/generated').'/';
    $allowed = static fn(string $path): bool => !str_starts_with($normalize(realpath($path) ?: $path).'/', $generated);
    foreach (get_declared_classes() as $class) {
        $file = (new ReflectionClass($class))->getFileName();
        if ($file && !$allowed($file)) {throw new RuntimeException('Source generated class loaded before isolation');}
    }
    $loader = new \Composer\Autoload\ClassLoader();
    foreach ($sourceLoader->getPrefixes() as $prefix => $paths) {$loader->set($prefix, array_values(array_filter($paths, $allowed)));}
    $loader->set('', array_values(array_filter($sourceLoader->getFallbackDirs(), $allowed)));
    foreach ($sourceLoader->getPrefixesPsr4() as $prefix => $paths) {$loader->setPsr4($prefix, array_values(array_filter($paths, $allowed)));}
    $loader->setPsr4('', array_values(array_filter($sourceLoader->getFallbackDirsPsr4(), $allowed)));
    $loader->addClassMap(array_filter($sourceLoader->getClassMap(), $allowed));
    $loader->add('', $root.'/generated/code', true);
    $loader->setClassMapAuthoritative(false);
    $loader->setUseIncludePath(false);
    $sourceLoader->unregister();
    $loader->register(true);
    return $loader;
}
