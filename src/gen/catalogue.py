"""Fixed lists used by the synthetic data generator (no randomness here).

Everything is fictional: products are generic medicine names (never brands), and
supplier, company and member names are invented word combinations.
"""

# The 8 categories, with the share of till lines each should get (sums to 1).
CATEGORIES = {
    "Analgesics": 0.18,
    "Antibiotics": 0.12,
    "Cardiovascular": 0.13,
    "Diabetes Care": 0.11,
    "Gastro": 0.13,
    "Cough and Cold": 0.12,
    "Vitamins and Supplements": 0.12,
    "Personal Care": 0.09,
}

# (generic name, strength, selling unit) per category: 150 products in total.
# S = STRIP, B = BOTTLE, P = PIECE.
PRODUCTS = {
    "Analgesics": [
        ("Paracetamol", "500 mg", "S"), ("Paracetamol", "650 mg", "S"),
        ("Paracetamol", "120 mg/5 ml", "B"), ("Paracetamol", "250 mg/5 ml", "B"),
        ("Ibuprofen", "200 mg", "S"), ("Ibuprofen", "400 mg", "S"), ("Ibuprofen", "100 mg/5 ml", "B"),
        ("Diclofenac Sodium", "50 mg", "S"), ("Diclofenac Sodium", "75 mg", "S"),
        ("Naproxen", "250 mg", "S"), ("Naproxen", "500 mg", "S"),
        ("Mefenamic Acid", "250 mg", "S"), ("Mefenamic Acid", "500 mg", "S"),
        ("Aspirin", "75 mg", "S"), ("Aspirin", "300 mg", "S"), ("Celecoxib", "200 mg", "S"),
        ("Etoricoxib", "90 mg", "S"), ("Ketorolac", "10 mg", "S"), ("Diclofenac Gel", "1%", "P"),
        ("Paracetamol Caffeine", "500/65 mg", "S"),
    ],
    "Antibiotics": [
        ("Amoxicillin", "250 mg", "S"), ("Amoxicillin", "500 mg", "S"), ("Amoxicillin", "125 mg/5 ml", "B"),
        ("Co-amoxiclav", "375 mg", "S"), ("Co-amoxiclav", "625 mg", "S"), ("Co-amoxiclav", "156 mg/5 ml", "B"),
        ("Azithromycin", "250 mg", "S"), ("Azithromycin", "500 mg", "S"), ("Azithromycin", "200 mg/5 ml", "B"),
        ("Ciprofloxacin", "250 mg", "S"), ("Ciprofloxacin", "500 mg", "S"), ("Levofloxacin", "500 mg", "S"),
        ("Cefixime", "200 mg", "S"), ("Cefixime", "100 mg/5 ml", "B"), ("Cephalexin", "500 mg", "S"),
        ("Clarithromycin", "500 mg", "S"), ("Doxycycline", "100 mg", "S"), ("Metronidazole", "400 mg", "S"),
        ("Metronidazole", "200 mg/5 ml", "B"), ("Fusidic Acid Cream", "2%", "P"),
    ],
    "Cardiovascular": [
        ("Amlodipine", "5 mg", "S"), ("Amlodipine", "10 mg", "S"), ("Losartan", "50 mg", "S"),
        ("Losartan", "100 mg", "S"), ("Atenolol", "50 mg", "S"), ("Bisoprolol", "2.5 mg", "S"),
        ("Bisoprolol", "5 mg", "S"), ("Atorvastatin", "10 mg", "S"), ("Atorvastatin", "20 mg", "S"),
        ("Atorvastatin", "40 mg", "S"), ("Rosuvastatin", "10 mg", "S"), ("Rosuvastatin", "20 mg", "S"),
        ("Clopidogrel", "75 mg", "S"), ("Valsartan", "80 mg", "S"), ("Valsartan", "160 mg", "S"),
        ("Hydrochlorothiazide", "25 mg", "S"), ("Furosemide", "40 mg", "S"), ("Spironolactone", "25 mg", "S"),
        ("Lisinopril", "10 mg", "S"), ("Isosorbide Mononitrate", "20 mg", "S"),
    ],
    "Diabetes Care": [
        ("Metformin", "500 mg", "S"), ("Metformin", "850 mg", "S"), ("Metformin", "1000 mg", "S"),
        ("Gliclazide", "80 mg", "S"), ("Gliclazide MR", "30 mg", "S"), ("Glimepiride", "1 mg", "S"),
        ("Glimepiride", "2 mg", "S"), ("Glimepiride", "4 mg", "S"), ("Sitagliptin", "50 mg", "S"),
        ("Sitagliptin", "100 mg", "S"), ("Sitagliptin Metformin", "50/500 mg", "S"),
        ("Vildagliptin", "50 mg", "S"), ("Empagliflozin", "10 mg", "S"), ("Empagliflozin", "25 mg", "S"),
        ("Dapagliflozin", "10 mg", "S"), ("Pioglitazone", "15 mg", "S"),
        ("Glucose Test Strips", "50 strips", "P"), ("Lancets", "100 pcs", "P"),
    ],
    "Gastro": [
        ("Omeprazole", "20 mg", "S"), ("Omeprazole", "40 mg", "S"), ("Esomeprazole", "20 mg", "S"),
        ("Esomeprazole", "40 mg", "S"), ("Pantoprazole", "40 mg", "S"), ("Lansoprazole", "30 mg", "S"),
        ("Famotidine", "20 mg", "S"), ("Domperidone", "10 mg", "S"), ("Domperidone", "5 mg/5 ml", "B"),
        ("Ondansetron", "4 mg", "S"), ("Ondansetron", "8 mg", "S"), ("Loperamide", "2 mg", "S"),
        ("Oral Rehydration Salts", "1 sachet", "P"), ("Antacid Suspension", "200/200 mg/5 ml", "B"),
        ("Lactulose", "3.35 g/5 ml", "B"), ("Ispaghula Husk", "3.5 g", "P"),
        ("Hyoscine Butylbromide", "10 mg", "S"), ("Metoclopramide", "10 mg", "S"),
        ("Simethicone Drops", "40 mg/ml", "B"),
    ],
    "Cough and Cold": [
        # The first product is the cough syrup that Inventory files under Gastro by mistake
        # in stage 1; stage 2 corrects it (the SCD Type 1 demo).
        ("Dextromethorphan Syrup", "15 mg/5 ml", "B"), ("Guaifenesin Syrup", "100 mg/5 ml", "B"),
        ("Ambroxol Syrup", "15 mg/5 ml", "B"), ("Ambroxol", "30 mg", "S"),
        ("Bromhexine Syrup", "4 mg/5 ml", "B"), ("Cetirizine", "10 mg", "S"), ("Levocetirizine", "5 mg", "S"),
        ("Loratadine", "10 mg", "S"), ("Fexofenadine", "120 mg", "S"), ("Fexofenadine", "180 mg", "S"),
        ("Chlorpheniramine", "4 mg", "S"), ("Pseudoephedrine Triprolidine", "60/2.5 mg", "S"),
        ("Montelukast", "10 mg", "S"), ("Montelukast", "5 mg", "S"), ("Salbutamol Syrup", "2 mg/5 ml", "B"),
        ("Salbutamol Inhaler", "100 mcg", "P"), ("Xylometazoline Nasal Drops", "0.1%", "B"),
        ("Throat Lozenges", "24 pcs", "P"),
    ],
    "Vitamins and Supplements": [
        ("Vitamin C", "500 mg", "S"), ("Vitamin D3", "50000 IU", "S"), ("Calcium Vitamin D3", "600 mg/400 IU", "S"),
        ("Multivitamin Tablets", "30 tabs", "B"), ("Multivitamin Syrup", "120 ml", "B"),
        ("Folic Acid", "5 mg", "S"), ("Ferrous Sulphate", "200 mg", "S"), ("Iron Folic Acid", "150/0.5 mg", "S"),
        ("Zinc Sulphate", "20 mg", "S"), ("Zinc Syrup", "20 mg/5 ml", "B"), ("Vitamin B Complex", "1 tab", "S"),
        ("Methylcobalamin", "500 mcg", "S"), ("Omega-3", "1000 mg", "B"), ("Vitamin E", "400 IU", "S"),
        ("Magnesium", "250 mg", "S"), ("Biotin", "5 mg", "B"), ("Cod Liver Oil Capsules", "60 caps", "B"),
        ("Vitamin A D Drops", "15 ml", "B"), ("Calcium Syrup", "120 ml", "B"),
    ],
    "Personal Care": [
        ("Antiseptic Liquid", "500 ml", "B"), ("Hand Sanitizer", "250 ml", "B"), ("Sunscreen", "SPF 50", "P"),
        ("Moisturising Cream", "100 g", "P"), ("Baby Diapers", "Size 3", "P"), ("Baby Wipes", "80 pcs", "P"),
        ("Toothpaste Sensitive", "100 g", "P"), ("Mouthwash", "250 ml", "B"), ("Medicated Shampoo", "200 ml", "B"),
        ("Cotton Bandage", "10 cm", "P"), ("Adhesive Plasters", "20 pcs", "P"), ("Digital Thermometer", "1 pc", "P"),
        ("Face Masks", "50 pcs", "P"), ("Petroleum Jelly", "100 g", "P"), ("Hair Oil", "200 ml", "B"),
        ("Surgical Gloves", "100 pcs", "P"),
    ],
}

