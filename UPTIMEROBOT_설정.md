# UptimeRobot 설정 가이드

## 1단계: UptimeRobot 가입
1. https://uptimerobot.com 접속
2. "Sign Up" 클릭
3. 이메일, 비밀번호 입력
4. 이메일 인증 완료

## 2단계: 모니터 추가
1. 로그인 후 대시보드에서 **"Add New Monitor"** 클릭

## 3단계: 모니터 설정
다음 정보를 입력:

- **Monitor Type**: `HTTP(s)` 선택
- **Friendly Name**: `Telegram Bot KeepAlive` (원하는 이름)
- **URL (or IP)**: Replit 웹 URL 입력
  - 예: `https://WLHA24.WLHA24.repl.co/`
  - 또는: `https://WLHA24.WLHA24.repl.co/health`
- **Monitoring Interval**: `5 minutes` 선택

## 4단계: 저장
- **"Create Monitor"** 클릭

## 5단계: 확인
- UptimeRobot 대시보드에서 상태가 **"Up"** (초록색)인지 확인
- 5분 후 다시 확인하여 계속 "Up"인지 확인

## 완료! 🎉
이제 UptimeRobot이 5분마다 Replit에 요청을 보내서 Replit이 잠들지 않습니다!




