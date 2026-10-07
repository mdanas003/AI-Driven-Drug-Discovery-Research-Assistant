# AWS Free Tier resource allowlist

**Audit state (2026-10-03): CLOSED / EMPTY.** No resource is authorized for creation.

## Confirmed allowlist

| AWS resource/service | Region | Account-specific Free Tier evidence | Monthly limit and remaining headroom | Authorized quantity | Expected cost |
|---|---|---|---|---:|---:|
| None | — | AWS identity/plan/creation date/region/usage could not be queried | Unknown | 0 | $0 |

## Why the list is empty

The local environment has no AWS CLI and no `AWS_ACCESS_KEY_ID`, `AWS_PROFILE`, `AWS_ROLE_ARN`, `AWS_WEB_IDENTITY_TOKEN_FILE`, `AWS_REGION`, or `AWS_DEFAULT_REGION` setting. Therefore neither account creation date nor Free Tier account plan/credit expiry, service entitlements, exact regional limits, current usage, remaining quota, or existing resources can be determined. Generic AWS public documentation is not account-specific evidence.

AWS publishes an account-level `GetFreeTierUsage` API for offer usage and a separate supported-services list for new signup plans. These sources need authenticated, account-specific inspection before an allowlist entry can be added. [GetFreeTierUsage](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_freetier_GetFreeTierUsage.html), [supported services](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html).

## Candidate resources (NOT allowed)

Serverless/static control-plane candidates such as API Gateway, Lambda, DynamoDB, S3 and CloudFront are not allowlisted. Service access does not demonstrate free monthly consumption. EC2 instances—including micro types—are not allowlisted; instance-hour, EBS, public IPv4, data transfer, AMI, region, cohort and quota terms would all need account verification. No GPU instance is allowed.

## Entry requirements

Add a resource only after recording: authenticated account identifier (securely, not in a public repo), account creation cohort/date, plan, region, exact offer name, monthly limit, actual and forecast use, remaining headroom, full resource and data-transfer estimate, service-specific pricing evidence, quantity, expected cost of $0 excluding credits, reviewer/date, and cleanup deadline. If any line item is uncertain or can exceed its no-charge allowance, leave it excluded.