UNIT_NAMES = {"S": "STRIP", "B": "BOTTLE", "P": "PIECE"}
UNIT_SUFFIX = {"S": "STR", "B": "BTL", "P": "PCS"}

# Shelf price range per selling unit in PKR, by (category, unit); default by unit.
PRICE_RANGE = {
    ("Analgesics", "S"): (25, 120), ("Antibiotics", "S"): (120, 520), ("Cardiovascular", "S"): (80, 420),
    ("Diabetes Care", "S"): (90, 650), ("Gastro", "S"): (60, 320), ("Cough and Cold", "S"): (40, 260),
    ("Vitamins and Supplements", "S"): (80, 500), ("Vitamins and Supplements", "B"): (300, 1500),
    ("Diabetes Care", "P"): (900, 2400), ("Personal Care", "B"): (180, 900), ("Personal Care", "P"): (120, 1200),
}
DEFAULT_PRICE_RANGE = {"S": (40, 300), "B": (120, 450), "P": (80, 600)}

# Seasonal multipliers on how often a category is bought, by calendar month.
SEASONS = {
    "Cough and Cold": {12: 1.8, 1: 1.9, 2: 1.6, 11: 1.2, 3: 1.1},     # flu season Dec-Feb
    "Analgesics": {8: 1.45, 9: 1.55, 10: 1.4, 7: 1.1},                  # dengue / monsoon Aug-Oct
    "Gastro": {8: 1.4, 9: 1.45, 10: 1.3, 7: 1.15},                      # monsoon Aug-Oct
}
# Vitamins rise in the month before Ramadan starts and in the month it starts (by year, month).
PRE_RAMADAN_MONTHS = {(2024, 2): 1.5, (2024, 3): 1.25, (2025, 2): 1.6, (2025, 1): 1.2,
                      (2026, 1): 1.5, (2026, 2): 1.3}

