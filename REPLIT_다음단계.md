# Replit 다음 단계 (GitHub에서 Import 완료 후)

## 1단계: 파일 확인하기

Replit에서 다음 파일들이 있는지 확인:
- ✅ `bot.py`
- ✅ `config.py`
- ✅ `keepalive.py`
- ✅ `requirements.txt`

## 2단계: config.py 확인하기

`config.py` 파일을 열어서 설정이 올바른지 확인:

```python
BOT_TOKEN = "8558479211:AAFwxFXqsm8NufHC5fwc3L3wxatbMAQ1Zio"
SOURCE_CHANNEL_ID = "-1003363597143"
TARGET_GROUP_ID = "-1003369712631"
```

**이미 설정되어 있으면 그대로 사용하면 됩니다!**

## 3단계: 패키지 설치하기

Replit 터미널에서 실행:

```bash
pip install -r requirements.txt
```

설치되는 패키지:
- python-telegram-bot
- python-dotenv
- APScheduler
- flask

## 4단계: 봇 실행하기

Replit 터미널에서 실행:

```bash
python bot.py
```

**확인사항:**
- 콘솔에 "KeepAlive 서버가 시작되었습니다" 메시지
- 콘솔에 "봇이 시작되었습니다" 메시지
- 에러가 없어야 함

## 5단계: Replit URL 확인하기

1. Replit 오른쪽 상단 **"Webview"** 또는 **"Open in new tab"** 클릭
2. 또는 주소창에서 URL 확인:
   - 예: `https://telegram-bot.your-username.repl.co`
   - 이 URL을 복사해두세요!

## 6단계: UptimeRobot 설정하기

### 6-1. UptimeRobot 가입
1. https://uptimerobot.com 접속
2. "Sign Up" 클릭 (무료)
3. 이메일 인증

### 6-2. 모니터 추가
1. 로그인 후 **"Add New Monitor"** 클릭
2. 설정:
   - **Monitor Type**: `HTTP(s)` 선택
   - **Friendly Name**: `Telegram Bot KeepAlive`
   - **URL**: Replit URL 입력
     - 예: `https://telegram-bot.your-username.repl.co/`
   - **Monitoring Interval**: `5 minutes` 선택
3. **"Create Monitor"** 클릭

### 6-3. 확인
- UptimeRobot에서 상태가 **"Up"** (초록색)인지 확인

## 7단계: 테스트하기

1. **비공개 채널에 새 메시지 올리기**
   - 봇이 즉시 그룹에 전송하는지 확인

2. **명령어 테스트**
   - 비공개 채널에 `/설정` 입력
   - 응답 확인

## 완료! 🎉

이제 PC를 꺼도 Replit에서 24시간 실행됩니다!




