![Python](https://img.shields.io/badge/python-3.13-blue)
![AWS](https://img.shields.io/badge/AWS-SAM-orange)


# GreenTrain AI

LLM 학습을 위한 한국 전력망 실시간 탄소 집약도 기반 저전력·고효율 인프라 도구.

학습 코드에 4줄을 추가하면, 한국 grid가 더러운 시간엔 GPU가 자동으로 느려지고, 깨끗해지면 풀스피드로 돌아간다. 모델은 그대로 수렴하되 wall-clock 시간만 길어지며, 그동안 탄소 배출이 줄어든다.

---

## 동작 원리

```
ElectricityMap API (한국 grid, zone=KR)
   ↓ Lambda fetch (EventBridge 15분 cron)
DynamoDB 상태 테이블
   ↓ API Gateway
로컬 Python 에이전트 (3초마다 polling)
   ↓
PyTorch 학습 루프 (batch 사이 sleep 자동 주입)
   ↓
GPU 전력 실측 (nvidia-smi)
   ↓ API Gateway
DynamoDB 메트릭 테이블
   ↓
웹 대시보드 (Streamlit + Plotly)
```

탄소 집약도에 따른 throttle:
- **GREEN** (< 400 gCO₂/kWh): 정상 속도 학습
- **YELLOW** (400-600): sleep ratio 1 (약 50% 속도)
- **RED** (≥ 600): sleep ratio 4 (약 20% 속도)

---

## 폴더 구조

```
greentrain/
├── greentrain_agent/        # 로컬 Python 에이전트 (재사용 가능한 패키지)
│   ├── telemetry.py         # nvidia-smi 측정
│   ├── state.py             # CarbonState enum + sleep ratio 테이블
│   ├── throttle.py          # sleep 주입
│   ├── callback.py          # 학습 루프 hook
│   ├── client.py            # AWS HTTP 클라이언트
│   ├── poller.py            # 백그라운드 /state polling
│   └── reporter.py          # 백그라운드 /metric POST queue
├── aws/                     # AWS SAM 서버리스 백엔드
│   ├── template.yaml
│   └── functions/           # 5개 Lambda
│       ├── carbon_judge/    # EventBridge 트리거, ElectricityMap fetch
│       ├── get_state/       # GET /state
│       ├── post_metric/     # POST /metric
│       ├── get_session/     # GET /session/{id}
│       └── simulate/        # POST /simulate (데모용)
├── examples/
│   ├── test_telemetry.py    # GPU 측정 smoke test
│   └── train_demo.py        # PyTorch 학습 + agent 통합 예시
└── scripts/
    ├── peek_state.py        # GET /state
    ├── simulate.py          # 강제 상태 트리거 (데모용)
    ├── dashboard.py         # 터미널 rich TUI
    └── dashboard_web.py     # 웹 Streamlit 대시보드
```

---

## 빠른 시작

### 사전 준비

- Python 3.13+ (3.11+ 호환 예상)
- NVIDIA GPU + CUDA 드라이버 (nvidia-smi 동작 필요)
- AWS 계정 (Free Tier로 충분)
- ElectricityMap 무료 API 키 ([발급](https://www.electricitymaps.com/free-tier-api))

### 1. AWS 백엔드 배포

```bash
pip install awscli aws-sam-cli
aws configure  # 서울 리전 ap-northeast-2 권장

cd aws
sam build
sam deploy --guided  # 처음 한 번
# 또는 ElectricityMap 키와 함께:
sam deploy --parameter-overrides "ElectricityMapApiKey=YOUR_KEY ElectricityMapZone=KR"
```

배포 후 출력되는 `ApiUrl`을 다음 단계에 사용.

### 2. 로컬 환경 세팅

```bash
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cu128  # CUDA wheel

cp .env.example .env
# .env 편집: GREENTRAIN_API_URL=<위 ApiUrl>
```

### 3. 데모 실행

3개 터미널:

```bash
# 터미널 1: 학습
python examples/train_demo.py --batches 2000 --remote --poll-interval 3

# 터미널 2: 웹 대시보드
streamlit run scripts/dashboard_web.py

# 터미널 3: 강제 상태 전환 (시연용)
python scripts/simulate.py RED --duration 1
```

대시보드 사이드바의 Demo 모드 토글로 강제 전환도 가능.

---

## 학습 코드에 통합하기

```python
from transformers import AutoModelForCausalLM
from greentrain_agent import GreenTrainCallback, GreenTrainClient, StatePoller, Throttler

model = AutoModelForCausalLM.from_pretrained("gpt2").cuda()
optim = torch.optim.AdamW(model.parameters(), lr=1e-5)

# === GreenTrain 통합 (4줄) ===
cb = GreenTrainCallback(throttler=Throttler())
StatePoller(GreenTrainClient(), cb.throttler, interval_seconds=3).start()
# =============================

for batch in dataloader:
    cb.on_batch_start()
    optim.zero_grad()
    loss = model(**batch).loss
    loss.backward()
    optim.step()
    cb.on_batch_end()
```

학습 코드 본체는 변경 없음. 어떤 LLM (GPT, BERT, LLaMA, Mistral 등)에도 즉시 적용 가능.

---

## 솔직한 한계

이 도구는 환경에 따라 효과가 크게 다름:

| 환경 | 효용 | 이유 |
|---|---|---|
| 데이터센터 GPU 서버 (A100/H100) | 매우 강함 | GPU가 시스템 전력의 80%+ 차지 |
| 항상 켜진 ML 워크스테이션 | 강함 | 시스템 오버헤드가 sunk cost |
| 클라우드 GPU 인스턴스 (시간 과금) | 약함 | throttle해도 인스턴스 비용 그대로 |
| 노트북 + 학습 후 종료 | 매우 약함 (역효과 가능) | 시스템 오버헤드 60W × 연장 시간이 GPU 절감 상쇄 |

주 타깃은 **데이터센터 / 항상 켜진 GPU 인프라**. 노트북 환경은 작동 원리 시연용.

자세한 분석은 [`docs/GreenTrain_AI_Implementation_Report.md`](../GreenTrain_AI_Implementation_Report.md) 참조.

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| 로컬 에이전트 | Python 3.13, PyTorch 2.11+, `nvidia-smi` |
| AWS 백엔드 | EventBridge, Lambda (Python 3.13), API Gateway HTTP API, DynamoDB |
| 배포 도구 | AWS SAM CLI |
| 외부 데이터 | ElectricityMap Free Tier API (zone=KR) |
| 웹 대시보드 | Streamlit, Plotly, Pandas |

비용: AWS Free Tier 한도 안 설계. 추가 인프라 비용 0.

---

## 검증 상태

- AWS 서버리스 백엔드 5개 Lambda 배포 및 동작 확인
- ElectricityMap 실시간 한국 grid 데이터 fetch 확인 (예: 473 gCO₂/kWh, 4분 사이 468→473 변동 검증)
- 로컬 에이전트 PyTorch 통합 동작 확인 (RTX 4070 Laptop, 풀 부하 166W, GREEN 평균 85W 실측)
- 웹 대시보드 실시간 차트 + 절감 카운터 동작 확인
- 라이브 데모 시나리오 검증 (학습 + 대시보드 + 시뮬레이터 3창)

---

## 라이선스

MIT License. 자세한 내용은 [LICENSE](LICENSE) 참조.

---

## 관련 문서

- [구현 보고서](../GreenTrain_AI_Implementation_Report.md) — 상세 구현 내용, 검증된 값과 추정값 구분
- [아이디어 노트 (해커톤 제출용)](../GreenTrain_AI_Idea_Note_Final.md) — 문제 정의, 선정 이유, 멘토 질문
