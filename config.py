"""Configuration and policy rules for the Invoice & Expense Agent."""

# Category keywords -> normalize raw vendor/description lines into categories.
CATEGORY_KEYWORDS = {
    "travel": ["airline", "flight", "uber", "lyft", "taxi", "hotel", "motel",
               "car rental", "hertz", "avis", "rail", "train", "parking"],
    "meals_entertainment": ["restaurant", "cafe", "coffee", "lunch", "dinner",
                            "breakfast", "bar", "grill", "catering", "food", "dining"],
    "software_subscriptions": ["aws", "microsoft", "adobe", "slack", "github",
                               "zoom", "saas", "software", "hosting", "cloud"],
    "office_supplies": ["stationery", "paper", "ink", "toner", "printer", "office depot",
                        "staples", "furniture", "desk", "chair"],
    "utilities": ["electric", "water", "gas", "internet", "phone", "verizon",
                  "utility", "broadband"],
    "marketing": ["google ads", "facebook", "ads", "marketing", "adwords",
                  "sponsorship", "promotion"],
    "professional_services": ["consulting", "legal", "accounting", "law", "attorney",
                              "audit", "professional", "consultant"],
    "license_fees": ["license", "permit", "registration", "renewal", "compliance"],
}

# Default category when nothing matches, plus a manual override mapping.
DEFAULT_CATEGORY = "uncategorized"

# Business hours of operation for timing checks (24h format).
BUSINESS_HOURS_START = 6
BUSINESS_HOURS_END = 22

# Deviation thresholds from the category average: flag if a single expense is
# more than `OUTLIER_MULTIPLIER` times the median for its category.
OUTLIER_MULTIPLIER = 3.0

# Maximum allowed single-expense amount before it needs manager approval.
APPROVAL_THRESHOLD = 1500.0

# Per-category, per-expense policy caps (compliance). An expense above its
# category cap is a policy breach and flagged for review.
CATEGORY_CAPS = {
    "meals_entertainment": 75.0,
    "travel": 600.0,
    "office_supplies": 1000.0,
    "utilities": 2000.0,
    "marketing": 5000.0,
    "software_subscriptions": 3000.0,
    "professional_services": 5000.0,
    "uncategorized": None,
}

# Approved vendor screening. Any expense whose vendor does not match one of
# these keywords is flagged for compliance review. Empty list disables the rule.
APPROVED_VENDORS = [
    "delta airlines", "marriott", "uber", "wework", "starbucks",
    "the capital grille", "doordash", "aws", "microsoft", "atlassian",
    "adobe", "verizon", "coned", "staples", "google ads",
    "reed & miller", "office depot", "late night pizza",
]

# Vendor concentration alert: flag when a single vendor accounts for more than
# this fraction of total spend.
VENDOR_CONCENTRATION_ALERT = 0.25

# Forecast horizon (days) for the next-period cash-flow estimate.
FORECAST_DAYS = 30

# Sentinel values passed to analyze() to disable a compliance rule.
NO_CAPS = {}
NO_VENDORS = []

# Example per-category monthly budget used when none is provided.
DEFAULT_BUDGET = {
    "software_subscriptions": 15000.0,
    "travel": 2500.0,
    "meals_entertainment": 1200.0,
    "office_supplies": 800.0,
    "utilities": 900.0,
    "marketing": 2000.0,
}

# Output report paths.
OUTPUT_CSV = "output/processed_expenses.csv"
OUTPUT_JSON = "output/agent_report.json"
OUTPUT_TXT = "output/agent_report.txt"

# Base currency and reference FX rates used to normalise multi-currency rows.
BASE_CURRENCY = "USD"
FX_RATES = {"USD": 1.0, "EUR": 1.11, "GBP": 1.31, "CAD": 0.73, "AUD": 0.66}

# Payment terms (days) by vendor keyword; matched like the approved-vendor list.
VENDOR_TERMS = {
    "aws": 7, "microsoft": 30, "delta airlines": 0, "marriott": 15,
    "uber": 7, "wework": 30, "starbucks": 0, "the capital grille": 0,
    "doordash": 0, "atlassian": 15, "adobe": 30, "verizon": 30,
    "coned": 15, "staples": 30, "google ads": 0, "reed & miller": 60,
    "office depot": 30, "late night pizza": 0, "refund desk": 0,
}
DEFAULT_TERMS_DAYS = 30

# Expense class rules: CAPEX indicators and fixed/variable sub-class mapping.
CAPEX_KEYWORDS = ["furniture", "hardware", "server", "machinery", "equipment",
                  "laptop", "vehicle", "renovation", "lease improvement",
                  "fixture", "desk", "printer"]
CAPEX_MIN_SUPPLIES_AMOUNT = 1000.0
FIXED_SUBCLASS = {"software_subscriptions", "utilities", "license_fees",
                  "professional_services", "office_supplies"}
VARIABLE_SUBCLASS = {"travel", "meals_entertainment", "marketing"}

# Category confidence below this is treated as an uncertain classification.
CONFIDENCE_THRESHOLD = 50.0

# Benford's law first-digit audit tolerance: mean absolute deviation above this
# triggers a first-digit anomaly flag.
BENFORD_MAD_THRESHOLD = 0.05

# Fraud Risk Index (0-100): rows above this are flagged high-fraud-risk.
FRAUD_RISK_THRESHOLD = 65.0

# Z-score beyond which an amount is a statistical outlier signal.
Z_SCORE_THRESHOLD = 2.5
