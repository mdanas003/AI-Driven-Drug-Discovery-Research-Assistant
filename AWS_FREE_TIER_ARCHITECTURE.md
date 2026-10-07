# AWS Free Tier only: feasibility architecture

**Audit date:** 2026-10-03  
**Deployment decision:** read-only feasibility audit only. No AWS account identity, creation date, plan state, region, current Free Tier usage, or account-specific service/instance allowance could be queried. AWS CLI is not installed and no AWS credential/profile/role/region environment configuration is present. Therefore **no AWS resource is authorized or confirmed eligible** and nothing was provisioned.

## Target boundary

The requested AWS control plane is lightweight API/job orchestration, minimal metadata/artifact storage, and health/status. Scientific computation stays outside AWS Free Tier: ET-Flow, GraphFDM, GFM training, affinity training, large molecular generation, and RL are **CLOUD_OUTSIDE_AWS_FREE_TIER_REQUIRED** if a GPU is needed. Under this zero-cost policy, those workloads must instead run locally when scientifically and technically feasible, or on a separately approved no-cost external GPU. Do not start a paid AWS or cloud GPU fallback.

The scientific architecture and interfaces remain intact. Disabling a GPU worker does not substitute CPU baselines for advanced methods and must never yield scientific results for a blocked stage.

## Candidate topology (not yet authorized)

If and only if the authenticated account console/API later confirms exact eligibility, limits, region, and expected incremental cost of **$0**, a control-plane-only candidate could use a small static frontend and lightweight API/job metadata service, with minimal storage. Candidate services might include S3/CloudFront for static assets, API Gateway/Lambda for API execution, and DynamoDB for job metadata. Being listed as available to a Free account does not prove that an offer has a $0 allowance or fits this account’s remaining monthly quota. No EC2 instance is selected. No public IPv4, load balancer, NAT Gateway, database, model API, GPU worker, auto-scaling, or paid fallback is permitted.

The current repository API and SQLite queue are single-host/container oriented; they do not directly constitute a serverless control plane. Any adaptation must preserve the existing API/job/artifact interfaces and scientifically transparent job states. Do not provision before that adaptation and account-specific gates pass.

## Cost estimate and deployment gate

| Item | Proposed quantity | Verified monthly allowance | Expected bill under verified account facts |
|---|---:|---:|---:|
| AWS resources today | 0 | Not queried | **$0** |
| Future API/compute/storage resources | 0 authorized | Not queried | **Not estimable; BLOCKED** |

Zero resources is the only configuration with a supportable expected AWS bill of **$0** based on the evidence available here. Free Tier credits are not treated as a $0 bill; promotional credits can offset otherwise chargeable use and do not satisfy this policy. Budgets and alerts are monitoring, not hard billing caps.

The current AWS documentation describes new Free Plan accounts as lasting up to six months or until credits are exhausted; historical accounts can have different EC2 offer rules. AWS’s EC2 documentation explicitly distinguishes accounts created before and after 2025-07-15 and directs operators to query the account-specific Free Tier offer. Account age and eligibility cannot be inferred from a machine or region. [AWS Free Tier FAQs](https://aws.amazon.com/free/free-tier-faqs/), [EC2 Free Tier usage](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html).

The new signup experience’s supported-service list says which services a plan can access, not that each service’s usage will bill $0; service inclusion is not a per-account offer/limit guarantee. [Supported services for new AWS signup](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html). Current and forecast usage must be read from the authenticated Free Tier API/console. [GetFreeTierUsage API](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_freetier_GetFreeTierUsage.html), [Free Tier API guide](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-free-tier-api.html).

## Execution split

- **AWS FREE-TIER READY:** none yet; account eligibility and exact quotas are unverified.
- **SCIENCE RUNS LOCALLY:** existing interfaces and tests run locally; this label does not claim that all advanced scientific models run on the local RTX 3050.
- **SCIENCE REQUIRES EXTERNAL GPU:** heavy model training/inference outside AWS Free Tier, with no paid fallback authorized.
- **BLOCKED:** account-specific Free Tier confirmation; cloud adaptation/eligibility; data/model scientific gates.
- **USER ACTION REQUIRED:** authenticate the AWS account and provide the selected region/account-plan evidence for read-only verification. Do not provide credentials in this repository or chat.
