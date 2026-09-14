# Security reports

Do not put vulnerabilities, access tokens, signed download URLs, database dumps
or private store details in a public issue or pull request.

Email [Matt MacDougall](mailto:matt.macdougall@rocketweb.com) with the subject
`Mage-OS demo catalog security report`. Send a redacted summary first, not live
credentials or a database export. Include the affected commit or release,
runtime versions, impact and a minimal reproducer using synthetic data.

If GitHub's private vulnerability reporting is enabled for this repository, you
can use **Security → Report a vulnerability** instead. That route is optional;
this document does not imply it is currently enabled.

This is prerelease lab tooling. There is no promised response deadline, bounty,
or maintained-version security support window. Use an isolated, disposable
installation, keep Mage-OS and its dependencies updated, and back up the empty
baseline before imports. Report issues in upstream packages to their respective
maintainers; identify any catalog integration that makes the issue reproducible.

Do not test against demo servers or other people's stores without permission.
