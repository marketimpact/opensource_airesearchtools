## GitHub Actions independence — standing instruction, 19 October 2026

Tom requires all MarketImpact systems to operate without GitHub Actions. Do not introduce, restore, enable, dispatch, or require GitHub Actions for builds, tests, security scans, deployments, release artifacts, or scheduled operations. A self-hosted Actions runner still depends on the Actions service and does not satisfy this requirement.

Run equivalent checks through repository-owned scripts, an independent scheduler on the dedicated CI host, or a supported operator-run path. Preserve lint, type checks, unit/integration/browser tests, secret/data-export scans, knowledge validation, review, exact-revision evidence, deployment locking, health checks and rollback. Never fabricate passing statuses or treat skipped or unreported checks as success. Keep untrusted code and CI workloads off production hosts and away from production credentials.

During migration, preserve existing workflow definitions as reference until each replacement is verified. Do not disable a working safeguard or scheduled task before its independent replacement passes. Required GitHub checks must be published by the independent verifier rather than be bound to the GitHub Actions integration. GitHub may remain the source/review/status service; its Actions service must not be a prerequisite. Instructions elsewhere describing Actions are historical and subordinate to this policy. Any exception requires Tom’s explicit authorization in the current task.

# Agent instructions

