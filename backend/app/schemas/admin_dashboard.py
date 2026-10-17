from pydantic import BaseModel


class ClinicCounts(BaseModel):
    total: int
    pending: int
    verified: int
    rejected: int


class UserCounts(BaseModel):
    total: int
    by_role: dict[str, int]


class StatusCounts(BaseModel):
    total: int
    by_status: dict[str, int]


class InventoryQuantities(BaseModel):
    available: int
    reserved: int


class AdminPlatformDashboard(BaseModel):
    clinics: ClinicCounts
    users: UserCounts
    donations: StatusCounts
    inventory: InventoryQuantities
    requests: StatusCounts
    waste: StatusCounts
