from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.routes.auth import router as auth_router
from app.api.routes.donations import router as donations_router
from app.api.routes.inventory import router as inventory_router
from app.api.routes.patient import router as patient_router
from app.api.routes.requests import patient_router as patient_requests_router, pharmacist_router as pharmacist_requests_router
from app.api.routes.prescriptions import patient_router as patient_prescriptions_router, pharmacist_router as pharmacist_prescriptions_router
from app.api.routes.dispensing import patient_router as patient_dispensing_router, pharmacist_router as pharmacist_dispensing_router
from app.api.routes.waste import router as waste_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.checkout import router as checkout_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.clinic_verification import router as clinic_verification_router

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
    # Vite may select another port when 5173 is occupied. Keep the development
    # fallback limited to loopback hosts; deployed origins belong in the env list.
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth_router)
app.include_router(donations_router)
app.include_router(inventory_router)
app.include_router(patient_router)
app.include_router(patient_requests_router)
app.include_router(pharmacist_requests_router)
app.include_router(patient_prescriptions_router)
app.include_router(pharmacist_prescriptions_router)
app.include_router(patient_dispensing_router)
app.include_router(pharmacist_dispensing_router)
app.include_router(waste_router)
app.include_router(notifications_router)
app.include_router(checkout_router)
app.include_router(dashboard_router)
app.include_router(clinic_verification_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "healthy"}

