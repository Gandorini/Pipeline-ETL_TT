import requests
from datetime import date, timedelta, datetime
from os import getenv
from dotenv import load_dotenv
import logging
from tqdm import tqdm
from supabase import create_client, Client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

load_dotenv()

def normalize_value(column_name, value):

    boolean_cols = ["refunded"]
    if column_name in boolean_cols:
        if value is None: return None
        boolean_map = {"sim": True, "não": False, "true": True, "false": False, "1": True, "0": False}
        return boolean_map.get(str(value).strip().lower())

    integer_cols = ["days", "guest", "underage_guest"]
    if column_name in integer_cols:
        if value is None or str(value).strip() == "": return None
        try:
            return int(float(str(value).replace(",", ".")))
        except (ValueError, TypeError):
            return None

    float_cols = ["tax_amount", "plan_amount"]
    if column_name in float_cols:
        if value is None or str(value).strip() == "": return None
        try:
            return float(str(value).replace(",", "."))
        except (ValueError, TypeError):
            return None

    datetime_cols = ["created_at"]
    if column_name in datetime_cols:
        if value is None: return None
        try:
            dt_obj = datetime.fromisoformat(value)
            if dt_obj.tzinfo is None:
                return dt_obj.isoformat() + "+00:00"
            return dt_obj.isoformat()
        except (ValueError, TypeError):
            return None

    return value

try:
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    logging.info(f"Incremental load process for date: {yesterday}")

    url = f"{getenv('API_URL')}?updated_at={yesterday}"
    headers = {"Authorization": getenv("TOKEN_KEY", "")}

    logging.info(f"Fetching data from API... Day - {yesterday}")
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json().get("data", {}).get("data", [])
    logging.info(f"Received {len(data)} records from API.")

    if not data:
        logging.info("No new records to process. Process completed.")
        exit()

    unique_records = {}
    for row in tqdm(data, desc="=> Step 1/2: Removing duplicates"):
        key = row.get("order_code")
        if key:
            unique_records[key] = row

    deduplicated_data = list(unique_records.values())
    logging.info(f"Duplicates removed. {len(deduplicated_data)} unique records remaining.")

    cols = ["order_code", "accommodation_code", "accommodation_name", "created_at",
            "name", "tax_number", "days", "guest", "underage_guest", "source",
            "paymethod", "status", "refunded", "type", "tax_amount", "plan_amount",
            "plans", "transaction_id", "payment_id", "tax_invoice", "plan_invoice"]

    normalized_records = []
    for row in tqdm(deduplicated_data, desc="=> Step 2/2: Normalising data"):
        record = {col_name: normalize_value(col_name, row.get(col_name)) for col_name in cols}
        normalized_records.append(record)

    supabase_url = getenv("SUPABASE_URL")
    supabase_key = getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be defined in .env")

    logging.info("Connecting to Supabase...")
    supabase: Client = create_client(supabase_url, supabase_key)
    logging.info("Connection successful.")

    logging.info(f"Executing UPSERT for {len(normalized_records)} records...")
    response = supabase.table('charges').upsert(
        normalized_records,
        on_conflict='order_code'
    ).execute()

    logging.info("UPSERT operation completed successfully.")

except requests.exceptions.RequestException as e:
    logging.error(f"Error communicating with API: {e}")
except Exception as e:
    logging.error(f"An unexpected error occurred: {e}", exc_info=True)

logging.info("Process complete!")