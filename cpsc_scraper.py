import os
import time
import csv
import json
import re
from datetime import datetime
import schedule
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import iris
import pandas as pd

# === IRIS CONNECTION CLASS ===
class IRIS_connection:
    def __init__(self, host="127.0.0.1", port=1972, namespace="USER", username="_SYSTEM", password="SYS"):
        args = {'hostname': host, 'port': port, 'namespace': namespace, 'username': username, 'password': password}
        self.conn = iris.connect(**args)

    def query(self, sql: str, parameters: list = []) -> pd.DataFrame:
        cursor = self.conn.cursor()
        cursor.execute(sql, parameters)
        rows = cursor.fetchall()
        if not rows:
            return pd.DataFrame()
        columns = [col[0] for col in cursor.description]
        df = pd.DataFrame(rows, columns=columns)
        cursor.close()
        return df

    def table_exists(self, table_name: str) -> bool:
        q = "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME=?"
        df = self.query(q, [table_name.upper()])
        return not df.empty and int(df.iloc[0, 0]) > 0

    def create_table(self, table_name: str, columns: dict):
        if self.table_exists(table_name):
            return
        cursor = self.conn.cursor()
        cols = ", ".join([f"{k} {v}" for k, v in columns.items()])
        sql = f"CREATE TABLE {table_name} ({cols})"
        cursor.execute(sql)
        self.conn.commit()
        cursor.close()
        print(f"[OK] Table {table_name} created.")

    def insert(self, table_name: str, data: dict) -> None:
        cursor = self.conn.cursor()
        columns = ', '.join([col.upper() for col in data.keys()])
        placeholders = ', '.join(['?'] * len(data))
        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        try:
            cursor.execute(sql, tuple(data.values()))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"Failed to insert into {table_name}: {e}")
            raise
        finally:
            cursor.close()

# === CONFIG ===
BASE_URL = "https://www.cpsc.gov/Recalls"
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

RECALLS_CSV = os.path.join(DOWNLOAD_DIR, "recalls_recall_listing.csv")
WARNINGS_CSV = os.path.join(DOWNLOAD_DIR, "product_safety_warning_listing.csv")
OUTPUT_JSON = "./processed_cpsc_data.json"

KNOWN_BRANDS = {
    "amazon", "walmart", "target", "best buy", "home depot", "lowe", "costco",
    "ebay", "apple", "samsung", "ikea", "aldi", "sears", "wayfair", "macys",
    "nordstrom", "kohls", "toys r us", "staples", "officedepot", "apolloscooters"
}

# === UTILS ===
def to_horolog(date_str):
    if not date_str or not date_str.strip():
        return None
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        base = datetime(1840, 12, 31)
        return (dt - base).days
    except Exception:
        return None

def parse_remedy(remedy_str):
    if not remedy_str:
        return []
    return [r.strip().upper() for r in remedy_str.split(",") if r.strip()]

def extract_units(units_str):
    if not units_str:
        return None
    match = re.search(r"([\d,]+)", units_str)
    if match:
        try:
            return int(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None

def split_list_field(value):
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]

def clean_company_list(values):
    if not values:
        return []
    text = " ".join(values)
    text = re.sub(r"\b(of|from)\s+[A-Z][a-z]+", "", text)
    text = re.sub(r"doing business as|dba|seller|trading as|also known as", "", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text).strip()
    matches = re.findall(r"\b[A-Z][A-Za-z0-9&\-\s]{2,}\b", text)
    cleaned = [m.strip() for m in matches if len(m.strip()) > 2]
    found_known = []
    for brand in KNOWN_BRANDS:
        if re.search(rf"\b{brand}\b", text, re.I):
            found_known.append(brand.title())
    ignore = {"China", "Ltd", "Inc", "LLC", "Corp", "Company", "Corporation", "Co", "USA"}
    unique = []
    for c in cleaned:
        if c not in ignore and not any(c in u or u in c for u in unique):
            unique.append(c)
    return sorted(set(found_known) if found_known else unique)

def normalize_sold_at(text):
    if not isinstance(text, str) or not text.strip():
        return []
    text_lower = text.lower()
    sites = re.findall(r"[A-Za-z0-9\.\-]+\.(?:com|org|co|net|gov)", text)
    brands = [b.title() for b in KNOWN_BRANDS if b in text_lower]
    stores = re.findall(r"\b[A-Z][A-Za-z&\s]{2,}(?=\s+(?:stores|online|nationwide|and))", text)
    all_items = list(set(sites + stores + brands))
    return sorted([s.strip() for s in all_items if s.strip()])

