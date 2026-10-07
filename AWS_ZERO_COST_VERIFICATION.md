# AWS zero-cost verification record

**Audit date:** 2026-10-03  
**Method:** local environment inspection plus current official AWS documentation review. No AWS resources were created.

## Read-only checks attempted

- `aws --version`: command not installed.
- `aws sts get-caller-identity`: could not run because AWS CLI is unavailable.
- `aws account get-account-information`: could not run because AWS CLI is unavailable.
- `aws freetier get-free-tier-usage --region us-east-1`: could not run because AWS CLI is unavailable.
- Environment presence checks found no `AWS_ACCESS_KEY_ID`, `AWS_PROFILE`, `AWS_ROLE_ARN`, `AWS_WEB_IDENTITY_TOKEN_FILE`, `AWS_REGION`, or `AWS_DEFAULT_REGION`.

No credential contents were requested or displayed. Account ID, account creation date/cohort, plan, eligibility, credits and expiry, account region, service limits, actual/forecast usage, eligible EC2 types and AMIs, storage/networking eligibility, existing resources, and possible bills are all **UNVERIFIED**.

## Official information reviewed

- AWS states the current Free Plan expires at the earlier of six months or exhaustion of Free Tier credits; prior-account history can affect eligibility. [AWS Free Tier FAQs](https://aws.amazon.com/free/free-tier-faqs/)
- EC2 eligibility and offers differ by account creation cohort; AWS provides account-specific EC2/Free Tier checks. Generic instance eligibility is not sufficient. [EC2 Free Tier usage](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html)
- AWS has an account-level API for reading Free Tier usage/limits. It requires an authenticated request. [GetFreeTierUsage](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_freetier_GetFreeTierUsage.html), [Free Tier API guide](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-free-tier-api.html)
- A service appearing as accessible under a signup plan does not verify this account’s exact monthly $0 offer or current remaining capacity. [Supported services for new AWS signup](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html)

## Result

| Check | Result |
|---|---|
| Identity and creation date | Unknown — authentication unavailable |
| Account plan and eligibility | Unknown |
| Region | Unknown |
| Monthly usage / offer limits / remaining quota | Unknown |
| Existing AWS resources | Unknown |
| Per-resource expected bill | Cannot calculate without account/region/usage facts |
| Resources authorized | None |
| Deployment | Not started |
| Expected AWS cost under actions taken | **$0** (zero resources created) |

## Stop condition

Do not deploy until an authenticated read-only audit has captured the items above for the selected region and every resource dimension; the exact proposed monthly usage must fit a verified $0 allowance without applying promotional credits. Budgets are monitoring, not a billing cap. If verification fails, retain an empty resource allowlist.
