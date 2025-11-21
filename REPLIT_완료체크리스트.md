# Replit 설정 완료 체크리스트

## ✅ 완료된 항목
- [x] GitHub에서 Replit으로 파일 import 완료
- [x] 필수 파일 확인 (bot.py, config.py, keepalive.py, requirements.txt)
- [x] KeepAlive 웹서버 실행 확인

## 🔄 다음 단계

### 1. Replit URL 확인
- 웹 미리보기 주소창에서 URL 복사
- 예: `https://WLHA24.your-username.repl.co`

### 2. 봇 실행 확인
터미널에서:
```bash
python bot.py
```

확인사항:
- "KeepAlive 서버가 시작되었습니다" 메시지
- "봇이 시작되었습니다" 메시지
- 에러 없음

### 3. UptimeRobot 설정
1. https://uptimerobot.com 가입
2. "Add New Monitor" 클릭
3. 설정:
   - Monitor Type: HTTP(s)
   - URL: Replit URL 입력
   - Interval: 5 minutes
4. "Create Monitor" 클릭

### 4. 테스트
- 비공개 채널에 메시지 올리기
- `/설정` 명령어 테스트

## 완료! 🎉
이제 PC를 꺼도 24시간 실행됩니다!



