import queue
import collections
import sys
import wave
import io
import numpy as np
import sounddevice as sd
import webrtcvad

import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient 

class VoiceTranscriber:
    def __init__(self, sample_rate=16000, block_duration_ms=30):
        """
        初始化音频捕获和VAD检测。
        webrtcvad 支持的采样率为 8000, 16000, 32000, 48000
        支持的帧长为 10, 20, 30 毫秒
        """
        self.sample_rate = sample_rate
        self.block_duration_ms = block_duration_ms
        self.block_size = int(sample_rate * block_duration_ms / 1000)
        
        # vad_mode 取值 0~3, 数字越大越严格地过滤噪音，3 对安静环境最好
        self.vad = webrtcvad.Vad(3)
        self.audio_queue = queue.Queue()

    def _audio_callback(self, indata, frames, time, status):
        """sounddevice 的回调函数，将捕获到的音频块放入队列中"""
        if status:
            print(f"音频捕获状态警告: {status}", file=sys.stderr)
        self.audio_queue.put(bytes(indata))

    def capture_voice(self, silence_duration=1.5, pre_speech_ms=300):
        """
        捕获一段语音，直到检测到持续 silence_duration 秒的静音为止。
        pre_speech_ms: 在检测到语音前保留的音频前缀长度，防止开头截字。
        返回包含16-bit PCM音频的 bytes 数据。
        """
        # 保存说话前的短时间音频数据，避免说话刚开始的声音因为反应慢被截断
        pre_speech_frames_len = int(pre_speech_ms / self.block_duration_ms)
        pre_speech_buffer = collections.deque(maxlen=pre_speech_frames_len)
        
        frames = []
        is_speech = False
        silence_frames = 0
        silence_limit = int(silence_duration * 1000 / self.block_duration_ms)
        
        print("等待语音输入...")
        
        with sd.RawInputStream(samplerate=self.sample_rate, 
                               blocksize=self.block_size, 
                               channels=1, 
                               dtype='int16',
                               callback=self._audio_callback):
            while True:
                frame = self.audio_queue.get()
                
                # 必须确保帧长正确才能交给webrtcvad处理（16000Hz下30ms为480个样本点，双字节即960字节）
                if len(frame) != self.block_size * 2:
                    continue
                
                # 判断当前帧是否包含语音
                active = self.vad.is_speech(frame, self.sample_rate)
                
                if not is_speech:
                    if active:
                        # 检测到语音开始
                        is_speech = True
                        print("检测到声音，开始录制...")
                        frames.extend(pre_speech_buffer)
                        frames.append(frame)
                    else:
                        # 还没人说话，缓存到预热区以保留声音前缀
                        pre_speech_buffer.append(frame)
                else:
                    frames.append(frame)
                    if active:
                        # 有语音，重置静音帧计数
                        silence_frames = 0
                    else:
                        # 没有语音，累加静音帧
                        silence_frames += 1
                        
                    # 如果持续一段时间没有检测到语音，则判断这句话结束，停止收集
                    if silence_frames > silence_limit:
                        print("检测到句子结尾，停止录制。")
                        break
                        
        # 将捕获的多个帧拼接到一起
        audio_data = b''.join(frames)
        return audio_data

    def transcribe_local_whisper(self, audio_data, model_size="medium"):
        """
        使用本地的 faster-whisper 库将音频转为文本，使用 GPU 加速
        前提需要安装： pip install faster-whisper
        """
        import os
        
        # [针对国内网络的优化]：强制 HuggingFace 使用国内镜像源，极大加快下载速度并防止卡死
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        
        from faster_whisper.transcribe import WhisperModel
        
        # 1. 自动将模型保存在当前脚本同级的 models 文件夹下
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_dir = os.path.join(current_dir, "models")
        os.makedirs(model_dir, exist_ok=True)
        
        print(f"载入本地 faster-whisper ('{model_size}') 模型中 (保存在 {model_dir})...")
        
        # 2. 设置使用 GPU (device="cuda") 以及半精度计算 (compute_type="float16")
        model = WhisperModel(
            model_size, 
            device="cuda", 
            compute_type="float16", 
            download_root=model_dir
        )
        
        # 3. 准备音频数组 (依旧是16kHz float32)
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        
        print("正在进行 faster-whisper GPU 音频转写...")
        
        # 4. 执行转写。faster-whisper 返回的是一个生成器 (generator)
        segments, info = model.transcribe(audio_np, beam_size=5, language="zh")
        
        # 遍历生成器，将所有段落拼接为一个完整字符串
        result_text = "".join([segment.text for segment in segments])
        return result_text



if __name__ == "__main__":
    transcriber = VoiceTranscriber()
    
    # 1. 自动捕获音频
    audio_pcm_data = transcriber.capture_voice(silence_duration=1.5)
    
    if len(audio_pcm_data) < transcriber.block_size * 2 * 10:
        print("未录制到有效音频数据。")
        sys.exit(0)
        
    print(f"成功收集到语音数据 ({len(audio_pcm_data)} 字节)")
    
    # 2. 调用本地Whisper做转录
    print("----- 本地转写测试 -----")
    try:
        text_local = transcriber.transcribe_local_whisper(audio_pcm_data, model_size="medium")
        print("\n[本地识别文本结果]:", text_local)
    except ImportError:
        print("未安装模块，请先运行: pip install faster-whisper")
        
    
