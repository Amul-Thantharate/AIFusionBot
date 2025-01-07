import os
import time
import logging
import google.generativeai as genai
from dotenv import load_dotenv
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi
from constants import (
    MEDIA_FOLDER,
    SUMMARY_PROMPT,
    VIDEO_ANALYSIS_PROMPT,
    ERROR_MESSAGES
)

def initialize():
    """Initialize the video insights module."""
    if not os.path.exists(MEDIA_FOLDER):
        os.makedirs(MEDIA_FOLDER)
    load_dotenv()
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError("❌ API_KEY not found in .env file")
    genai.configure(api_key=api_key)

def get_insights(video_path):
    """Get insights from a video using Gemini Vision."""
    try:
        logging.info(f"🎥 Processing video: {video_path}")
        
        # Initialize Gemini model with the newer 1.5 Flash version
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Read video frames
        import cv2
        cap = cv2.VideoCapture(video_path)
        frames = []
        frame_interval = 30  # Capture one frame every second (assuming 30fps)
        frame_count = 0
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            if frame_count % frame_interval == 0:
                # Convert frame to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # Convert to format expected by Gemini
                _, buffer = cv2.imencode('.jpg', frame_rgb)
                frames.append({
                    "mime_type": "image/jpeg",
                    "data": buffer.tobytes()
                })
                
                # Limit to max 10 frames to avoid token limits
                if len(frames) >= 10:
                    break
                    
            frame_count += 1
            
        cap.release()
        
        if not frames:
            raise ValueError("No frames could be extracted from the video")
            
        # Generate content with frames
        response = model.generate_content(
            contents=[VIDEO_ANALYSIS_PROMPT] + frames,
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 2048
            }
        )
        
        return response.text
        
    except Exception as e:
        logging.error(f"❌ Error in get_insights: {str(e)}")
        raise

def save_video_file(file_data, filename):
    file_path = os.path.join(MEDIA_FOLDER, filename)
    with open(file_path, 'wb') as f:
        f.write(file_data)
    return file_path

def extract_transcript_details(youtube_video_url):
    """Extract transcript from YouTube video and handle cases where transcripts are unavailable."""
    try:
        # Extract video ID
        if "youtube.com/watch?v=" in youtube_video_url:
            video_id = youtube_video_url.split("watch?v=")[1].split("&")[0]
        elif "youtu.be/" in youtube_video_url:
            video_id = youtube_video_url.split("youtu.be/")[1].split("?")[0]
        else:
            raise ValueError("❌ Invalid YouTube URL format")

        try:
            # Try to get manual captions first
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        except Exception:
            try:
                # If manual captions fail, try auto-generated ones
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en-US'])
            except Exception:
                # If both fail, try to get any available transcript
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript = transcript_list.find_transcript(['en'])
                transcript_list = transcript.fetch()

        transcript = " ".join([item["text"] for item in transcript_list])
        return transcript
    except Exception as e:
        logging.error(f"❌ Error extracting transcript: {str(e)}")
        raise ValueError("❌ Could not extract video transcript. The video might not have captions available.")

def generate_gemini_content(transcript_text, prompt):
    """Generate content using Gemini Pro model."""
    try:
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt + transcript_text)
        return response.text
    except Exception as e:
        logging.error(f"❌ Error generating content: {str(e)}")
        raise

def process_youtube_video(youtube_url):
    """Process a YouTube video and return its summary."""
    try:
        transcript = extract_transcript_details(youtube_url)
        if transcript:
            summary = generate_gemini_content(transcript, SUMMARY_PROMPT)
            return "📝 Video Summary:\n\n" + summary
        return "❌ Could not generate summary. Please try another video."
    except Exception as e:
        logging.error(f"❌ Error processing YouTube video: {str(e)}")
        raise

def cleanup_video_file(file_path):
    """Clean up temporary video file."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"🗑️ Cleaned up file: {file_path}")
    except Exception as e:
        logging.error(f"❌ Error cleaning up file {file_path}: {str(e)}")
