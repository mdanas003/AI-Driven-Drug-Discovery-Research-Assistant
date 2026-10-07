# AWS Free Tier deployment procedure

**Status:** Not deployed. This is a gated runbook. There are no AWS CLI credentials, profile, role, or region in the current environment. Do not install/configure AWS tooling or provision resources until the account-specific eligibility gate has been verified.

## Gate 0 — identify the account without creating resources

Using an authenticated AWS console session or read-only credentials, capture:

1. Account ID (record only securely), AWS account creation date, account plan (Free or Paid), Free Plan expiration, current credit balance and expiry. Credits must not be counted as permission to use chargeable resources.
2. Intended region and plan access to each candidate service.
3. Current month actual and forecast Free Tier offer usage and limits for every candidate service/usage type using the Free Tier console and `GetFreeTierUsage`; check all regions for existing account usage.
4. Existing resources/quotas, storage, public IPv4, data transfer, DNS/certificate resources and any shared/payer account effects.
5. Whether the account was created before 2025-07-15; EC2 Free Tier rules differ across cohorts. Query the account’s own eligible instance types and AMIs; never infer from a generic webpage.

AWS documents that new Free Plan expiry depends on the earlier of six months and exhaustion of the promotional credit balance; Free Tier offers can vary by account plan and signup date. [AWS Free Tier FAQs](https://aws.amazon.com/free/free-tier-faqs/), [EC2 Free Tier usage](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html).

**Stop if any field is unknown, the plan/eligibility cannot be verified, an offer has no remaining allowance, the service requires a paid plan, or expected AWS bill is not exactly $0 without promotional credits.** A budget alarm is not a stop mechanism.

## Gate 1 — calculate and review before any change

For each candidate resource, record service, resource type, region, monthly request/runtime/storage/egress quantity, account-specific free offer name/limit/remaining amount, overage rate exposure, and expected bill. Require two independent checks: Free Tier offer usage/eligibility plus current AWS pricing for every metered dimension. Include public IPv4, snapshots, volumes, object requests, data transfer, logs, DNS, certificates and support where applicable.

The only deployment plan that currently meets a verifiable **EXPECTED AWS COST = $0** is no AWS resources. After account verification, update the allowlist and cost table. No one may deploy from this document alone.

## Gate 2 — control-plane-only adaptation

If a separately reviewed plan passes Gate 1, adapt/validate the light API, job state, health/status, and minimal metadata/artifact interfaces against only the resources explicitly allowlisted. Keep GPU/scientific workers disabled. No data-plane architecture change may mark a blocked science stage successful. Do not add S3/API Gateway/Lambda/DynamoDB just because AWS lists those services as available.

## Safety conditions

- No EC2, GPU, or any compute instance unless that exact instance type, AMI, region, hours, EBS volume and account-specific $0 allowance are all confirmed first. User’s strict rule also prohibits any resource that could charge if its allowance is exceeded; this may rule out EC2 even if a free offer exists.
- No NAT Gateway, load balancer, RDS, OpenSearch, Bedrock/model API, Marketplace AMI, paid support, public IPv4, auto-scaling, or credits-funded service.
- No public endpoint until its ingress, DNS, TLS, data transfer and abuse controls have independently verified $0 bounds. Otherwise keep API local/private.
- No unattended worker or scheduled GPU. No paid fallback or automatic upgrade.
- Stop deployment immediately if eligibility data becomes stale, an account plan changes, or any charge/forecast appears.

## Verification and rollback

Before a deployment: review the completed allowlist, estimate, and `AWS_COST_GUARDRAILS.md`; use read-only account queries to recheck quotas immediately before apply. After any approved deployment, query resources globally and across regions, Free Tier actual/forecast use, bill/Cost Explorer, and service health. Record actual usage. If any cost is forecast or observed, stop/delete only after checking data retention/cleanup consequences; report the incident and do not recreate it.

No deployment steps in this runbook have been executed.
