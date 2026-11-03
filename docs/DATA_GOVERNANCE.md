# Acquisition-layer research governance checklist

- Record ticker, company alias used, acquisition timestamp, source, query, window, UTC timezone, retrieval status, and record count.
- Resolve ambiguous company names manually before broad extraction. Query text is not proof that a mention refers to the intended organization.
- Preserve native timestamps and granularity before producing time-aligned features.
- Inspect failed, empty, capped, and partially collected sources individually; do not translate missing information into zeros.
- Do not derive reputational escalation labels from the same variables used as predictors within the same time window.
- Maintain a separate, explicit event validation protocol. SEC filings are corroborating disclosure evidence, not incident labels.
- For YouTube, verify current API terms, consent/approval if applicable, retention rules, and restrictions before collecting/storing identifiable comments. Default extraction omits text and author identifiers; this prevents later text sentiment analysis unless a compliant collection/processing workflow is enabled.
- Avoid publishing raw research datasets, comment text, keys, or private authentication files in GitHub. Restrict Drive access appropriately.
- Confirm Yahoo Finance data rights and use a licensed source if needed for archival reproducibility or publication.
- Document API failures/limits and time-varying coverage in Chapter 3 and in study limitations.
