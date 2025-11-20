# 봇 24시간 실행 가이드 (무료)

PC를 종료해도 봇이 24시간 돌아가도록 하는 무료 방법들입니다.

## 방법 1: Render (가장 추천 - 쉬움)

### 장점
- 완전 무료 (제한적이지만 충분함)
- 자동 배포
- 쉬운 설정

### 단계
1. https://render.com 가입
2. New → Web Service 선택
3. GitHub 저장소 연결 (또는 직접 업로드)
4. 설정:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot.py`
5. 환경 변수 추가 (.env 파일 내용):
   - BOT_TOKEN
   - SOURCE_CHANNEL_ID
   - TARGET_GROUP_ID
   - SEND_INTERVAL_HOURS
   - SEND_INTERVAL_MINUTES

## 방법 2: Railway (추천)

### 장점
- 무료 크레딧 제공
- 매우 쉬운 설정
- GitHub 연동

### 단계
1. https://railway.app 가입
2. New Project → Deploy from GitHub
3. 저장소 선택
4. 환경 변수 추가
5. Deploy!

## 방법 3: PythonAnywhere

### 장점
- Python 전용
- 무료 티어 제공

### 단계
1. https://www.pythonanywhere.com 가입
2. Files 탭에서 파일 업로드
3. Tasks 탭에서 스케줄러 설정
4. Always-on task로 설정

## 방법 4: Oracle Cloud Always Free (가장 강력)

### 장점
- 완전 무료 (영구)
- VPS 제공
- 가장 강력함

### 단계
1. https://www.oracle.com/cloud/free/ 가입
2. VM 인스턴스 생성 (Always Free)
3. SSH로 접속
4. Python 및 봇 설치
5. systemd로 서비스 등록

## 방법 5: Google Colab (임시)

### 장점
- 즉시 사용 가능
- 완전 무료

### 단점
- 세션이 끊기면 중단 (최대 12시간)
- 안정성 낮음

## 빠른 시작: Render 사용하기

가장 쉬운 방법은 Render입니다. 아래 단계를 따르세요:

1. GitHub에 코드 업로드
2. Render에서 저장소 연결
3. 환경 변수 설정
4. Deploy!

자세한 내용은 각 서비스의 공식 문서를 참고하세요.