# === CSV PROCESSING ===
def process_csv(path, source_type):
    data = []
    with open(path, newline='', encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            base = {
                "name_of_product": row.get("Name of product"),
                "description": row.get("Description"),
                "hazard_description": row.get("Hazard Description"),
                "consumer_action": row.get("Consumer Action"),
                "units": extract_units(row.get("Units")),
                "incidents": row.get("Incidents"),
                "sold_at": normalize_sold_at(row.get("Sold At")),
                "importers": clean_company_list(split_list_field(row.get("Importers"))),
                "manufacturers": clean_company_list(split_list_field(row.get("Manufacturers"))),
                "distributors": clean_company_list(split_list_field(row.get("Distributors"))),
                "manufactured_in": split_list_field(row.get("Manufactured In")),
            }
            if source_type == "recall":
                base.update({
                    "source": "recall",
                    "recall_number": row.get("Recall Number"),
                    "recall_date": to_horolog(row.get("Date")),
                    "recall_heading": row.get("Recall Heading"),
                    "remedy_type": parse_remedy(row.get("Remedy Type")),
                    "remedy": row.get("Remedy"),
                })
            else:
                base.update({
                    "source": "warning",
                    "product_safety_warning_number": row.get("Product Safety Warning Number"),
                    "recall_date": to_horolog(row.get("Product Safety Warning Date")),
                    "recall_heading": row.get("Product Safety Warning Title"),
                })
            data.append(base)
    return data

# === SELENIUM CSV DOWNLOAD ===
def download_cpsc_csvs():
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(BASE_URL)
        wait = WebDriverWait(driver, 20)
        try:
            close_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="sitewidePopup"]/div/div/div[3]/button')))
            close_btn.click()
            print("[OK] Popup closed.")
            time.sleep(2)
        except Exception:
            pass
        export_tab = wait.until(EC.element_to_be_clickable((By.XPATH, '//label[@for="tab2"]')))
        export_tab.click()
        print("[OK] 'Export CSV' tab opened.")
        time.sleep(2)
        recalls_csv = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="recalls_csv"]/div/div/div[2]/a[2]')))
        recalls_csv.click()
        print("[OK] Downloading: Recalls CSV...")
        time.sleep(5)
        warnings_csv = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="recalls_csv"]/div/div/div[2]/a[3]')))
        warnings_csv.click()
        print("[OK] Downloading: Product Safety Warnings CSV...")
        time.sleep(5)
    finally:
        driver.quit()

# === AUXILIARY TABLE UPSERT ===
def upsert_aux_table(conn, table_name, key, values):
    cursor = conn.conn.cursor()
    cursor.execute(f"DELETE FROM {table_name} WHERE recall_number = ?", (key,))
    conn.conn.commit()
    cursor.close()
    for v in values:
        conn.insert(table_name, {"recall_number": key, "value": v})

# === MAIN TASK ===
def run_task():
    download_cpsc_csvs()
    recalls = process_csv(RECALLS_CSV, "recall")
    warnings = process_csv(WARNINGS_CSV, "warning")
    all_data = recalls + warnings

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print("[OK] Processing finished. JSON saved.")

    conn = IRIS_connection()

    # === CREATE MAIN TABLE ===
    conn.create_table("cpsc_data", {
        "id": "SERIAL PRIMARY KEY",
        "source": "VARCHAR(20)",
        "recall_number": "VARCHAR(50)",
        "product_safety_warning_number": "VARCHAR(50)",
        "name_of_product": "VARCHAR(8000)",
        "description": "LONGVARCHAR(8000)",
        "hazard_description": "VARCHAR(8000)",
        "consumer_action": "VARCHAR(8000)",
        "units": "INTEGER",
        "incidents": "VARCHAR(8000)",
        "recall_date": "DATE",
        "recall_heading": "VARCHAR(8000)",
        "remedy": "VARCHAR(8000)"
    })

    # === CREATE AUXILIARY TABLES ===
    aux_tables = {
        "cpsc_sold_at": "VARCHAR(255)",
        "cpsc_importers": "VARCHAR(255)",
        "cpsc_manufacturers": "VARCHAR(255)",
        "cpsc_distributors": "VARCHAR(255)",
        "cpsc_manufactured_in": "VARCHAR(255)",
        "cpsc_remedy_type": "VARCHAR(255)"
    }
    for tname, col_type in aux_tables.items():
        conn.create_table(tname, {
            "id": "SERIAL PRIMARY KEY",
            "recall_number": "VARCHAR(50)",
            "value": col_type
        })

    # === INSERT OR UPDATE MAIN + AUX ===
    for record in all_data:
        flat_data = {k: v for k, v in record.items() if not isinstance(v, list)}
        key = flat_data.get("recall_number") or flat_data.get("product_safety_warning_number")

        if not key:
            continue

        # Check if record exists
        existing = conn.query("SELECT id FROM cpsc_data WHERE recall_number=?", [key])
        try:
            if not existing.empty:
                set_sql = ", ".join([f"{k.upper()}=?" for k in flat_data.keys()])
                update_sql = f"UPDATE cpsc_data SET {set_sql} WHERE recall_number=?"
                cursor = conn.conn.cursor()
                cursor.execute(update_sql, tuple(flat_data.values()) + (key,))
                conn.conn.commit()
                cursor.close()
            else:
                conn.insert("cpsc_data", flat_data)
        except Exception as e:
            print(f"Error inserting/updating record: {e}")

        # Insert into auxiliary tables
        for list_field, table_name in [
            ("sold_at", "cpsc_sold_at"),
            ("importers", "cpsc_importers"),
            ("manufacturers", "cpsc_manufacturers"),
            ("distributors", "cpsc_distributors"),
            ("manufactured_in", "cpsc_manufactured_in"),
            ("remedy_type", "cpsc_remedy_type"),
        ]:
            upsert_aux_table(conn, table_name, key, record.get(list_field, []))

    # delete CSVs
    for f in [RECALLS_CSV, WARNINGS_CSV]:
        if os.path.exists(f):
            os.remove(f)
    print("[OK] CSV files deleted.")

# === EXECUTE IMMEDIATELY ===
run_task()

# === SCHEDULE DAILY AT 22:00 ===
schedule.every().day.at("22:00").do(run_task)
print("Scheduler started. Script will run daily at 22:00.")

while True:
    schedule.run_pending()
    time.sleep(60)
