# bff_api.py
from fastapi import FastAPI, Query, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import iris
import datetime
from collections import Counter

def parse_date(val):
    """Converte valores de data em datetime.datetime"""
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        return val
    if isinstance(val, datetime.date):
        return datetime.datetime(val.year, val.month, val.day)
    if isinstance(val, (int, float)):
        return datetime.datetime.fromtimestamp(val)
    if isinstance(val, str):
        # tenta vários formatos comuns
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
            try:
                return datetime.datetime.strptime(val, fmt)
            except:
                continue
        # se não der certo, retorna None
        return None
    return None

# === IRIS CONNECTION ===
class IRISConnection:
    def __init__(self, host="127.0.0.1", port=1972, namespace="USER", username="_SYSTEM", password="SYS"):
        self.conn = iris.connect(hostname=host, port=port, namespace=namespace, username=username, password=password)

    def query(self, sql: str, params: list = []):
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description] if rows else []
        cursor.close()
        return [dict(zip(columns, row)) for row in rows] if rows else []

# === MODELS ===
class RecallOut(BaseModel):
    recall_number: str
    name_of_product: str = None
    recall_date: Optional[datetime.datetime] = None
    source: str = None
    manufacturers: List[str] = []
    sold_at: List[str] = []
    country: List[str] = []
    remedy_type: List[str] = []
    hazard_description: str = None
    consumer_action: str = None
    units: int = 0

# Summary and charts
class InsightSummary(BaseModel):
    total_recalls: int
    avg_units: int
    top_manufacturers: Dict[str,int]
    top_sellers: Dict[str,int]

class InsightCounter(BaseModel):
    name: str
    count: int

# === FASTAPI ===
app = FastAPI(title="CPSC BFF API")

# === UTILITIES ===
def get_auxiliary(conn, table_name: str, recall_number: str):
    sql = f"SELECT * FROM {table_name} WHERE recall_number = ?"
    rows = conn.query(sql, [recall_number])
    return [r[list(r.keys())[1]] for r in rows] if rows else []

# === ROUTES ===
@app.get("/recalls/", response_model=List[RecallOut])
def list_recalls(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                 manufacturer: str = None, country: str = None, source: str = None):
    conn = IRISConnection()
    sql = "SELECT * FROM cpsc_data ORDER BY recall_date DESC"
    all_records = conn.query(sql)
    if not all_records:
        raise HTTPException(status_code=404, detail="No recalls found")

    # Filtering
    filtered = []
    for rec in all_records:
        rn = rec['recall_number']
        rec['manufacturers'] = get_auxiliary(conn, "cpsc_manufacturers", rn)
        rec['sold_at'] = get_auxiliary(conn, "cpsc_sold_at", rn)
        rec['country'] = get_auxiliary(conn, "cpsc_manufactured_in", rn)
        rec['remedy_type'] = get_auxiliary(conn, "cpsc_remedy_type", rn)
        rec['recall_date'] = parse_date(rec.get('recall_date'))
        rec['units'] = rec.get('units') or 0

        if manufacturer and manufacturer not in rec['manufacturers']:
            continue
        if country and country not in rec['country']:
            continue
        if source and source != rec.get('source'):
            continue
        filtered.append(rec)

    skip = (page - 1) * page_size
    return filtered[skip:skip+page_size]

@app.get("/recalls/{recall_number}", response_model=RecallOut)
def recall_detail(recall_number: str):
    conn = IRISConnection()
    sql = "SELECT * FROM cpsc_data WHERE recall_number = ?"
    results = conn.query(sql, [recall_number])
    if not results:
        raise HTTPException(status_code=404, detail=f"Recall {recall_number} not found")
    rec = results[0]

    # Preencher campos relacionados
    rec['manufacturers'] = get_auxiliary(conn, "cpsc_manufacturers", recall_number)
    rec['sold_at'] = get_auxiliary(conn, "cpsc_sold_at", recall_number)
    rec['country'] = get_auxiliary(conn, "cpsc_manufactured_in", recall_number)
    rec['remedy_type'] = get_auxiliary(conn, "cpsc_remedy_type", recall_number)
    rec['recall_date'] = parse_date(rec.get('recall_date'))
    rec['units'] = rec.get('units') or 0

    return rec

