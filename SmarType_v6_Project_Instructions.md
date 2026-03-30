# 快打 SmarType v6 — Project Instructions

> **用途**：上下文衔接文档。在新对话开始时提供给 Claude，使其能快速掌握项目全局。
> **最后更新**：2026-03-21
> **维护者**：Yuyuan (gstarmanager18@gmail.com)

---

## 1. 项目概述

**快打 SmarType v6** 是一个 Windows 全局语音听写工具。按住右 Shift 说话，松开后自动识别语音并将文字注入到当前活动窗口（通过剪贴板 Ctrl+V）。

核心技术栈：Python 3.12.5 + Groq Whisper Large v3 Turbo API（主力） + OpenAI Whisper-1（备用）。

### 关键特性

- 全局热键监听（默认右 Shift，按住=录音，松开=识别+注入）
- 分段实时转录（每 3 秒调一次 Groq API，结果显示在屏幕底部胶囊条跑马灯）
- 自动语言检测（根据活动窗口切换 zh-TW / zh-CN / ko / en）
- 智能词典（自动从用户输入中学习高频词汇，加入 Whisper prompt 提升准确度）
- 系统托盘常驻 + 管理员权限运行
- 单实例锁（Windows Named Mutex，防止多进程出现双球）

---

## 2. 文件结构

### 主程序目录：`C:\whisper-dictation\`

| 文件 | 作用 |
|------|------|
| `dictation.py` | **主程序**（963行），包含所有核心逻辑 |
| `window_detector.py` | 检测当前活动窗口，返回进程名、语言标签等 |
| `smart_vocab.py` | 智能词典模块，自动学习高频词、导出 prompt words |
| `converter.py` | 文字后处理（简繁转换等），`convert(raw, target_lang)` |
| `app_rules.py` | 窗口→语言映射规则管理界面 |
| `vocab_manager.py` | 词汇管理界面 |
| `history_viewer.py` | 听写历史查看界面 |
| `start.bat` | 启动脚本（以管理员权限运行 dictation.py） |
| `setup.py` | 初始配置（API Key 设置等） |

### 配置目录：`C:\Users\gstar\.whisper-dictation\`

| 文件 | 作用 |
|------|------|
| `config.json` | 主配置（API Key、热键、麦克风选择等） |
| `vocabulary.json` | 用户词汇库（手动词汇 + 自动纠错映射） |
| `history.jsonl` | 听写历史记录（每条含时间戳、文字、窗口、字数） |
| `debug.log` | **调试日志**（v6 新增，每次按键/API调用/错误全记录） |

### 中转目录：`C:\Users\gstar\Desktop\AI_Bridge\`

由于 Cowork 沙盒无法直接写入 `C:\whisper-dictation\`，所有文件修改先写到 AI_Bridge，再由用户手动复制到目标目录。

---

## 3. dictation.py 架构（963行）

### 类和核心组件

```
Recorder             (183-256行)  录音器，支持分段回调
  .start(on_segment, seg_secs)    启动录音，每 seg_secs 秒触发 on_segment 回调
  .stop() -> bytes|None           停止录音，返回完整 WAV bytes
  ._callback()                    pyaudio stream callback，累积 frames + 分段触发

Transcriber          (539-593行)  转录器，Groq 优先 + OpenAI 备用
  .transcribe(wav_bytes, prompt)  主入口
  ._groq_transcribe()             verbose_json 模式，语言非中文时自动重试
  ._openai_transcribe()           OpenAI 备用

CenterBall           (351-493行)  底部胶囊条 UI（tkinter）
  480×56px, #1D9E75 绿色, 屏幕底部居中
  .show_recording(lang)           显示"聆聽中..."+ 脉冲动画
  .append_text(text)              替换模式显示跑马灯文字（不累加）
  .show_processing()              显示"⏳ 識別中..."
  .show_result(text, lang)        显示"✓"+ 预览文字，2.5秒后自动隐藏
  .show_error(msg)                显示"❌"+ 错误信息，3秒后隐藏
  .safe_*()                       线程安全版本（通过 root.after(0, ...)）

SmarTypeApp          (596-963行)  主应用
  .__init__()                     初始化所有组件 + _processing=False
  .on_press()                     热键按下 → 开始录音 + 分段转录
  .on_release()                   热键松开 → 停止录音 + 最终转录 + 注入文字
  ._on_segment(wav_bytes)         分段回调 → 转录并更新跑马灯
  ._poll_hotkey()                 20ms 轮询热键状态
  .run()                          启动入口（Mutex + mainloop）
```

### 关键流程：一次完整的听写

```
用户按住右Shift → on_press()
  ├─ is_recording = True
  ├─ ball.safe_show_recording(lang)      → 胶囊条出现 "聆聽中..."
  └─ recorder.start(on_segment, seg_secs=3)

每3秒 → Recorder._callback 触发 → _on_segment(wav_bytes)
  ├─ 新线程调 transcriber.transcribe()
  └─ 结果 → ball.safe_append(text)       → 跑马灯更新

用户松开右Shift → on_release()
  ├─ _processing = True                  → 阻止并行处理
  ├─ is_recording = False                → 分段回调停止
  ├─ wav_bytes = recorder.stop()         → 获取完整音频
  └─ process() 线程:
      ├─ transcriber.transcribe(完整音频)  → 最终转录（最准确）
      ├─ inject_text(final_text)           → 剪贴板 Ctrl+V 注入
      ├─ _processing = False               → ★ 立即复位（sleep前）
      ├─ time.sleep(2.5)                   → 显示结果
      └─ _update_tray("ready")
