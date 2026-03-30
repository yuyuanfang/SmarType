@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -c "
import sys, pyaudio, audioop, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print('=== SmarType 麥克風測試 ===')
print()

pa = pyaudio.PyAudio()
print('可用輸入裝置：')
for i in range(pa.get_device_count()):
    d = pa.get_device_info_by_index(i)
    if d['maxInputChannels'] > 0:
        print(f'  [{i}] {d[\"name\"]}')
print()

import json
from pathlib import Path
cfg = json.loads(Path('userdata/config.json').read_text(encoding='utf-8'))
dev = cfg.get('mic_index', 1)
thr = cfg.get('energy_thr', 20)
print(f'目前設定：麥克風=[{dev}]  閾值={thr}')
print()

try:
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                     input=True, input_device_index=dev, frames_per_buffer=512)
    print('請說話（測試 5 秒）...')
    peak = 0
    for i in range(100):
        data = stream.read(512, exception_on_overflow=False)
        rms = audioop.rms(data, 2)
        if rms > peak: peak = rms
        bar = '█' * min(40, rms // 5)
        triggered = ' <<< 觸發！' if rms > thr else ''
        print(f'\r  RMS={rms:>4d}  {bar:<40}{triggered}', end='', flush=True)
        time.sleep(0.05)
    stream.stop_stream(); stream.close()
    print()
    print()
    print(f'峰值 RMS = {peak}')
    print(f'目前閾值 = {thr}')
    if peak < thr:
        print(f'[問題] 說話時 RMS({peak}) < 閾值({thr})，麥克風無法觸發！')
        print(f'建議閾值 = {max(5, peak // 3)}')
    else:
        print('[正常] 說話時 RMS 超過閾值，可以正常觸發。')
except Exception as e:
    print(f'錯誤：{e}')
finally:
    pa.terminate()
"
pause
