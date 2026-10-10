# Dynamic & Conditionally Rendered Templates Allowlist

**Generated On:** 2026-10-09  
**Purpose:** Whitelist templates that are rendered conditionally, via dynamic string construction, or loaded as viewer fallbacks, preventing false-positive deletion during Phase 3 template cleanup.

---

## 1. Dynamic / Conditional Template Mapping

| Template File | Calling Route / Function | Render Pattern / Context | Retention Status |
| :--- | :--- | :--- | :--- |
| `resource.html` | `/resource/<slug>`, `/pyq/<college>/<subject>` | Primary resource view; selected when `v2_ui=False` or legacy view parameter is active. | **Retain (Core)** |
| `resource_v2.html` | `/resource/<slug>`, `/v2/resource/<slug>` | Next-generation modern resource interface; rendered dynamically when feature flag is active. | **Retain (Primary V2)** |
| `app/pdf_reader.html` | `/embed/pdf/<file_id>`, `/view/pdf/<file_id>` | Embedded standalone PDF viewer mode. | **Allowlisted (Viewer Mode)** |
| `peer_profile.html` | `/profile/<user_id>`, `/peer/<user_id>` | Public peer visitor profile page view. | **Allowlisted (Public Profile)** |
| `preview.html` | `/preview/<doc_id>` | Dynamic document quick preview modal / iFrame wrapper. | **Allowlisted (Preview)** |
| `payment.html` | `/payment/checkout`, `/buy-tea` | Monetization / PhonePe checkout overlay. | **Allowlisted (Monetization)** |
| `payment_receipt.html`| `/payment/receipt/<tx_id>` | Post-checkout dynamic invoice & receipt view. | **Allowlisted (Invoicing)** |

---

## 2. Dynamic Template Rules for Refactoring
1. **Never delete** any template listed in this allowlist during unreferenced file scans.
2. When merging `resource.html` and `resource_v2.html`, ensure all parameters are backwards-compatible before removing either file.
