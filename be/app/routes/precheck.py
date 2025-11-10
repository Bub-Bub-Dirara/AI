from fastapi import APIRouter
from be.app.schemas.contracts import ContractRequest, RiskReport

router = APIRouter(prefix="/precheck", tags=["Precheck"])

@router.post("/contracts", response_model=RiskReport, summary="전세계약 분석 요청")
def analyze_contract(body: ContractRequest):
    # TODO: 실제 분석 로직 연결
    return RiskReport(
        contractId="ctr_8f29a1c2",
        riskScore=0.82,
        riskFactors=["등기부 불일치", "임대인 채무 과다"],
        status="PENDING",
    )

@router.get("/contracts/{contract_id}/risk-report",
            response_model=RiskReport,
            summary="특정 계약의 리스크 리포트 조회")
def get_risk_report(contract_id: str):
    # TODO: DB 조회/상태 반환
    return RiskReport(
        contractId=contract_id,
        riskScore=0.45,
        riskFactors=["전세권 설정 이상 없음", "근저당 낮음"],
        status="DONE",
    )