# Ten branches: store_code, store_name, area, region, Purchasing branch_id, Purchasing label,
# receipt prefix, sales weight, and the 2-3 ways cashiers type the branch name at the till.
BRANCHES = [
    ("BR-NNZ", "Nuskha North Nazimabad", "Central", "North", 3, "North Nazimabad Br.", "NNZ", 1.1,
     ["North Nazimabad", "N. Nazimabad", "NORTH NAZIMABAD "]),
    ("BR-GBG", "Nuskha Gulberg", "Central", "North", 7, "Gulberg Br.", "GBG", 0.9,
     ["Gulberg", "GULBERG", "Gulberg Town"]),
    ("BR-NZM", "Nuskha Nazimabad", "Central", "North", 1, "Nazimabad Br.", "NZM", 0.8,
     ["Nazimabad", "nazimabad "]),
    ("BR-ORG", "Nuskha Orangi", "West", "North", 9, "Orangi Town Br.", "ORG", 0.7,
     ["Orangi", "Orangi Town", "ORANGI"]),
    ("BR-GUL", "Nuskha Gulshan-e-Iqbal", "Gulshan", "East", 4, "Gulshan-e-Iqbal Br.", "GUL", 1.3,
     ["Gulshan-e-Iqbal", "Gulshan", "GULSHAN-E-IQBAL "]),
    ("BR-GLJ", "Nuskha Gulistan-e-Jauhar", "Gulshan", "East", 6, "Gulistan-e-Jauhar Br.", "GLJ", 1.0,
     ["Gulistan-e-Jauhar", "Jauhar", "GULISTAN E JOHAR"]),
    ("BR-MLR", "Nuskha Malir", "Malir", "East", 10, "Malir Br.", "MLR", 0.8,
     ["Malir", "MALIR CANTT"]),
    ("BR-CLF", "Nuskha Clifton", "South", "South", 2, "Clifton Br.", "CLF", 1.2,
     ["Clifton", "CLIFTON", "Clifton Blk 5"]),
    ("BR-SDR", "Nuskha Saddar", "South", "South", 5, "Saddar Br.", "SDR", 1.0,
     ["Saddar", "Sadar", "SADDAR "]),
    ("BR-PEC", "Nuskha PECHS", "Jamshed", "South", 8, "PECHS Br.", "PEC", 1.0,
     ["PECHS", "P.E.C.H.S", "Pechs"]),
]

