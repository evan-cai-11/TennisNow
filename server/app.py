from fastapi import FastAPI, Query
from pydantic import BaseModel
from datetime import datetime
import asyncpg

app = FastAPI()

class AvailResult(BaseModel):
    court_id: int
    name: str
    distance_m: float
    explain: str | None = None
    conflicts: list[dict] | None = None

@app.get("/availability/search")
async def availability_search(
    lat: float, lng: float,
    start: datetime, end: datetime,
    radius_km: float = 8.0,
    public_only: bool = True
):
    conn = await asyncpg.connect(dsn="postgres://...")
    # Nearby courts
    rows = await conn.fetch("""
      SELECT id, name,
             ST_Distance(geom, ST_MakePoint($1,$2)::geography) AS meters
      FROM courts
      WHERE ST_DWithin(geom, ST_MakePoint($1,$2)::geography, $3*1000)
        AND ($4::bool IS FALSE OR is_public = TRUE)
      ORDER BY geom <-> ST_MakePoint($1,$2)::geography
      LIMIT 200
    """, lng, lat, radius_km, public_only)

    available, unavailable, unknown = [], [], []
    for r in rows:
        conflicts = await conn.fetch("""
            SELECT starts_at, ends_at, title
            FROM reservations
            WHERE court_id=$1 AND status='confirmed'
              AND tstzrange(starts_at, ends_at, '[)') &&
                  tstzrange($2, $3, '[)')
            ORDER BY starts_at
            LIMIT 5
        """, r["id"], start, end)
        if conflicts:
            unavailable.append({
              "court_id": r["id"],
              "name": r["name"],
              "distance_m": r["meters"],
              "conflicts": [dict(c) for c in conflicts],
              "explain": f"{len(conflicts)} overlapping reservation(s)"
            })
        else:
            # If no feed configured, treat as unknown
            feed = await conn.fetchval("SELECT calendar_feed_url FROM courts WHERE id=$1", r["id"])
            (available if feed else unknown).append({
              "court_id": r["id"],
              "name": r["name"],
              "distance_m": r["meters"],
              "explain": "No overlapping reservations in window" if feed else None
            })
    await conn.close()
    return {"available": available, "unavailable": unavailable, "unknown": unknown}
