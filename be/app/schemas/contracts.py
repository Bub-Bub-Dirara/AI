from pydantic import BaseModel, Field
from typing import List

class ContractRequest(BaseModel):
    address: str = Field(..., example="서울시 노원구 광운대학교 새빛관 102호")
    deposit: int = Field(..., example=100_000_000)
    landlordName: str = Field(..., example="전사람")
    contractDate: str = Field(..., example="2025-10-20")  # ISO date string

class RiskReport(BaseModel):
    contractId: str = Field(..., example="ctr_8f29a1c2")
    riskScore: float = Field(..., ge=0, le=1, example=0.82)
    riskFactors: List[str] = Field(default_factory=list, example=["등기부 불일치", "임대인 채무 과다"])
    status: str = Field(..., example="PENDING")
