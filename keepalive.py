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

def run_keepalive(port=8080):
    """KeepAlive 서버 실행"""
    print(f"KeepAlive 서버 시작: http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    run_keepalive()

