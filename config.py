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

# Output report paths.
OUTPUT_CSV = "output/processed_expenses.csv"
OUTPUT_JSON = "output/agent_report.json"
OUTPUT_TXT = "output/agent_report.txt"