```

### 安全协议

与 Claude 协作时的约定：**所有代码修改和命令执行前，必须先呈现行动方案，获得用户明确同意后才执行。**

---

## 4. 已解决的问题

### Problem 1：重复文字注入
- **原因**：多个 process 线程并行运行
- **修复**：`_processing` 布尔锁，`on_release()` 开头检查，`finally` 块复位

### Problem 2：双球（两个托盘图标/UI窗口）
- **原因**：多个进程同时启动
- **修复**：Windows Named Mutex `Global\SmarType_v6_SingleInstance`，重复启动时弹窗提示

### Problem 3：跑马灯 UI 对齐竞品
- **原因**：原版是圆球居中，竞品是底部胶囊条
- **修复**：CenterBall 重写为 480×56 水平胶囊条，替换模式（不累加），分段转录回调启用

### Problem 4：韩文误识别
- **状态**：用户决定暂不处理，观察实际使用情况

---

## 5. 当前待解决问题（2026-03-21）

### Issue A：语音输入完全没有识别结果

**症状**：按住右 Shift 说话后松开，胶囊条显示处理中，但最终没有文字注入到目标窗口。

**已实施的调试措施**：
1. 全程 `_dbg()` 日志写入 `~/.whisper-dictation/debug.log`
2. `show_error()` 红色 ❌ 视觉反馈
3. `_processing` 在 `inject_text()` 后立即复位（不再等 2.5s sleep）

**排查步骤**：
1. 打开 `C:\Users\gstar\.whisper-dictation\debug.log` 查看日志
2. 关注以下关键行：
   - `wav_bytes is None` → 录音太短（<5帧≈0.3秒）
   - `transcribe EXCEPTION` → API 报错（Key/网络/限额）
   - `transcribe returned: 'EMPTY'` → 语音太轻或无声
   - `BLOCKED by _processing=True` → 上一次还没处理完
   - `process() UNHANDLED EXCEPTION` → 代码层面的错误

**可能的根因（按概率排序）**：
1. Groq API 调用异常（Key 问题、rate limit），但 `print()` 被隐藏的控制台窗口吞掉了
2. `_processing` 被前一次请求锁住（已修复：提前复位）
3. `convert()` 或 `apply_corrections()` 抛出异常

### Issue B：跑马灯文字出现有时间差

**本质**：这不是 bug，是 Groq API 网络延迟（1-3 秒/段）。分段每 3 秒触发一次，加上 API 响应时间，用户感知到约 4-5 秒延迟。可优化但非关键。

---

## 6. 技术细节备忘

### 依赖库

```
pyaudio          录音（stream callback 模式）
keyboard         全局热键监听
pyautogui        模拟键盘操作（Ctrl+V 注入）
pyperclip        剪贴板读写
pystray          系统托盘图标
tkinter          UI（胶囊条）
PIL/Pillow       托盘图标绘制
groq             Groq API 客户端
openai           OpenAI API 客户端（备用）
```

### 配置项（config.json）

```json
{
  "groq_api_key": "gsk_...",     // 主力 API Key
  "api_key": "sk-...",           // OpenAI 备用 Key
  "hotkey": "right shift",       // 触发热键
  "default_lang": "zh-TW",      // 默认语言
  "insert_method": "clipboard",  // 注入方式
  "mic_index": null,             // 麦克风设备索引（null=默认）
  "segment_secs": 3,             // 分段转录间隔（秒）
  "auto_start": false            // 是否开机启动
}
```

### 关键常量

```python
SAMPLE_RATE = 16000    # 16kHz（Whisper 要求）
CHANNELS    = 1        # 单声道
CHUNK       = 1024     # pyaudio 帧大小
FORMAT      = pyaudio.paInt16
```

### 并发模型

```
主线程         → tkinter mainloop（CenterBall UI）
热键轮询线程   → _poll_hotkey()，20ms 间隔
托盘线程       → pystray.Icon.run()
分段转录线程   → 每3秒从 Recorder._callback 中 spawn
最终处理线程   → on_release() 中 spawn process()
Enter学习线程  → _listen_enter() 中 spawn _learn_from_text()
```

### 线程安全

- `_processing` 布尔锁防止并行 process 线程
- `release_lock` (threading.Lock) 防止松键抖动重复触发
- `ball.safe_*()` 方法通过 `root.after(0, ...)` 确保 tkinter 操作在主线程执行
- `is_recording` 标志位控制分段回调是否继续

---

## 7. 测试工具

### test_numbers.py

独立测试脚本，验证 Groq API 连通性和中文数字识别能力。

```bash
# API 连通性测试（静音）
python test_numbers.py

# 真实音频测试
python test_numbers.py --file "录音.mp3"
```

输出：转录全文 + 提取的所有数字 → `test_numbers_result.txt`

### debug.log 实时查看

```powershell
# PowerShell 实时追踪日志
Get-Content "$env:USERPROFILE\.whisper-dictation\debug.log" -Wait -Tail 20
```

---

## 8. 部署流程

1. 修改 `dictation.py` → 写到 `C:\Users\gstar\Desktop\AI_Bridge\dictation.py`
2. 用户手动复制到 `C:\whisper-dictation\dictation.py`（沙盒限制）
3. 如果程序正在运行，先从托盘退出
4. 运行 `start.bat` 或 `python dictation.py` 重新启动

---

## 9. 注意事项

- `dictation.py` 入口处会隐藏控制台窗口（`ShowWindow(..., 0)`），所以所有 `print()` 用户看不到，必须用 `_dbg()` 写文件日志
- 程序需要管理员权限（`ensure_admin()` 会自动 UAC 提权）
- `keyboard` 库在非管理员模式下可能无法捕获全局按键
- `__pycache__` 可能缓存旧字节码，部署新版后如果行为异常，先删除 `__pycache__` 目录
- Groq free tier 限制：whisper-large-v3-turbo 约 20-30 requests/minute
