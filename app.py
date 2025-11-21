"""
Replit Web Service 진입점
웹사이트처럼 24시간 작동하도록 KeepAlive 서버를 메인으로 실행하고,
봇을 백그라운드에서 실행합니다.
"""
import threading
import os
import sys
import time

def start_bot():
    """봇을 별도 스레드에서 실행"""
    try:
        # bot.py의 main 함수 실행
        from bot import main
        main()
    except Exception as e:
        print(f"봇 시작 실패: {e}")
        import traceback
        traceback.print_exc()

def start_web_server():
    """KeepAlive 웹서버 실행 (메인)"""
    from keepalive import app
    port = int(os.environ.get('PORT', 8080))
    print(f"KeepAlive 웹서버 시작: http://0.0.0.0:{port}")
    print("봇이 백그라운드에서 실행됩니다.")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    # 봇을 백그라운드 스레드에서 시작
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # 메인 스레드에서 웹서버 실행 (이게 메인 프로세스)
    # Replit이 이 웹서버를 Web Service로 인식하여 24시간 유지
    start_web_server()

