# JeonSafe BE

> **전세사기 예방 및 법률대응 지원 플랫폼 – 백엔드 레포지토리**  
> FastAPI 기반으로 개발된 RESTful API 서버입니다.  
> 사용자 인증(JWT), 증빙 파일 업로드(로컬 / AWS S3), 사전 위험 분석 및 대화 로그 관리 등의 기능을 제공합니다.


## 📁 프로젝트 구조
```
BE/
├── app/
│ ├── core/       # 공통 설정, 보안, DB, S3 클라이언트 등
│ │ ├── config.py
│ │ ├── db.py
│ │ ├── s3.py
│ │ └── security.py
│ ├── models/     # SQLAlchemy ORM 모델
│ ├── schemas/    # Pydantic 스키마 정의
│ ├── routes/     # FastAPI 라우트 (엔드포인트)
│ │ ├── auth.py
│ │ ├── chat.py
│ │ ├── precheck.py
│ │ └── upload.py
│ └── main.py     # FastAPI 진입점
├── uploads/      # 로컬 업로드 저장 디렉터리
├── .env          # 환경변수 파일 (AWS, JWT, DB 등)
├── requirements.txt
└── README.md
```

## ⚙️ 주요 기능

| 기능 | 설명 |
|------|------|
| 🔐 **Auth** | 회원가입, 로그인, JWT 기반 인증 |
| 💬 **Chat** | AI 챗로그 저장 및 조회 |
| 📄 **File Upload** | PDF / 이미지 파일 업로드 및 S3 저장 지원 |
| ☁️ **AWS S3 연동** | presigned URL 기반 안전한 파일 다운로드 |
| 🔍 **Precheck** | 계약서 사전 위험 점검 및 분석 (추후 AI 연동 예정) |


## 🚀 실행 방법

### 1️⃣ 환경 준비
Python 3.10 이상 권장  
(Windows 기준 예시)

```bash
# 1. 가상환경 생성
python -m venv .venv-sms

# 2. 가상환경 활성화
# Windows PowerShell
.venv-sms\Scripts\activate
# macOS / Linux
source .venv-sms/bin/activate
````

### 2️⃣ 패키지 설치
```powershell
pip install -r requirements.txt
```

### 3️⃣ 환경변수 설정
- `.env` 파일은 BE 루트에 존재합니다.

### 4️⃣ 서버 실행
```powershell
uvicorn app.main:app --reload
```
- 서버가 실행되면 `http://127.0.0.1:8000/docs`
 에서 Swagger UI로 API를 테스트할 수 있습니다.


 ## 🧩 주요 API 엔드포인트

 | Method | Endpoint                       | 설명                  |
| :----: | :----------------------------- | :------------------ |
|  POST  | `/api/auth/signup`             | 회원가입                |
|  POST  | `/api/auth/login`              | 로그인 (JWT 토큰 발급)     |
|  POST  | `/api/files`                   | 파일 업로드 (로컬 or S3)   |
|   GET  | `/api/files/{id}/download-url` | S3 presigned URL 조회 |
|   GET  | `/api/files/{id}/download`     | 로컬 파일 다운로드          |
|   GET  | `/api/chat/logs`               | 대화 로그 조회            |

## 🧰 기술 스택

- **Backend**: FastAPI, Uvicorn

- **DB**: SQLAlchemy

- **Security**: JWT (python-jose), bcrypt (passlib)

- **Storage**: AWS S3 (boto3) + Local Fallback

- **Validation**: Pydantic

- **Environment**: python-dotenv

## 🧑‍💻 개발 환경

- Python 3.10+

- FastAPI 0.114+

- AWS SDK (boto3)

- Visual Studio Code

- Windows 11 호환

## 💬 문의

shshshsh77710@gmail.com