@app.get("/insights/summary", response_model=InsightSummary)
def get_summary():
    conn = IRISConnection()
    
    # 1. Buscar dados principais
    data = conn.query("SELECT recall_number, units FROM cpsc_data")
    if not data:
        raise HTTPException(status_code=404, detail="No data")

    total_recalls = len(data)
    units_list = [d['units'] or 0 for d in data]
    valid_units = [u for u in units_list if u]
    avg_units = int(sum(valid_units) / len(valid_units)) if valid_units else 0

    # 2. Buscar todas as tabelas auxiliares de uma vez
    manufacturers_data = conn.query("SELECT recall_number, value FROM SQLUser.cpsc_manufacturers")
    sellers_data = conn.query("SELECT recall_number, value FROM SQLUser.cpsc_sold_at")
    countries_data = conn.query("SELECT recall_number, value FROM SQLUser.cpsc_manufactured_in")

    # 3. Criar dicionário recall_number -> lista de valores
    manufacturers_map = {}
    for r in manufacturers_data:
        manufacturers_map.setdefault(r['recall_number'], []).append(r['value'])

    sellers_map = {}
    for r in sellers_data:
        sellers_map.setdefault(r['recall_number'], []).append(r['value'])

    countries_map = {}
    for r in countries_data:
        countries_map.setdefault(r['recall_number'], []).append(r['value'])

    # 4. Construir contadores
    top_manufacturers = Counter()
    top_sellers = Counter()
    country_counter = Counter()
    for rec in data:
        rn = rec['recall_number']
        top_manufacturers.update(manufacturers_map.get(rn, []))
        top_sellers.update(sellers_map.get(rn, []))
        country_counter.update(countries_map.get(rn, []))

    countries_affected = len(country_counter)  # simplificado

    return {
        "total_recalls": total_recalls,
        "avg_units": avg_units,
        "top_manufacturers": dict(top_manufacturers.most_common(10)),
        "top_sellers": dict(top_sellers.most_common(10)),
        "countries_affected": countries_affected
    }


@app.get("/insights/by_month", response_model=List[InsightCounter])
def by_month():
    conn = IRISConnection()
    data = conn.query("SELECT recall_date FROM cpsc_data WHERE recall_date IS NOT NULL")
    month_counter = Counter()
    for rec in data:
        dt = rec['recall_date']
        if isinstance(dt, (int, float)):
            dt = datetime.datetime.fromtimestamp(dt)
        elif isinstance(dt, datetime.date):
            dt = datetime.datetime(dt.year, dt.month, dt.day)
        month_counter[dt.strftime("%Y-%m")] += 1
    return [{"name": m, "count": c} for m, c in sorted(month_counter.items())]


@app.get("/insights/by_country", response_model=List[InsightCounter])
def by_country():
    conn = IRISConnection()
    data = conn.query("SELECT * FROM cpsc_manufactured_in")
    country_counter = Counter()
    for rec in data:
        country_counter.update([rec[list(rec.keys())[1]]])
    return [{"name": c, "count": n} for c, n in country_counter.most_common()]

@app.get("/insights/by_remedy_type", response_model=List[InsightCounter])
def by_remedy():
    conn = IRISConnection()
    data = conn.query("SELECT * FROM cpsc_remedy_type")
    counter = Counter()
    for rec in data:
        counter.update([rec[list(rec.keys())[1]]])
    return [{"name": r, "count": n} for r, n in counter.most_common()]

@app.get("/insights/by_hazard", response_model=List[InsightCounter])
def by_hazard():
    conn = IRISConnection()
    data = conn.query("SELECT hazard_description FROM cpsc_data WHERE hazard_description IS NOT NULL")
    counter = Counter()
    for rec in data:
        counter.update([rec['hazard_description']])
    return [{"name": h, "count": n} for h, n in counter.most_common()]

# === RUN SERVER ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bff_api:app", host="0.0.0.0", port=8001, reload=True)