# Invented words for fictional supplier and company names.
SUPPLIER_WORDS = ["Alder", "Basalt", "Cobalt", "Dunewood", "Emberly", "Falconridge", "Garnet", "Harbourline",
                  "Indigo", "Juniper", "Kitewing", "Lumen", "Maplegate", "Nimbus", "Onyxfield", "Pebblestone",
                  "Quartzline", "Ridgeway", "Saffronia", "Tealbrook", "Umberly", "Vistara", "Willowmere",
                  "Zephyra", "Amberlane"]
SUPPLIER_SUFFIX = ["Medical Distributors", "Pharma Supply", "Health Traders", "Drug House", "Medicare Agencies"]
IMPORT_COUNTRIES = ["China", "Germany", "Switzerland", "Turkey", "Malaysia"]

COMPANY_WORDS = ["Bluewater", "Copperleaf", "Driftwood", "Evergreen", "Fernhill", "Goldcrest", "Highmoor",
                 "Ironbark", "Jadestone", "Kingsfoil", "Larkspur", "Moonridge", "Northwind", "Oakhollow",
                 "Pinecrest"]
COMPANY_TRADES = ["Textiles Ltd", "Logistics (Pvt) Ltd", "Foods Ltd", "Engineering Ltd", "Packaging Ltd",
                  "Garments (Pvt) Ltd", "Steel Works Ltd", "Software (Pvt) Ltd", "Ceramics Ltd",
                  "Shipping (Pvt) Ltd", "Paper Mills Ltd", "Polymers Ltd", "Builders (Pvt) Ltd",
                  "Agro Industries Ltd", "Leather Works Ltd"]

# Invented member names (random first + last combinations, not real people).
FIRST_NAMES = ["Ayesha", "Bilal", "Danish", "Farah", "Hamza", "Hina", "Imran", "Javeria", "Kashif", "Laiba",
               "Mahnoor", "Nadia", "Omer", "Rabia", "Saad", "Sana", "Taha", "Uzma", "Waqas", "Zainab",
               "Arsalan", "Bushra", "Fahad", "Mehwish", "Rizwan", "Sadia", "Usman", "Yusra"]
LAST_NAMES = ["Ahmed", "Ali", "Baig", "Chaudhry", "Farooqui", "Hashmi", "Iqbal", "Jafri", "Khan", "Malik",
              "Mirza", "Qureshi", "Rizvi", "Saeed", "Shaikh", "Siddiqui", "Usmani", "Zaidi"]

# Approximate Ramadan dates in the history window (used for seasons and dim_date.is_ramadan).
RAMADAN = [("2024-03-12", "2024-04-10"), ("2025-03-02", "2025-03-30"), ("2026-02-19", "2026-03-20")]
