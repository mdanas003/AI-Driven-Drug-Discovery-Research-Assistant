# Zero-cost deployment status

**As of:** 2026-10-03  
**AWS provisioning performed:** No. This was a read-only feasibility audit.

## AWS FREE-TIER READY

- **No AWS deployment is currently AWS Free-Tier ready.** No AWS account ID, creation date, account plan, region, Free Tier eligibility, offer limits, remaining monthly quotas, or existing usage could be verified. AWS CLI is absent and no credential/profile/role/region environment configuration is available.
- The only verified zero-cost AWS configuration from this environment is **zero AWS resources**, with expected AWS cost **$0/month**.
- AWS public documentation says new Free Plan accounts can end after six months or when credits are exhausted, and that offer/EC2 eligibility varies by signup cohort. Public plan/service availability is not proof of this account’s $0 quota. Free credits are not counted as $0 billing. Budgets do not prevent charges. [AWS Free Tier FAQs](https://aws.amazon.com/free/free-tier-faqs/), [EC2 Free Tier usage](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html).

## SCIENCE RUNS LOCALLY

- The existing repository’s local tests and interfaces remain available. The last verified suite was 58 tests passing, compileall passed, and `pip check` passed. These checks do not establish scientific model validity or that all approved advanced models can run locally.
- Existing data/model blockers remain as described in `FINAL_DEPLOYMENT_STATUS.md`. Do not report scientific candidates as validated from interface or smoke tests.

## SCIENCE REQUIRES EXTERNAL GPU

- ET-Flow execution (subject to checkpoint rights/runtime gates), target-conditioned GP-MoLFormer training, GFM training/evaluation, GraphFDM training/reproduction, affinity training/evaluation, and large generation/RL workloads requiring GPU are **CLOUD_OUTSIDE_AWS_FREE_TIER_REQUIRED**. They are not to run on AWS Free Tier. Use only local hardware if technically feasible or an independently approved no-cost external GPU; no paid fallback is authorized.

## BLOCKED

- **BLOCKED — account eligibility verification:** account creation date and plan could not be queried. AWS credentials and CLI are not present; account eligibility and regional entitlements must not be guessed.
- **BLOCKED — exact Free Tier resource limits:** no authenticated `GetFreeTierUsage`/console data; no monthly limits, current use, forecast, or remaining headroom verified for compute, storage, data transfer, API or metadata services.
- **BLOCKED — control-plane deployment:** no service/resource is on the allowlist. Current repo’s API/SQLite queue also needs a technically validated control-plane deployment mapping before any AWS resource is considered.
- **BLOCKED_BY_ZERO_COST_POLICY:** all candidate resources whose exact $0 account allowance and all cost dimensions are unverified. No chargeable or credits-funded services may be deployed.
- **CLOUD_OUTSIDE_AWS_FREE_TIER_REQUIRED:** any heavy scientific GPU component on AWS; stop that component under this policy.

## USER ACTION REQUIRED

- Provide access to the AWS console or a narrowly scoped read-only AWS identity/CLI session so account creation date, account plan, region, service eligibility, exact offer limits, current/forecast usage and existing resources can be inspected. Do not send credentials in chat or commit them. No provisioning permission is needed for that audit.
- Until that account-specific audit passes and the allowlist is explicitly populated with expected cost exactly $0, deployment remains at zero resources. Any future resource creation requires a separate user-directed deployment step after the verified estimate and allowlist are reviewable.
