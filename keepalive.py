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
    import socket
    # Replit에서는 환경 변수 PORT를 사용, 없으면 8080 사용
    if port is None:
        port = int(os.environ.get('PORT', 8080))
    
    # 포트가 이미 사용 중이면 다른 포트 시도
    for attempt in range(5):
        try:
            # 포트 사용 가능 여부 확인
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            
            if result != 0:  # 포트가 사용 가능
                print(f"KeepAlive 서버 시작: http://0.0.0.0:{port}")
                # Replit에서는 use_reloader=False로 설정
                app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
                return
            else:
                # 포트가 사용 중이면 다음 포트 시도
                port += 1
        except Exception as e:
            # 포트 확인 실패 시 다음 포트 시도
            port += 1
            continue
    
    # 모든 포트 시도 실패 시 경고만 출력하고 계속 진행
    print(f"경고: KeepAlive 서버 포트를 찾을 수 없습니다. (시도한 포트: {port-5}~{port-1})")

if __name__ == '__main__':
    run_keepalive()

