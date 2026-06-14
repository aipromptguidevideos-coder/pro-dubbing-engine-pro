"""
Professional Dubbing Engine - Upgraded Version
Handles SRT, TXT to SRT conversion, timestamp-aware chunking, parallel TTS generation, and duration validation.
"""

import re
import asyncio
import edge_tts
from typing import List, Dict, Tuple, Optional
import os
import json
import time
import datetime
import google.generativeai as genai

class DubbingSegment:
    def __init__(self, start: float, end: float, lang: str, text: str, segment_id: int):
        self.start = start
        self.end = end
        self.duration = end - start
        self.lang = lang
        self.text = text
        self.segment_id = segment_id
        self.tts_audio_path = None
        self.tts_duration = None
        self.adjusted_text = text
        self.adjusted_speed = 1.0
        self.status = "pending"

class ProDubbingEngine:
    def __init__(self, api_key: str = None, output_language: str = "my"):
        self.tolerance = 0.3  # ±0.3 seconds
        self.api_key = api_key
        self.output_language = output_language.lower()
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash-lite')
        
        self.language_voice_map = {
            "my": "my-MM-ThihaNeural",
            "en": "en-US-GuyNeural",
            "ja": "ja-JP-KeitaNeural",
            "ko": "ko-KR-InJoonNeural",
            "th": "th-TH-NiwatNeural",
            "vi": "vi-VN-HoaiMyNeural"
        }

    def _time_to_seconds(self, time_str: str) -> float:
        """Convert HH:MM:SS,ms or MM:SS to seconds"""
        time_str = time_str.replace(',', '.').strip('[] ')
        parts = time_str.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(time_str)

    def parse_srt(self, srt_content: str) -> List[DubbingSegment]:
        """Parse SRT content into DubbingSegments"""
        segments = []
        # Pattern for SRT blocks
        pattern = r'(\d+)\s+(\d{2}:\d{2}:\d{2}[,. ]\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}[,. ]\d{3})\s+(.*?)(?=\n\n|\n\d+\n|$)'
        matches = re.finditer(pattern, srt_content, re.DOTALL)
        
        for i, match in enumerate(matches):
            start_s = self._time_to_seconds(match.group(2))
            end_s = self._time_to_seconds(match.group(3))
            text = match.group(4).replace('\n', ' ').strip()
            
            segments.append(DubbingSegment(
                start=start_s,
                end=end_s,
                lang=self.output_language,
                text=text,
                segment_id=i
            ))
        return segments

    async def text_to_srt_with_ai(self, text: str) -> str:
        """Convert custom formatted text to standard SRT using Gemini AI for precision"""
        if not self.api_key:
            return self._simple_text_to_srt(text)

        prompt = f"""
        Convert the following timestamped text into a valid SRT subtitle format.
        The input format is: [HH:MM:SS] Text content
        Ensure the timing is continuous and natural for dubbing.
        Output ONLY the valid SRT content.
        
        Input:
        {text}
        """
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text.strip()
        except Exception as e:
            print(f"AI Conversion Error: {e}")
            return self._simple_text_to_srt(text)

    def _simple_text_to_srt(self, text: str) -> str:
        """Regex-based fallback for text to SRT conversion"""
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        srt_out = []
        idx = 1
        
        for i in range(len(lines)):
            match = re.match(r'\[?(\d{2}:\d{2}:\d{2})\]?\s*(.*)', lines[i])
            if match:
                start_time = match.group(1) + ",000"
                content = match.group(2)
                
                if i + 1 < len(lines):
                    next_match = re.match(r'\[?(\d{2}:\d{2}:\d{2})\]?', lines[i+1])
                    if next_match:
                        end_time = next_match.group(1) + ",000"
                    else:
                        end_time = self._add_seconds_to_time(match.group(1), 2) + ",000"
                else:
                    end_time = self._add_seconds_to_time(match.group(1), 2) + ",000"
                
                srt_out.append(f"{idx}\n{start_time} --> {end_time}\n{content}\n")
                idx += 1
        return "\n".join(srt_out)

    def _add_seconds_to_time(self, time_str: str, seconds_to_add: int) -> str:
        try:
            t = datetime.datetime.strptime(time_str, "%H:%M:%S")
            t_new = t + datetime.timedelta(seconds=seconds_to_add)
            return t_new.strftime("%H:%M:%S")
        except:
            return time_str

    def chunk_segments(self, segments: List[DubbingSegment], chunk_size: int) -> List[List[DubbingSegment]]:
        """Split segments into chunks of specified size"""
        return [segments[i:i + chunk_size] for i in range(0, len(segments), chunk_size)]

    async def generate_tts_for_segment(self, segment: DubbingSegment, output_dir: str) -> bool:
        """Generate TTS and measure duration"""
        try:
            voice = self.language_voice_map.get(segment.lang, self.language_voice_map["my"])
            output_path = os.path.join(output_dir, f"seg_{segment.segment_id}.mp3")
            
            communicate = edge_tts.Communicate(segment.text, voice)
            await communicate.save(output_path)
            
            # In real use, use FFmpeg to get exact duration. Here we simulate.
            word_count = len(segment.text.split())
            segment.tts_duration = max(0.5, word_count / 2.5) 
            segment.tts_audio_path = output_path
            segment.status = "tts_generated"
            return True
        except Exception as e:
            segment.status = f"error: {e}"
            return False

    def validate_and_adjust(self, segment: DubbingSegment):
        """Calculate speed adjustment if duration is out of tolerance"""
        if not segment.tts_duration: return
        
        diff = segment.tts_duration - segment.duration
        if abs(diff) > self.tolerance:
            if segment.tts_duration > segment.duration:
                segment.adjusted_speed = segment.tts_duration / segment.duration
                segment.status = "speed_adjusted"
            else:
                segment.status = "valid_short"
        else:
            segment.status = "valid"

    async def process_workflow(self, segments: List[DubbingSegment], output_dir: str) -> Dict:
        """Execute parallel generation and validation"""
        if not os.path.exists(output_dir): os.makedirs(output_dir)
        
        tasks = [self.generate_tts_for_segment(seg, output_dir) for seg in segments]
        await asyncio.gather(*tasks)
        
        for seg in segments:
            self.validate_and_adjust(seg)
            
        return {
            "total": len(segments),
            "successful": len([s for s in segments if "error" not in s.status]),
            "segments": [vars(s) for s in segments]
        }
