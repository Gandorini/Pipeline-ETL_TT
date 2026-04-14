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
    logging.info(f"Processo de carga incremental para a data: {yesterday}")

    url = f"{getenv('API_URL')}?updated_at={yesterday}"
    headers = {"Authorization": getenv("TOKEN_KEY", "")}

    logging.info(f"A buscar dados da API... Dia - {yesterday}")
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json().get("data", {}).get("data", [])
    logging.info(f"Recebidos {len(data)} registos da API.")

    if not data:
        logging.info("Nenhum registo novo para processar. O processo foi concluído.")
        exit()

    unique_records = {}
    for row in tqdm(data, desc="=> Passo 1/2: A remover duplicados"):
        key = row.get("order_code")
        if key:
            unique_records[key] = row
    
    deduplicated_data = list(unique_records.values())
    logging.info(f"Removidos duplicados. Restam {len(deduplicated_data)} registos únicos.")

    cols = ["order_code", "accommodation_code", "accommodation_name", "created_at",
            "name", "tax_number", "days", "guest", "underage_guest", "source",
            "paymethod", "status", "refunded", "type", "tax_amount", "plan_amount",
            "plans", "transaction_id", "payment_id", "tax_invoice", "plan_invoice"]
    
    normalized_records = []
    for row in tqdm(deduplicated_data, desc="=> Passo 2/2: A normalizar dados"):
        record = {col_name: normalize_value(col_name, row.get(col_name)) for col_name in cols}
        normalized_records.append(record)

    # 3. Conexão e Inserção no Supabase
    supabase_url = getenv("SUPABASE_URL")
    supabase_key = getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL e SUPABASE_KEY devem estar definidos no .env")

    logging.info("A conectar-se ao Supabase...")
    supabase: Client = create_client(supabase_url, supabase_key)
    logging.info("Conexão bem-sucedida.")

    logging.info(f"A executar a operação de UPSERT para {len(normalized_records)} registos...")
    response = supabase.table('charges').upsert(
        normalized_records, 
        on_conflict='order_code'
    ).execute()
    
    logging.info("Operação de UPSERT concluída com sucesso.")

except requests.exceptions.RequestException as e:
    logging.error(f"Erro ao comunicar com a API: {e}")
except Exception as e:
    logging.error(f"Ocorreu um erro inesperado: {e}", exc_info=True)

logging.info("Processo concluído!")
