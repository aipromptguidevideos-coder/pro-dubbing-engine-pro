import streamlit as st
import os
import asyncio
import json
from pro_dubbing_engine import ProDubbingEngine
import tempfile

st.set_page_config(page_title="Pro Dubbing Engine Upgrade", page_icon="🎙️", layout="wide")

st.title("🎙️ Pro Dubbing Engine - Advanced Upgrade")
st.markdown("---")

# Sidebar for settings
with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("Gemini API Key (Optional)", type="password")
    output_lang = st.selectbox("Output Language", ["my", "en", "ja", "ko", "th", "vi"], index=0)
    chunk_size = st.slider("Chunk Size (segments per chunk)", 1, 50, 10)
    st.info("Upgrade: Now supports SRT and TXT file uploads!")

# Initialize engine
engine = ProDubbingEngine(api_key=api_key if api_key else None, output_language=output_lang)

tab1, tab2 = st.tabs(["📤 Input & Process", "📊 Analytics"])

with tab1:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("1. Provide Input")
        input_type = st.radio("Select Input Type:", ["Text Input", "File Upload (.srt / .txt)"])
        
        script_content = ""
        if input_type == "Text Input":
            script_content = st.text_area("Paste your script with timestamps here:", height=300, 
                                        placeholder="[00:00:00] Hello...\n[00:00:02] Welcome...")
        else:
            uploaded_file = st.file_uploader("Upload .srt or .txt file", type=["srt", "txt"])
            if uploaded_file:
                script_content = uploaded_file.read().decode("utf-8")
                st.success(f"File '{uploaded_file.name}' loaded!")

    with col2:
        st.subheader("2. Process & Dub")
        if st.button("🚀 Start Professional Dubbing", use_container_width=True):
            if not script_content:
                st.warning("Please provide some script content first.")
            else:
                with st.spinner("Processing..."):
                    # Step 1: Handle TXT to SRT if needed
                    if "[00:" in script_content and "-->" not in script_content:
                        st.info("Converting custom text format to SRT...")
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        srt_content = loop.run_until_complete(engine.text_to_srt_with_ai(script_content))
                    else:
                        srt_content = script_content
                    
                    # Step 2: Parse SRT
                    segments = engine.parse_srt(srt_content)
                    if not segments:
                        st.error("No valid segments found. Please check your format.")
                    else:
                        st.success(f"Found {len(segments)} segments!")
                        
                        # Step 3: Chunking
                        chunks = engine.chunk_segments(segments, chunk_size)
                        st.info(f"Split into {len(chunks)} chunks for parallel processing.")
                        
                        # Step 4: Process Workflow
                        with tempfile.TemporaryDirectory() as tmp_dir:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            results = loop.run_until_complete(engine.process_workflow(segments, tmp_dir))
                            
                            st.session_state.results = results
                            st.success("✅ Dubbing process completed!")

    if "results" in st.session_state:
        st.divider()
        st.subheader("🎧 Processing Results")
        res = st.session_state.results
        st.write(f"Total Segments: {res['total']} | Successful: {res['successful']}")
        
        with st.expander("View Detailed Segment Status"):
            st.table(res['segments'])

with tab2:
    st.subheader("📈 Technical Analytics")
    if "results" in st.session_state:
        res = st.session_state.results
        # Simple stats
        avg_speed = sum([s['adjusted_speed'] for s in res['segments']]) / len(res['segments'])
        st.metric("Average Speed Adjustment", f"{avg_speed:.2f}x")
        
        # Timeline view
        st.write("**Segment Timeline**")
        for s in res['segments']:
            status_color = "🟢" if s['status'] == 'valid' else "🟡" if 'adjusted' in s['status'] else "🔴"
            st.text(f"{status_color} [{s['start']:.2f}s - {s['end']:.2f}s] Speed: {s['adjusted_speed']:.2f}x | {s['text'][:50]}...")
    else:
        st.info("Run the dubbing process to see analytics.")
