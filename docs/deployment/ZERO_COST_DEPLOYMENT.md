# Zero-cost AWS deployment status

**Status:** Not deployed. **AWS resources created:** 0. **Current AWS spend from this project:** $0 because no resources exist.

## Audit result

The read-only audit recorded on 2026-10-03 could not authenticate to AWS: AWS CLI and account credentials/profile/role were not available. Account creation cohort, plan, region, Free Tier offers and limits, current usage, existing resources, and potential billable usage remain unverified. No AWS resource is approved; the resource allowlist is empty.

AWS Free Tier offers vary by plan and account cohort. A service being accessible under a Free account does not establish that its usage is currently $0 for this account. Promotional credits do not count as a zero-cost allowance, and AWS Budgets are monitoring rather than a hard billing cap. Re-audit through the AWS Console or authenticated read-only `GetFreeTierUsage` API before proposing any resource.

## Non-negotiable controls

- Create no AWS resources until account, region, exact quota, current/forecast usage, and every metered cost dimension are verified.
- Require calculated expected cost of exactly $0 excluding credits. If uncertain or nonzero, mark `BLOCKED_BY_ZERO_COST_POLICY` and do not deploy.
- No AWS GPU/EC2, NAT Gateway, paid load balancer, RDS, OpenSearch, Bedrock/model API, Marketplace AMI, public IPv4, auto-scaling, or paid fallback.
- No AWS resource allowlist entries are currently authorized.
- Heavy scientific GPU work is outside AWS Free Tier. Keep AWS GPU workers disabled. The scientific architecture remains intact; unavailable models remain blocked.

## Control plane

The current API and SQLite queue are local/single-host components, not a verified AWS deployment. Any future control-plane proposal must account for compute time, requests, storage, public ingress, IPv4, DNS/TLS, logs and data transfer using account-specific limits. Do not infer that serverless or storage services are free from generic service-availability lists.

## Required next step

Authenticate directly through the AWS Console or provide a narrowly scoped read-only session. Do not send credentials in chat or commit them. Update the allowlist only with account-specific evidence. This audit is not authorization to provision resources.
