from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import requests, logging, time

app = FastAPI(title="Rine FF API - Full Stats + Cache")
logger = logging.getLogger("uvicorn.error")

FREE_FF_API_BASES = [
    "https://free-ff-api-src-5plp.onrender.com/api/v1/account"
]
FF_COMMUNITY_KEY = ""  # nếu có, đặt vào env biến
TIMEOUT = 10
CACHE_EXP = 300  # 5 phút
cache = {}

class KADStats(BaseModel):
    team1: Optional[float] = None
    team2: Optional[float] = None
    team4: Optional[float] = None

class FFInfoFull(BaseModel):
    uid: str
    nickname: Optional[str] = None
    level: Optional[int] = None
    accountId: Optional[str] = None
    region: Optional[str] = None
    likes: Optional[int] = None
    vip_level: Optional[int] = None
    bio: Optional[str] = None
    survival_rank: Optional[str] = None
    clash_rank: Optional[str] = None
    survival_kad: Optional[KADStats] = None
    clash_kad: Optional[float] = None
    diamonds_spent: Optional[int] = None
    raw: dict

def fetch_free_ff(uid: str, region="ID"):
    for base in FREE_FF_API_BASES:
        try:
            r = requests.get(base, params={"uid": uid, "region": region}, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.info("free-ff-api error: %s", e)
    raise RuntimeError("All free-ff-api endpoints failed")

def fetch_ff_community(uid: str, region="sg"):
    if not FF_COMMUNITY_KEY:
        raise RuntimeError("No FF_COMMUNITY_KEY configured")
    headers = {"x-api-key": FF_COMMUNITY_KEY}
    r = requests.get("https://developers.freefirecommunity.com/api/v1/info", headers=headers,
                     params={"uid": uid, "region": region}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def parse_data(uid, region, data):
    basic = data.get("basicInfo", {})
    stats = data.get("stats", {})
    survival_kad = KADStats(
        team1=stats.get("survival", {}).get("kad", {}).get("team1"),
        team2=stats.get("survival", {}).get("kad", {}).get("team2"),
        team4=stats.get("survival", {}).get("kad", {}).get("team4"),
    )
    clash_kad = stats.get("clash", {}).get("kad")
    survival_rank = stats.get("survival", {}).get("rank")
    clash_rank = stats.get("clash", {}).get("rank")
    likes = basic.get("likes")
    diamonds_spent = stats.get("totalDiamondSpent")
    vip_level = basic.get("vip")
    bio = basic.get("bio")
    return FFInfoFull(
        uid=uid,
        nickname=basic.get("nickname"),
        level=basic.get("level"),
        accountId=basic.get("accountId"),
        region=region,
        likes=likes,
        vip_level=vip_level,
        bio=bio,
        survival_rank=survival_rank,
        clash_rank=clash_rank,
        survival_kad=survival_kad,
        clash_kad=clash_kad,
        diamonds_spent=diamonds_spent,
        raw=data
    )

@app.get("/info_full", response_model=FFInfoFull)
def get_info_full(uid: str = Query(...), region: Optional[str] = Query(None)):
    region_try = region or "ID"
    cache_key = f"{uid}_{region_try}"
    now = time.time()
    if cache_key in cache:
        data, t = cache[cache_key]
        if now - t < CACHE_EXP:
            return data
    # Try public free-ff-api
    try:
        data_raw = fetch_free_ff(uid, region_try)
        result = parse_data(uid, region_try, data_raw)
        cache[cache_key] = (result, now)
        return result
    except Exception as e:
        logger.info("Public API failed: %s", e)
    # Fallback to Free Fire Community API
    try:
        data_raw = fetch_ff_community(uid, region_try)
        result = parse_data(uid, region_try, data_raw)
        cache[cache_key] = (result, now)
        return result
    except Exception as e:
        logger.error("All upstream failed: %s", e)
        raise HTTPException(status_code=502, detail="All upstream providers failed")
