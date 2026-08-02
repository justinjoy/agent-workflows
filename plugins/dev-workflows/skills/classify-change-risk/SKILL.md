---
name: classify-change-risk
description: Atomic implementation skill that classifies request risk, scope, validation needs, and whether planning/review gates are required.
---

# Classify Change Risk

Classify the request using the inspected repository context.

Output a `risk_classification` artifact naming:

- trivial vs. non-trivial change
- single-file vs. multi-file scope
- shared behavior, persistence, network, or public API impact
- focused and broad validation needs
- whether planning, critique, review, and final validation gates are required
