# Separate published-history issue — no remediation performed

The source application's existing Git history and fetched development branch contain
`legacy/streamlit_prototype/data/pdfs/Made to Stick - Chip and Dan Heath.pdf`, a 225-page,
1,131,941-byte original book PDF, plus associated book-derived JSON records under the legacy data directory.
The PDF Git blob ID is `f06d2b3beec5421a870f0ae3599b39ca87ad3747`; introduction was observed at
commit `e201803`. The identical blob was observed on upstream development ref
`7715717cb2e91e043104e9765017baa801a66344`. No source passages, PDF bytes or derived records are copied here.

This snapshot excludes the entire legacy directory and all inherited ancestry. It does not remove existing
published history elsewhere. Deleting a file in a future commit would not erase older versions.
Owner-directed rights/privacy review and any separately authorized hosting/history remediation remain
outside this task. No deletion, rewrite, force-push, backup change or existing-repository cleanup was attempted.
This document records the finding; it makes no claim of remediation or legal determination.
