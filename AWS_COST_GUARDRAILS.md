# AWS zero-cost guardrails

These guardrails implement **EXPECTED AWS COST = $0**, independent of promotional credits. AWS Budgets are alerts and do not prevent charges; they are not an enforcement boundary.

## Hard prohibitions

- Create/start no resource unless its exact resource type, region, account-specific free offer, remaining monthly allowance and all metered dimensions are verified at the time of deployment and listed in `AWS_FREE_TIER_RESOURCE_ALLOWLIST.md`.
- Do not spend AWS promotional credits to justify chargeable usage. If a resource has a nonzero list-price estimate, classify it `BLOCKED_BY_ZERO_COST_POLICY` and do not deploy it.
- No GPU/EC2, NAT Gateway, load balancer, paid RDS/OpenSearch/Bedrock, Marketplace AMI, paid support, public IPv4, auto-scaling or paid fallback without an explicit user request changing this strict policy. No such change is assumed here.
- No unattended compute, schedule, event rule, or automatic recovery that could restart chargeable resources.
- No API key, AWS credential, or billing data in source control, job payloads, logs, or generated public artifacts.

## Fail-closed allowlist

Current allowed AWS resource creation: **none**. The allowlist must stay empty until account date, plan, region, Free Tier usage and exact quotas are verified via authenticated read-only console/API evidence. A service’s appearance in AWS's list of services accessible to a Free account is insufficient.

Where the account supports it without charge, use restrictive IAM/SCP policies to deny unapproved resource types and regions, instance starts, Marketplace subscriptions, public IPv4 assignment, VPC endpoints/NAT/load balancers, auto-scaling, and plan upgrades. These policies are additional guardrails, not proof of a zero bill. Do not create new guardrail resources if their cost is not verified at $0.

## Monitoring (not a billing cap)

- Before any future deployment, inspect the AWS Free Tier console and `GetFreeTierUsage` actual and forecast usage for every resource, across regions.
- Recheck after each deployment and periodically while any resource exists. The current AWS EC2 documentation warns that Free Tier usage data is not real time and may update only several times a day; do not use a lagging usage widget as authorization to consume the remaining margin. [AWS EC2 Free Tier usage](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html).
- Billing alerts/budgets may be used only after their own costs and delivery path are verified as $0. Alerts can arrive late and do not halt use. Never treat a $0 budget as a hard spend cap.
- Require substantial headroom below each monthly allowance, accounting for existing/shared usage and forecast uncertainty. If exact headroom cannot be established, deploy nothing.

## Shutdown and recovery

- No auto-scaling and no unattended GPU instances.
- Maintain a human-reviewed inventory; verify all regions and services before the end of any Free Tier offer/plan period.
- Set a dated shutdown review before account Free Plan expiration. Deleting compute does not necessarily delete volumes, snapshots, addresses, logs, DNS, or artifacts; inspect each explicitly.
- Do not auto-upgrade the AWS account plan. If AWS suspends a Free Plan account at expiration, do not upgrade as a recovery mechanism without a separate user request.
- If projected or actual charges are nonzero, stop new work, stop/delete the resource after preserving only user-approved data, and report `BLOCKED_BY_ZERO_COST_POLICY`.
