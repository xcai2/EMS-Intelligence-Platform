from typing import Optional
from pydantic import BaseModel


class HyperscalerCompany(BaseModel):
    name: str
    ticker: str
    color: str
    capex_2026_billions: Optional[float] = None
    capex_2025_billions: Optional[float] = None
    yoy_growth_pct: Optional[float] = None
    ai_focus_areas: list[str] = []
    key_metrics: dict[str, str] = {}
    recent_announcements: list[str] = []


class StargateProject(BaseModel):
    total_investment_billions: Optional[float] = None
    timeline: str = ""
    partners: list[str] = []
    planned_capacity_gw: Optional[float] = None
    locations: list[str] = []


class Big5CapexResponse(BaseModel):
    companies: list[HyperscalerCompany] = []
    last_updated: str = ""
    source: str = "Gemini API"
    source_status: str = "missing_cache"  # "gemini_cached" | "missing_cache"
    total_2026_capex_billions: Optional[float] = None
    stargate_project: StargateProject = StargateProject()


class Big5CapexSummaryResponse(BaseModel):
    total_2026_capex_billions: Optional[float] = None
    avg_yoy_growth_pct: Optional[float] = None
    company_count: int = 0
    source_status: str = "missing_cache"


class HyperscalerFiscalYear(BaseModel):
    capex: Optional[float] = None
    revenue: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    operating_margin: Optional[float] = None


class HyperscalerCompanyFinancials(BaseModel):
    company: str
    ticker: str
    color: str
    fiscal_years: dict[str, HyperscalerFiscalYear] = {}
    source: str = "yfinance"
    fetched_at: str = ""
    error: Optional[str] = None


class HyperscalerFinancialsResponse(BaseModel):
    companies: list[HyperscalerCompanyFinancials] = []
    errors: list[str] = []
