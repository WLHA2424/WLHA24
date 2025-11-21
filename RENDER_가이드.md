# Render + UptimeRobot 24시간 무료 배포 가이드

## 준비물
- GitHub 계정
- Render 계정 (무료)
- UptimeRobot 계정 (무료)

## 1단계: GitHub에 코드 업로드
1. GitHub 저장소 생성
2. 모든 파일 업로드:
   - `bot.py`
   - `config.py`
   - `keepalive.py`
   - `requirements.txt`
   - `Procfile`
   - `message_ids.txt`
   - `.env` (또는 Render에서 환경변수로 설정)

## 2단계: Render 배포
1. https://render.com 접속 → Sign Up (GitHub로 가입)
2. Dashboard → **New** → **Web Service**
3. GitHub 저장소 연결
4. 설정:
   - **Name**: `telegram-bot` (원하는 이름)
   - **Region**: `Singapore`
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: (비워두기 - Procfile 사용)
   - **Plan**: `Free`
5. **Environment Variables** 추가:
   - `BOT_TOKEN`: 텔레그램 봇 토큰
   - `SOURCE_CHANNEL_ID`: 소스 채널 ID
   - `TARGET_GROUP_IDS`: 대상 그룹 ID (쉼표로 구분)
   - `SEND_INTERVAL_HOURS`: `0`
   - `SEND_INTERVAL_MINUTES`: `10`
   - `PORT`: `8080`
6. **Create Web Service** 클릭

## 3단계: UptimeRobot 설정
1. https://uptimerobot.com 접속 → Sign Up
2. Dashboard → **Add New Monitor**
3. 설정:
   - **Monitor Type**: `HTTP(s)`
   - **Friendly Name**: `Telegram Bot`
   - **URL**: Render에서 제공한 URL (예: `https://telegram-bot.onrender.com`)
   - **Monitoring Interval**: `5 minutes`
4. **Create Monitor** 클릭

## 완료!
- Render가 15분 미사용 시 잠들지만, UptimeRobot이 5분마다 깨워줍니다
- 완전 무료로 24시간 운영 가능합니다


