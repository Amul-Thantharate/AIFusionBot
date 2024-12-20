import requests
from PIL import Image
from io import BytesIO
import time
import os
from dotenv import load_dotenv
import logging
from groq import Groq
from fpdf import FPDF
from typing import Optional
from together import Together
import base64
from image_generator import AIImageGenerator

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

def generate_image(prompt: str, user_id: str = None) -> tuple[bool, bytes, str, str]:
    """
    Generate an image using Together AI's service with prompt enhancement.
    
    Args:
        prompt (str): The description of the image to generate
        user_id (str): Optional user ID for session management
    
    Returns:
        tuple[bool, bytes, str, str]: (success, image_data, error_message, enhanced_prompt)
    """
    try:
        generator = AIImageGenerator()
        enhanced_prompt = generator.enhance_prompt(prompt)
        if not enhanced_prompt:
            return False, None, "Failed to enhance prompt", None
            
        success, image_data, error_msg = generator.generate_image(enhanced_prompt)
        if not success:
            return False, None, error_msg, None
            
        return True, base64.b64decode(image_data), "", enhanced_prompt
    except Exception as e:
        error_msg = f"Error in image generation: {str(e)}"
        logger.error(error_msg)
        return False, None, error_msg, None

def interactive_chat(text: str, temperature: float = 0.7, max_tokens: int = 1024, 
                    model_type: str = "groq", stream: bool = False, api_key: str = None):
    """
    Chat with the Groq AI model.
    
    Args:
        text (str): The user's message
        temperature (float): Controls randomness in the response
        max_tokens (int): Maximum number of tokens in the response
        model_type (str): The model to use (currently only supports "groq")
        stream (bool): Whether to stream the response
        api_key (str): The Groq API key for authentication
        
    Returns:
        str: The AI's response
    """
    try:
        if not api_key:
            return "Please set your Groq API key using /setgroqkey command"

        client = Groq(api_key=api_key)
        
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant."
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            model="llama3-8b-8192",
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=1,
            stream=stream
        )
        
        if stream:
            # For streaming responses, return a generator
            return (chunk.choices[0].delta.content for chunk in response)
        else:
            # For non-streaming responses, return the complete text
            return response.choices[0].message.content
            
    except Exception as e:
        logger.error(f"Error in chat: {str(e)}")
        if "Invalid API key" in str(e):
            return "Invalid Groq API key. Please check your key and try again."
        return f"Sorry, I encountered an error: {str(e)}"

def save_chat_history(history: list, format: str = "markdown") -> tuple[bool, str, Optional[bytes]]:
    """
    Save chat history in the specified format.
    
    Args:
        history (list): List of chat messages
        format (str): Format to save in ("markdown" or "pdf")
    
    Returns:
        tuple[bool, str, Optional[bytes]]: (success, message, file_bytes)
    """
    try:
        if not history:
            return False, "No chat history to export.", None

        # Convert history to markdown format
        markdown_content = "# O-Chat History\n\n"
        for msg in history:
            role = "🤖 Assistant" if msg["role"] == "assistant" else "👤 You"
            markdown_content += f"### {role}:\n{msg['content']}\n\n"

        if format.lower() == "markdown":
            return True, "Chat history exported as Markdown.", markdown_content.encode('utf-8')
        
        elif format.lower() == "pdf":
            # Create PDF using FPDF
            pdf = FPDF()
            pdf.add_page()
            
            # Set font for title
            pdf.set_font("Arial", "B", 24)
            pdf.cell(0, 20, "O-Chat History", ln=True, align="C")
            pdf.ln(10)
            
            # Set font for content
            pdf.set_font("Arial", size=12)
            
            # Add each message
            for msg in history:
                role = "🤖 Assistant:" if msg["role"] == "assistant" else "👤 You:"
                pdf.set_font("Arial", "B", 14)
                pdf.cell(0, 10, role, ln=True)
                
                pdf.set_font("Arial", size=12)
                # Split content into lines to handle long messages
                lines = msg["content"].split('\n')
                for line in lines:
                    # Split long lines
                    while len(line) > 0:
                        chunk = line[:90]  # Max chars per line
                        line = line[90:]
                        pdf.multi_cell(0, 10, chunk)
                pdf.ln(5)
            
            return True, "Chat history exported as PDF.", pdf.output(dest='S').encode('latin1')
        
        else:
            return False, f"Unsupported format: {format}", None

    except Exception as e:
        logger.error(f"Error saving chat history: {str(e)}")
        return False, f"Error saving chat history: {str(e)}", None

def run_app():
    """Run the main application - starts the Telegram bot"""
    from telegram_bot import run_telegram_bot
    run_telegram_bot()

if __name__ == "__main__":
    run_app()
