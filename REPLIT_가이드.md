# Replit + KeepAlive 설정 가이드 (단계별)

## 1단계: Replit 계정 만들기

1. https://replit.com 접속
2. "Sign up" 클릭하여 계정 생성 (Google/GitHub 계정으로도 가능)
3. 로그인

## 2단계: Replit에 새 프로젝트 만들기

1. Replit 대시보드에서 "Create Repl" 클릭
2. Template 선택: **"Python"** 선택
3. Project name: `telegram-bot` (원하는 이름)
4. "Create Repl" 클릭

## 3단계: 파일 업로드하기

### 방법 1: 직접 복사-붙여넣기

각 파일을 열어서 Replit에 복사:

1. **bot.py** 파일 내용 전체 복사 → Replit에서 `main.py` 삭제하고 새 파일 `bot.py` 만들기 → 붙여넣기
2. **config.py** 파일 내용 복사 → Replit에서 새 파일 `config.py` 만들기 → 붙여넣기
3. **keepalive.py** 파일 내용 복사 → Replit에서 새 파일 `keepalive.py` 만들기 → 붙여넣기
4. **requirements.txt** 파일 내용 복사 → Replit에서 새 파일 `requirements.txt` 만들기 → 붙여넣기

### 방법 2: GitHub 사용 (선택사항)

1. GitHub에 프로젝트 업로드
2. Replit에서 "Import from GitHub" 선택
3. GitHub 저장소 URL 입력

## 4단계: config.py 수정하기

Replit에서 `config.py` 파일 열기:

```python
import os

# 텔레그램 봇 토큰
BOT_TOKEN = "8558479211:AAFwxFXqsm8NufHC5fwc3L3wxatbMAQ1Zio"

# 소스 채널 ID (비공개 채널)
SOURCE_CHANNEL_ID = "-1003363597143"

# 대상 그룹 ID (메시지를 전달할 그룹)
TARGET_GROUP_ID = "-1003369712631"

# 전송 간격 (시간 단위, 기본값: 1시간)
SEND_INTERVAL_HOURS = 0.0

# 전송 간격 (분 단위로도 설정 가능)
SEND_INTERVAL_MINUTES = 1.0
```

**이미 설정되어 있으면 그대로 사용**

## 5단계: 패키지 설치하기

Replit 터미널에서 실행:

```bash
pip install -r requirements.txt
```

설치되는 패키지:
- python-telegram-bot
- python-dotenv
- APScheduler
- flask

## 6단계: 봇 실행하기

Replit 터미널에서 실행:

```bash
python bot.py
```

**확인사항:**
- 콘솔에 "KeepAlive 서버가 시작되었습니다" 메시지가 나와야 함
- 콘솔에 "봇이 시작되었습니다" 메시지가 나와야 함

## 7단계: Replit URL 확인하기

1. Replit 오른쪽 상단에 있는 **"Webview"** 또는 **"Open in new tab"** 클릭
2. 또는 Replit URL 확인:
   - 예: `https://telegram-bot.your-username.repl.co`
   - 이 URL을 복사해두세요

## 8단계: UptimeRobot 설정하기

### 8-1. UptimeRobot 가입

1. https://uptimerobot.com 접속
2. "Sign Up" 클릭
3. 무료 계정 생성 (이메일 인증 필요)

### 8-2. 모니터 추가

1. 로그인 후 대시보드에서 **"Add New Monitor"** 클릭
2. 설정 입력:
   - **Monitor Type**: `HTTP(s)` 선택
   - **Friendly Name**: `Telegram Bot KeepAlive` (원하는 이름)
   - **URL (or IP)**: Replit URL 입력
     - 예: `https://telegram-bot.your-username.repl.co/`
     - 또는: `https://telegram-bot.your-username.repl.co/health`
   - **Monitoring Interval**: `5 minutes` 선택
3. **"Create Monitor"** 클릭

### 8-3. 확인

- UptimeRobot 대시보드에서 상태가 **"Up"** (초록색)인지 확인
- 5분 후 다시 확인하여 계속 "Up"인지 확인

## 9단계: 테스트하기

1. **비공개 채널에 새 메시지 올리기**
   - 봇이 즉시 그룹에 전송하는지 확인

2. **명령어 테스트**
   - 비공개 채널에 `/설정` 입력
   - 비공개 채널에 응답이 오는지 확인

3. **KeepAlive 확인**
   - UptimeRobot에서 상태가 "Up"인지 확인
   - Replit 콘솔에서 KeepAlive 요청 로그 확인

## 10단계: 24시간 실행 확인

1. PC를 끄거나 Replit 브라우저를 닫아도 됩니다
2. 몇 시간 후 UptimeRobot에서 상태 확인
3. 비공개 채널에 메시지 올려서 봇이 작동하는지 확인

## 문제 해결

### KeepAlive 서버가 시작되지 않으면:
- `pip install flask` 실행
- `keepalive.py` 파일이 있는지 확인

### 봇이 메시지를 받지 못하면:
- 봇이 채널의 관리자로 추가되어 있는지 확인
- 봇이 채널에서 메시지를 읽을 권한이 있는지 확인

### UptimeRobot이 "Down"으로 표시되면:
- Replit URL이 올바른지 확인
- Replit에서 봇이 실행 중인지 확인
- Replit URL에 `/` 또는 `/health`를 추가해보기

## 완료!

이제 봇이 24시간 실행됩니다! 🎉

