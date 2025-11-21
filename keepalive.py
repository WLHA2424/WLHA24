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
    """KeepAlive 서버 실행 (Render에서도 작동)"""
    import os
    import socket
    
    # Render에서는 PORT 환경변수를 사용, 없으면 8080 사용
    if port is None:
        port = int(os.environ.get('PORT', 8080))
    
    # Render가 포트를 감지할 수 있도록 메인 프로세스에서 바인딩
    try:
        # 포트 사용 가능 여부 확인
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        if result != 0:  # 포트가 사용 가능
            print(f"KeepAlive 서버 시작: http://0.0.0.0:{port} (PORT 환경변수: {os.environ.get('PORT', '없음')})")
            # Render에서도 작동하도록 설정
            app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
            return
        else:
            # 포트가 사용 중이면 다른 포트 시도 (최대 3회)
            print(f"포트 {port}가 사용 중입니다. 다른 포트를 시도합니다...")
            for attempt in range(3):
                port += 1
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.settimeout(1)
                    result = sock.connect_ex(('127.0.0.1', port))
                    sock.close()
                    if result != 0:
                        print(f"KeepAlive 서버 시작: http://0.0.0.0:{port}")
                        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
                        return
                except:
                    continue
    except Exception as e:
        print(f"KeepAlive 서버 시작 중 오류: {e}")
        # 오류가 발생해도 계속 진행 (봇은 정상 작동)
    
    # 모든 포트 시도 실패 시 경고만 출력하고 계속 진행
    print(f"경고: KeepAlive 서버 포트를 찾을 수 없습니다. (시도한 포트: {port}~{port+2})")

if __name__ == '__main__':
    run_keepalive()

