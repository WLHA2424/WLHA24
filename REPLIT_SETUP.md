# Replit + KeepAlive 설정 가이드

## 1. Replit에 프로젝트 업로드

1. Replit에 새 프로젝트 생성
2. 모든 파일 업로드:
   - `bot.py`
   - `config.py`
   - `requirements.txt`
   - `keepalive.py`
   - `.gitignore`

## 2. Replit에서 설정

### 환경 변수 설정
Replit의 Secrets 탭에서:
- `BOT_TOKEN`: 텔레그램 봇 토큰
- `SOURCE_CHANNEL_ID`: 비공개 채널 ID
- `TARGET_GROUP_ID`: 대상 그룹 ID

또는 `config.py`에 직접 입력

### 패키지 설치
```bash
pip install -r requirements.txt
```

## 3. UptimeRobot 설정

1. [UptimeRobot](https://uptimerobot.com) 가입 (무료)
2. "Add New Monitor" 클릭
3. 설정:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: Telegram Bot KeepAlive
   - **URL**: `https://your-repl-name.your-username.repl.co/`
   - **Monitoring Interval**: 5 minutes
4. "Create Monitor" 클릭

## 4. Replit 실행

Replit에서 `bot.py` 실행:
```bash
python bot.py
```

## 5. 확인

- Replit 콘솔에서 "KeepAlive 서버가 시작되었습니다" 메시지 확인
- UptimeRobot에서 상태가 "Up"인지 확인
- 5분마다 요청이 오는지 확인

## 주의사항

- Replit 무료 플랜은 CPU 시간 제한이 있을 수 있습니다
- UptimeRobot 무료 플랜은 50개 모니터까지 가능합니다
- KeepAlive 서버는 봇과 함께 실행되며, 봇이 종료되면 함께 종료됩니다








