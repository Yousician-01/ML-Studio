# Security

## Report vulnerabilities privately

Do not disclose vulnerabilities, exploit details, sensitive logs, or affected
data in public Issues or PRs.

Once GitHub Private Vulnerability Reporting is enabled, use the repository's
**Security → Advisories → Report a vulnerability** action. Its availability must
be checked on GitHub; this repository cannot enable it through a file.

No private reporting email or other maintainer channel has been established in
this bootstrap. If the private report action is unavailable, withhold the
details. You may open a neutral administrative Issue asking maintainers to enable
private security reporting, without identifying the vulnerability, affected
component, exploit, or sensitive data. Share details only after a verified
private channel is available. No response-time guarantee is currently offered.

A private report should describe the affected revision, impact, reproduction
using synthetic data, and any mitigation, without including real secrets.

## Current support and assumptions

There are no application releases or supported version series yet. Report
problems against the relevant repository revision. A release support policy will
be defined when releases exist.

ML Studio is intended to execute Python/ML workloads locally. Code inherits the
permissions and access of the local runtime/container. A container alone is not
a claim of secure isolation, and no sandboxing is implemented here.

The prototype is not designed as a secure multi-tenant arbitrary-code execution
platform. Development instances should not be exposed to untrusted networks.
Do not execute untrusted code or model artifacts assuming the project isolates
them. Future ingestion, file access, dependencies, generated code, and workload
resource limits require security review during implementation.

Keep datasets and credentials out of public reports and commits. Ignore rules
are a convenience, not a security control. Tracking artifacts and AI context can
contain sensitive information too; planned logging and data-sharing boundaries
are described in [architecture](docs/architecture.md).
