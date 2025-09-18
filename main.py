from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel
from typing import List, Literal
from datetime import datetime
import math
import random

app = FastAPI(
    title="3I/ATLAS Mission Planner API",
    version="1.0.0",
    description="API for simulating spacecraft interception missions to 3I/ATLAS"
)

# -------------------------
# CORS Middleware
# -------------------------
# Allowed origins: localhost (dev) + Vercel frontend (prod)
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if allowed_origins_env:
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
else:
    # Local development fallback
    allowed_origins = [
        "http://localhost:3000",
        "https://localhost:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Pydantic Models
# -------------------------
class MissionParameters(BaseModel):
    launch_date: str
    propulsion_type: Literal["chemical", "ion", "solar-sail"]
    payload_size: Literal["small", "medium", "large"]

class MissionResults(BaseModel):
    travel_time: float
    delta_v: float
    success_probability: float
    mission_log: List[str]
    fuel_cost: float
    mission_status: str

class AtlasInfo(BaseModel):
    name: str
    discovery_date: str
    description: str
    characteristics: dict
    scientific_value: str

# -------------------------
# Debug Endpoint
# -------------------------
@app.post("/api/debug")
async def debug_request(request: Request):
    data = await request.json()
    print("=== RAW FRONTEND REQUEST ===")
    print(data)

    raw_date = data.get("launch_date")
    parsed_date = None
    if raw_date:
        try:
            parsed_date = datetime.fromisoformat(raw_date.replace("T", " "))
        except:
            try:
                parsed_date = datetime.fromtimestamp(int(raw_date)/1000)
            except:
                parsed_date = None

    return {
        "received": data,
        "parsed_date": str(parsed_date) if parsed_date else None
    }

# -------------------------
# Mission Simulation Logic
# -------------------------
def calculate_mission_parameters(params: MissionParameters) -> MissionResults:
    ATLAS_VELOCITY = 60.0
    EARTH_ORBITAL_VELOCITY = 30.0
    OPTIMAL_LAUNCH_DATE = datetime(2025, 10, 30, 10, 0)
    ATLAS_PERIHELION_DISTANCE = 1.4
    ATLAS_CLOSEST_EARTH_DISTANCE = 1.8

    try:
        launch_date = datetime.fromisoformat(params.launch_date.replace("T", " "))
    except:
        launch_date = OPTIMAL_LAUNCH_DATE

    days_diff = abs((launch_date - OPTIMAL_LAUNCH_DATE).days)
    time_from_perihelion = days_diff / 365.25
    current_distance = ATLAS_PERIHELION_DISTANCE + abs(time_from_perihelion) * 2.0

    # Base mission parameters
    base_delta_v = 15.0 + (current_distance - ATLAS_CLOSEST_EARTH_DISTANCE) * 5.0
    base_travel_time = 2.0 + (current_distance - ATLAS_CLOSEST_EARTH_DISTANCE) * 1.5
    base_success = max(0.05, 0.8 - (current_distance - ATLAS_CLOSEST_EARTH_DISTANCE) * 0.2)

    propulsion_modifiers = {
        "chemical": {"delta_v_mult": 1.0, "time_mult": 0.8, "success_mod": -0.4, "fuel_efficiency": 0.3, "max_delta_v": 15.0},
        "ion": {"delta_v_mult": 0.7, "time_mult": 1.5, "success_mod": -0.2, "fuel_efficiency": 0.8, "max_delta_v": 25.0},
        "solar-sail": {"delta_v_mult": 0.4, "time_mult": 3.0, "success_mod": -0.6, "fuel_efficiency": 1.0, "max_delta_v": 10.0},
    }

    payload_modifiers = {
        "small": {"delta_v_mult": 0.9, "time_mult": 0.9, "success_mod": 0.1},
        "medium": {"delta_v_mult": 1.0, "time_mult": 1.0, "success_mod": 0.0},
        "large": {"delta_v_mult": 1.3, "time_mult": 1.3, "success_mod": -0.1},
    }

    prop_mod = propulsion_modifiers[params.propulsion_type]
    payload_mod = payload_modifiers[params.payload_size]

    date_penalty = min(days_diff / 30.0, 1.0)

    delta_v = base_delta_v * prop_mod["delta_v_mult"] * payload_mod["delta_v_mult"] * (1 + date_penalty * 0.2)
    velocity_matching_requirement = ATLAS_VELOCITY - EARTH_ORBITAL_VELOCITY
    total_delta_v = delta_v + velocity_matching_requirement

    travel_time = base_travel_time * prop_mod["time_mult"] * payload_mod["time_mult"] * (1 + date_penalty * 0.1)

    excess_dv_ratio = max(0.0, (total_delta_v - prop_mod["max_delta_v"]) / prop_mod["max_delta_v"])
    success_probability = max(0.01, min(0.95,
        base_success * (1 - 0.5 * excess_dv_ratio) + prop_mod["success_mod"] + payload_mod["success_mod"] - date_penalty * 0.2
    ))

    fuel_cost = delta_v * (1 / prop_mod["fuel_efficiency"]) * (1 + payload_mod["delta_v_mult"] - 1)

    if launch_date.year > 2026:
        mission_status = "failure"
        success_probability = 0.0
        mission_log = [
            f"❌ Mission IMPOSSIBLE: Launch after 2026",
            f"Launch date: {params.launch_date}"
        ]
    else:
        if success_probability >= 0.8:
            mission_status = "success"
        elif success_probability >= 0.6:
            mission_status = "warning"
        else:
            mission_status = "failure"

        mission_log = [
            f"Launch date: {params.launch_date}",
            f"Propulsion: {params.propulsion_type.title()}",
            f"Payload: {params.payload_size.title()}",
            f"Estimated travel time: {travel_time:.1f} years",
            f"Total ΔV required: {total_delta_v:.1f} km/s",
            f"Fuel cost estimate: {fuel_cost:.1f} units",
            f"Success probability: {success_probability:.1%}",
        ]

    return MissionResults(
        travel_time=travel_time,
        delta_v=delta_v,
        success_probability=success_probability,
        fuel_cost=fuel_cost,
        mission_status=mission_status,
        mission_log=mission_log
    )

# -------------------------
# API Endpoints
# -------------------------
@app.get("/")
def root():
    return {"message": "3I/ATLAS Mission Planner API", "version": "1.0.0", "status": "operational"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/simulate", response_model=MissionResults)
def simulate_mission(parameters: MissionParameters):
    try:
        return calculate_mission_parameters(parameters)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Simulation failed: {str(e)}")

@app.get("/atlas-info", response_model=AtlasInfo)
def get_atlas_info():
    return AtlasInfo(
        name="3I/ATLAS (2I/Borisov)",
        discovery_date="2019-08-30",
        description="3I/ATLAS is the first confirmed interstellar comet...",
        characteristics={
            "velocity": "32.1 km/s",
            "inclination": "44.1°",
            "eccentricity": "3.36",
            "perihelion": "2.01 AU",
            "composition": "Unknown - likely water ice and organic compounds"
        },
        scientific_value="Studying 3I/ATLAS would provide unprecedented data..."
    )

@app.get("/mission-history")
def get_mission_history():
    return {
        "missions": [
            {"name": "Voyager 1", "launch_date": "1977-09-05", "propulsion": "chemical",
             "delta_v": 15.1, "travel_time": 3.7, "status": "success"},
            {"name": "Voyager 2", "launch_date": "1977-08-20", "propulsion": "chemical",
             "delta_v": 15.1, "travel_time": 3.7, "status": "success"},
            {"name": "New Horizons", "launch_date": "2006-01-19", "propulsion": "chemical",
             "delta_v": 16.26, "travel_time": 9.5, "status": "success"}
        ]
    }

# -------------------------
# Run Server
# -------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
