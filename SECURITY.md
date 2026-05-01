# Security Policy
   
## Reporting a Vulnerability
Please contact me directly or create a private security advisory on GitHub.

## Security Framework Alignment

This project includes security controls mapped to the OWASP Top 10 web application security risks.

This mapping is a project self-assessment. It is not a third-party audit, certification, or guarantee of compliance. 
Security also depends on how the package is configured and used by the consuming Django application, including 
Django settings, AWS IAM permissions, API Gateway configuration, TLS, cookie settings, logging, monitoring, and 
application-specific authorization checks.

The current OWASP Top 10 release is OWASP Top 10:2025. The previous project mapping was based on OWASP Top 10:2021.

## OWASP Top 10:2025 Mapping

| Category | Status | Project controls and notes |
| --- | --- | --- |
| A01:2025 - Broken Access Control | Partially mitigated | The package supports WebSocket token protection, API Gateway validation, handler whitelisting, Django permission checks, origin/host checks, and connection/session validation. Applications must still implement object-level authorization in their handlers. |
| A02:2025 - Security Misconfiguration | Partially mitigated | The package provides secure defaults and production guidance. Correct Django settings, AWS configuration, allowed hosts, trusted origins, cookies, TLS, and environment separation remain deployment responsibilities. |
| A03:2025 - Software Supply Chain Failures | Partially mitigated | Dependency management and vulnerability scanning should be performed by maintainers and deployers. Additional controls such as pinned hashes, SBOM generation, signed releases, and provenance would strengthen this area. |
| A04:2025 - Cryptographic Failures | Shared responsibility | The package relies on Django, AWS, HTTPS/WSS, secure cookies, session handling, and generated WebSocket tokens. Deployments must configure TLS, secrets, cookies, and session security correctly. |
| A05:2025 - Injection | Partially mitigated | The package uses Django ORM patterns and validates selected inputs such as connection IDs and channel names. Application handlers must validate message payloads and avoid unsafe use of client-controlled input. |
| A06:2025 - Insecure Design | Partially mitigated | The design uses defence-in-depth controls including short-lived single-use tokens, rate limiting, validation, handler restrictions, and permission hooks. Applications should still perform threat modelling for their own WebSocket workflows. |
| A07:2025 - Authentication Failures | Partially mitigated | Authenticated WebSocket connections can be protected with short-lived, single-use, session-bound tokens. Correct Django authentication, session, CSRF, and cookie configuration is required. |
| A08:2025 - Software or Data Integrity Failures | Partially mitigated | Single-use tokens and validation help protect connection integrity. Broader software integrity controls such as release signing, CI/CD hardening, dependency provenance, and package verification are recommended. |
| A09:2025 - Security Logging and Alerting Failures | Partially mitigated | The package documents security-relevant events that should be logged and monitored. Production deployments should configure centralised logging, alerting, retention, and incident response processes. |
| A10:2025 - Mishandling of Exceptional Conditions | Partially mitigated | The package uses validation and generic error responses in security-sensitive paths. Applications should handle exceptions consistently, fail closed where appropriate, and avoid exposing implementation details to clients. |

## OWASP Top 10:2021 Mapping

The project was previously mapped to OWASP Top 10:2021. That mapping remains useful for historical comparison, but OWASP Top 10:2025 should be treated as the current reference.

| Category | Status |
| --- | --- |
| A01:2021 - Broken Access Control | Partially mitigated |
| A02:2021 - Cryptographic Failures | Shared responsibility |
| A03:2021 - Injection | Partially mitigated |
| A04:2021 - Insecure Design | Partially mitigated |
| A05:2021 - Security Misconfiguration | Partially mitigated |
| A06:2021 - Vulnerable and Outdated Components | Partially mitigated / shared responsibility |
| A07:2021 - Identification and Authentication Failures | Partially mitigated |
| A08:2021 - Software and Data Integrity Failures | Partially mitigated |
| A09:2021 - Security Logging and Monitoring Failures | Partially mitigated |
| A10:2021 - Server-Side Request Forgery | Mostly not applicable to the package core, but application handlers must avoid unsafe outbound request behaviour. |

## Security Notes for Users

For production deployments:

- enable WebSocket token protection for authenticated connections;
- validate application message payloads in handlers;
- perform object-level authorization checks in handlers;
- configure Django `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, sessions, cookies, and secret settings securely;
- restrict AWS IAM permissions to the minimum required;
- use HTTPS/WSS in production;
- monitor rejected connections, token validation failures, rate limit failures, unexpected headers, invalid channels, and failed message sends;
- keep Django, Python, boto3, and deployment dependencies up to date;
- consider dependency scanning, SBOM generation, signed releases, and provenance checks for stronger supply-chain assurance.
