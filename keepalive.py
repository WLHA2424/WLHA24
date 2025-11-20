"""
KeepAlive 웹서버 - Replit이 잠들지 않도록 유지
UptimeRobot이 5분마다 이 서버에 요청을 보내서 Replit을 깨워둡니다.
"""
from flask import Flask
import threading
import time

app = Flask(__name__)

@app.route('/')
def home():
    """홈 페이지 - UptimeRobot이 ping하는 엔드포인트"""
    return {
        "status": "ok",
        "message": "봇이 실행 중입니다",
        "timestamp": time.time()
    }, 200

@app.route('/health')
def health():
    """헬스 체크 엔드포인트"""
    return {
        "status": "healthy",
        "bot": "running"
    }, 200

def run_keepalive(port=None):
    """KeepAlive 서버 실행"""
    import os
    # Replit에서는 환경 변수 PORT를 사용, 없으면 8080 사용
    if port is None:
        port = int(os.environ.get('PORT', 8080))
    print(f"KeepAlive 서버 시작: http://0.0.0.0:{port}")
    # Replit에서는 use_reloader=False로 설정
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    run_keepalive()

