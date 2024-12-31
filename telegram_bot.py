#!/usr/bin/env python3
"""
AIFusionBot - Telegram Bot Implementation
Handles all bot commands and interactions
"""

import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime
from io import BytesIO
import time
import base64
from typing import Optional
from dotenv import load_dotenv
from main import interactive_chat, save_chat_history, generate_image
from flask import Flask, request, jsonify
from groq import Groq
import asyncio
import tempfile
from pathlib import Path

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variable for user sessions
user_sessions = {}

# Dictionary of available commands and their descriptions
COMMANDS = {
    'start': 'Start the bot and get welcome message',
    'help': 'Show help message with all commands',
    'chat': 'Start a chat with AI',
    'imagine': 'Generate an image from text description',
    'enhance': 'Enhance your text prompt',
    'settings': 'View and modify bot settings',
    'save': 'Save current chat history',
    'temperature': 'Adjust response creativity (0.1-1.0)',
    'tokens': 'Set maximum response length (100-4096)',
    'uploadenv': 'Upload .env file to configure API keys',
    'describe': 'Analyze and describe an image (reply to an image or provide URL)',
    'transcribe': 'Convert English audio to text (voice or file)',
    'formats': 'Show supported audio formats',
    'clear': 'Clear chat history',
    'export': 'Export chat history as file',
    'voice': 'Send a voice message to transcribe',
    'audio': 'Send an audio file to transcribe',
    'lang': 'Show supported language (English only)'
}

class UserSession:
    def __init__(self):
        self.model_type = "groq"
        self.temperature = 0.5
        self.max_tokens = 1024
        self.chat_history = []
        self.groq_api_key = os.getenv('GROQ_API_KEY')
        self.together_api_key = os.getenv('TOGETHER_API_KEY')
        self.last_enhanced_prompt = None  # Store the last enhanced prompt

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    welcome_message = (
        "👋 *Welcome to AIFusionBot!*\n\n"
        "Created By Amul Thantharate👋 \n\n"
        "I'm your AI assistant with multiple capabilities:\n\n"
        "🤖 *AI Chat*\n"
        "• Use /chat to start a conversation\n"
        "• Adjust settings with /settings\n\n"
        "🎨 *Image Generation*\n"
        "• Create images with /imagine\n"
        "• Enhance prompts with /enhance\n\n"
        "🎵 *Audio Transcription*\n"
        "• Convert English audio to text\n"
        "• Use /transcribe for help\n"
        "• Check formats with /formats\n\n"
        "📷 *Image Analysis*\n"
        "• Analyze images with /describe\n"
        "• Send images directly for analysis\n\n"
        "Use /help to see all available commands!"
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_text = "*Available Commands:*\n\n"
    
    # Group commands by category
    categories = {
        "🤖 Chat Commands": ['chat', 'temperature', 'tokens', 'clear', 'save', 'export'],
        "🎨 Image Commands": ['imagine', 'enhance', 'describe'],
        "🎵 Audio Commands": ['transcribe', 'formats', 'voice', 'audio', 'lang'],
        "⚙️ Settings": ['settings', 'uploadenv'],
        "ℹ️ General": ['start', 'help']
    }
    
    for category, cmd_list in categories.items():
        help_text += f"\n{category}:\n"
        for cmd in cmd_list:
            if cmd in COMMANDS:
                help_text += f"/{cmd} - {COMMANDS[cmd]}\n"
    
    help_text += "\n📝 *Tips:*\n"
    help_text += "• Use /settings to customize bot behavior\n"
    help_text += "• Only English audio is supported for transcription\n"
    help_text += "• Clear audio quality gives better results\n"
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def setgroqkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /setgroqkey command."""
    # Delete the message containing the API key for security
    await update.message.delete()

    if not context.args:
        await update.message.reply_text(
            "Please provide your Groq API key after /setgroqkey\n"
            "Example: `/setgroqkey your_api_key`\n"
            "⚠️ Your message will be deleted immediately for security.",
            parse_mode='Markdown'
        )
        return

    user_id = update.effective_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()

    session = user_sessions[user_id]
    session.groq_api_key = context.args[0]

    await update.message.reply_text(
        "✅ Groq API key set successfully!\n"
        "You can now use all bot features.\n"
        "Try `/chat Hello!` or `/imagine sunset`",
        parse_mode='Markdown'
    )

async def settogetherkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /settogetherkey command."""
    # Delete the message containing the API key for security
    await update.message.delete()

    if not context.args:
        await update.message.reply_text(
            "Please provide your Together API key after /settogetherkey\n"
            "Example: `/settogetherkey your_api_key`\n"
            "⚠️ Your message will be deleted immediately for security.",
            parse_mode='Markdown'
        )
        return

    user_id = update.effective_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()

    session = user_sessions[user_id]
    session.together_api_key = context.args[0]

    # Send confirmation in private message
    await update.message.reply_text(
        "✅ Together API key set successfully!\n"
        "Try generating an image with `/imagine beautiful sunset`",
        parse_mode='Markdown'
    )

async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /chat command."""
    if not context.args:
        await update.message.reply_text("Please provide a message after /chat")
        return

    user_id = update.effective_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()

    session = user_sessions[user_id]
    message = ' '.join(context.args)

    try:
        # Send typing action
        await update.message.chat.send_action(action="typing")

        response = interactive_chat(
            text=message,
            temperature=session.temperature,
            max_tokens=session.max_tokens,
            model_type="groq",
            stream=False,
            api_key=session.groq_api_key
        )

        # Store in chat history
        session.chat_history.append({"role": "user", "content": message})
        session.chat_history.append({"role": "assistant", "content": response})

        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Error in chat_command: {str(e)}")
        await update.message.reply_text(f"Sorry, an error occurred: {str(e)}")

async def imagine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /imagine command for image generation with prompt enhancement."""
    if not update.message:
        return

    if not context.args:
        await update.message.reply_text(
            "Please provide a description after /imagine\n"
            "Example: `/imagine beautiful sunset over mountains, realistic, 4k, detailed`",
            parse_mode='Markdown'
        )
        return

    user_id = update.effective_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()

    session = user_sessions[user_id]
    if not session.together_api_key:
        await update.message.reply_text(
            "⚠️ Please set your Together API key first using:\n"
            "`/settogetherkey your_api_key`",
            parse_mode='Markdown'
        )
        return

    if not session.groq_api_key:
        await update.message.reply_text(
            "⚠️ Please set your Groq API key first using:\n"
            "`/setgroqkey your_api_key`",
            parse_mode='Markdown'
        )
        return

    prompt = ' '.join(context.args)

    # Send a message indicating that prompt enhancement has started
    progress_message = await update.message.reply_text(
        "🎨 Step 1/2: Enhancing your prompt... Please wait."
    )

    try:
        start_time = time.time()
        # Pass the user_id to generate_image
        success, image_bytes, message, enhanced_prompt = generate_image(prompt, user_id=user_id)
        total_time = time.time() - start_time
        
        if success and image_bytes:
            # Update progress message for image generation
            await progress_message.edit_text("🎨 Step 2/2: Generating image from enhanced prompt...")
            
            # Use the returned enhanced prompt
            enhanced_caption = (
                f"🎯 Original prompt:\n'{prompt}'\n\n"
                f"✨ Enhanced prompt:\n'{enhanced_prompt}'\n\n"
                f"⏱️ Total generation time: {total_time:.2f} seconds"
            )
            
            # Send the generated image with the enhanced caption
            await update.message.reply_photo(
                photo=BytesIO(image_bytes),
                caption=enhanced_caption,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Failed to generate image: {message}")
    except Exception as e:
        logger.error(f"Error in image generation: {str(e)}")
        await update.message.reply_text(
            "❌ Sorry, something went wrong while generating the image. Please try again later."
        )
    finally:
        # Delete the progress message
        await progress_message.delete()

async def enhance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /enhance command for text enhancement."""
    if not update.message:
        return

    if not context.args:
        await update.message.reply_text(
            "Please provide text after /enhance\n"
            "Example: `/enhance A boy playing basketball`",
            parse_mode='Markdown'
        )
        return

    user_id = update.effective_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()

    session = user_sessions[user_id]
    if not session.groq_api_key:
        await update.message.reply_text(
            "⚠️ Please set your Groq API key first using:\n"
            "`/setgroqkey your_api_key`",
            parse_mode='Markdown'
        )
        return

    text = ' '.join(context.args)

    # Send a message indicating that enhancement has started
    progress_message = await update.message.reply_text(
        "✍️ Enhancing your text... Please wait."
    )

    try:
        from tone_enhancer import ToneEnhancer
        enhancer = ToneEnhancer()
        
        start_time = time.time()
        success, enhanced_text, error = await enhancer.enhance_text(text)
        total_time = time.time() - start_time
        
        if success and enhanced_text:
            response = (
                f"🎯 Original text:\n'{text}'\n\n"
                f"✨ Enhanced version:\n'{enhanced_text}'\n\n"
                f"⏱️ Enhanced in {total_time:.2f} seconds"
            )
            await update.message.reply_text(response, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Failed to enhance text: {error}")
    except Exception as e:
        logger.error(f"Error in text enhancement: {str(e)}")
        await update.message.reply_text(
            "❌ Sorry, something went wrong while enhancing the text. Please try again later."
        )
    finally:
        # Delete the progress message
        await progress_message.delete()

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /settings command."""
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()

    session = user_sessions[user_id]
    settings_text = (
        f"*Current Settings:*\n"
        f"Model: Groq\n"
        f"Temperature: {session.temperature}\n"
        f"Max Tokens: {session.max_tokens}\n"
        f"Groq API Key: {'✅ Set' if session.groq_api_key else '❌ Not Set'}\n"
        f"Together API Key: {'✅ Set' if session.together_api_key else '❌ Not Set'}\n"
    )
    await update.message.reply_text(settings_text, parse_mode='Markdown')

async def save_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /save command."""
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("No chat history to save.")
        return

    session = user_sessions[user_id]
    if not session.chat_history:
        await update.message.reply_text("No chat history to save.")
        return

    try:
        # Save chat history
        filename = save_chat_history(
            messages=session.chat_history,
            model_type="groq",
            export_format='json'  # You can make this configurable
        )
        await update.message.reply_text(f"Chat history saved to: {filename}")
    except Exception as e:
        logger.error(f"Error saving chat history: {str(e)}")
        await update.message.reply_text(f"Error saving chat history: {str(e)}")

async def temperature_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /temperature command."""
    if not context.args:
        await update.message.reply_text("Please provide a temperature value (0.0-1.0)")
        return

    try:
        temp = float(context.args[0])
        if not 0 <= temp <= 1:
            raise ValueError("Temperature must be between 0 and 1")

        user_id = update.effective_user.id
        if user_id not in user_sessions:
            user_sessions[user_id] = UserSession()

        session = user_sessions[user_id]
        session.temperature = temp
        await update.message.reply_text(f"Temperature set to: {temp}")
    except ValueError as e:
        await update.message.reply_text(str(e))

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /clear command."""
    if not update.message:
        return

    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("No chat history to clear.")
        return

    # Create inline keyboard for confirmation
    keyboard = [
        [
            InlineKeyboardButton("Yes, clear history", callback_data='clear_confirm'),
            InlineKeyboardButton("No, keep history", callback_data='clear_cancel')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ Are you sure you want to clear your chat history?\n"
        "This action cannot be undone.",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()  # Answer the callback query to remove the loading state

    if query.data == 'clear_confirm':
        user_id = update.effective_user.id
        if user_id in user_sessions:
            user_sessions[user_id].chat_history = []
            await query.edit_message_text("🗑️ Chat history cleared successfully!")
    elif query.data == 'clear_cancel':
        await query.edit_message_text("✅ Clear operation cancelled. Your chat history is preserved.")

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /export command."""
    if not update.message:
        return

    # Check if format is specified
    format_type = "markdown"  # default format
    if context.args:
        format_type = context.args[0].lower()
        if format_type not in ["markdown", "pdf"]:
            await update.message.reply_text(
                "❌ Invalid format. Please use:\n"
                "• `/export markdown` - Export as Markdown\n"
                "• `/export pdf` - Export as PDF",
                parse_mode='Markdown'
            )
            return

    user_id = update.effective_user.id
    if user_id not in user_sessions or not user_sessions[user_id].chat_history:
        await update.message.reply_text("No chat history to export.")
        return

    # Send "processing" message
    processing_msg = await update.message.reply_text("📤 Processing your export request...")

    try:
        success, message, file_bytes = save_chat_history(
            user_sessions[user_id].chat_history,
            format_type
        )

        if success and file_bytes:
            # Prepare the file
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            if format_type == "markdown":
                filename = f"chat_history_{current_time}.md"
                caption = "📝 Here's your chat history in Markdown format!"
            else:  # pdf
                filename = f"chat_history_{current_time}.pdf"
                caption = "📄 Here's your chat history in PDF format!"

            # Send the file
            await update.message.reply_document(
                document=BytesIO(file_bytes),
                filename=filename,
                caption=caption
            )
        else:
            await update.message.reply_text(f"❌ Export failed: {message}")

    except Exception as e:
        logger.error(f"Error in export_command: {str(e)}")
        await update.message.reply_text("❌ Sorry, something went wrong during export.")

    finally:
        # Delete the processing message
        await processing_msg.delete()

async def uploadenv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /uploadenv command."""
    if not update.message:
        return

    await update.message.reply_text(
        "Please upload your .env file. It should contain your API keys in this format:\n\n"
        "```\n"
        "GROQ_API_KEY=your_groq_key\n"
        "TOGETHER_API_KEY=your_together_key\n"
        "```\n"
        "⚠️ The file will be processed securely and deleted immediately.",
        parse_mode='Markdown'
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded documents."""
    if not update.message or not update.message.document:
        return

    # Check if the file is a .env file
    if not update.message.document.file_name.endswith('.env'):
        await update.message.reply_text("❌ Please upload a .env file.")
        return

    try:
        # Download the file
        file = await context.bot.get_file(update.message.document.file_id)
        env_content = BytesIO()
        await file.download_to_memory(env_content)
        
        # Process the .env file content
        env_content.seek(0)
        env_text = env_content.read().decode('utf-8')
        
        # Parse the environment variables
        user_id = update.effective_user.id
        if user_id not in user_sessions:
            user_sessions[user_id] = UserSession()
            
        session = user_sessions[user_id]
        success_msg = []
        
        for line in env_text.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            try:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                
                if key == 'GROQ_API_KEY':
                    session.groq_api_key = value
                    success_msg.append("✅ Groq API key set successfully")
                elif key == 'TOGETHER_API_KEY':
                    session.together_api_key = value
                    success_msg.append("✅ Together API key set successfully")
            except ValueError:
                continue
        
        # Delete the message containing the .env file
        await update.message.delete()
        
        if success_msg:
            await update.message.reply_text(
                "🔑 API Keys updated:\n" + "\n".join(success_msg) + "\n\n"
                "Try the following commands:\n"
                "• `/chat Hello!` - Test chat with Groq\n"
                "• `/imagine sunset` - Generate image with Together AI",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ No valid API keys found in the .env file.\n"
                "Make sure your file contains GROQ_API_KEY and/or TOGETHER_API_KEY."
            )
            
    except Exception as e:
        logger.error(f"Error processing .env file: {str(e)}")
        await update.message.reply_text(
            "❌ Error processing the .env file. Please make sure it's properly formatted."
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the telegram bot."""
    logger.error(f"Exception while handling an update: {context.error}")
    if update and isinstance(update, Update) and update.effective_message:
        text = "Sorry, an error occurred while processing your request."
        await update.effective_message.reply_text(text)

async def describe_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /describe command and direct photo messages for image analysis"""
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()
    
    # Get photo from different possible sources
    photo = None
    image_url = None
    
    if update.message.photo:
        # Direct photo message
        photo = update.message.photo[-1]  # Get highest quality photo
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        # Reply to photo with /describe
        photo = update.message.reply_to_message.photo[-1]
    else:
        # Check if URL was provided with /describe command
        args = context.args
        if args:
            image_url = args[0]
        else:
            await update.message.reply_text(
                "Please either:\n"
                "1. Send a photo directly\n"
                "2. Reply to a photo with /describe\n"
                "3. Provide an image URL: `/describe https://example.com/image.jpg`",
                parse_mode='Markdown'
            )
            return
    
    try:
        # Initialize Groq client
        groq = Groq(api_key=user_sessions[user_id].groq_api_key)
        
        # If we have a photo, download it and convert to base64
        if photo:
            await update.message.reply_text("Downloading image...")
            file = await context.bot.get_file(photo.file_id)
            photo_data = await file.download_as_bytearray()
            base64_image = base64.b64encode(photo_data).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{base64_image}"
        
        # Create chat completion with image
        await update.message.reply_text("Analyzing image...")
        chat_completion = groq.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image? Provide a detailed description."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        }
                    ]
                }
            ],
            model="llama-3.2-11b-vision-preview",
            temperature=user_sessions[user_id].temperature,
            max_tokens=user_sessions[user_id].max_tokens
        )
        
        description = chat_completion.choices[0].message.content
        await update.message.reply_text(description)
        
    except Exception as e:
        error_message = str(e)
        if "api_key" in error_message.lower():
            await update.message.reply_text(
                "Please set your Groq API key first using the /setgroqkey command.\n"
                "You can get an API key from https://console.groq.com"
            )
        else:
            await update.message.reply_text(f"Error analyzing image: {error_message}")
            logger.error(f"Error in describe_image: {error_message}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photos sent directly to the bot"""
    await describe_image(update, context)

# Create temp directory for audio files
TEMP_DIR = Path(tempfile.gettempdir()) / "audio_transcribe"
TEMP_DIR.mkdir(exist_ok=True)

# Supported audio formats
SUPPORTED_FORMATS = {'.mp3', '.wav', '.m4a', '.ogg', '.oga', '.opus', '.mp4', '.mpeg', '.mpga', '.webm'}

def get_file_extension(file_name: str) -> str:
    """Get the file extension from the file name."""
    return Path(file_name).suffix.lower()

def is_supported_format(file_name: str) -> bool:
    """Check if the file format is supported."""
    return get_file_extension(file_name) in SUPPORTED_FORMATS

def transcribe_audio(filename, prompt=None):
    """Transcribe English audio file using Groq API."""
    # Initialize the Groq client
    client = Groq()  # Make sure GROQ_API_KEY is set in your environment variables
    
    try:
        # Open the audio file
        with open(filename, "rb") as file:
            # Create a translation of the audio file
            translation = client.audio.translations.create(
                file=(filename, file.read()),  # Required audio file
                model="whisper-large-v3",  # Required model to use for translation
                prompt=prompt or "This is English audio, transcribe accurately",  # Set English context
                response_format="json",  # Optional
                temperature=0.0,  # Optional
                language="en"  # Specify English language
            )
            
            # Check if the detected language is English
            if hasattr(translation, 'language') and translation.language.lower() != 'en':
                logger.warning(f"Non-English audio detected: {translation.language}")
                return "⚠️ Sorry, this bot only transcribes English audio. Detected language: " + translation.language
            
            return translation.text
    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        return None

async def transcribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send information about audio transcription when /transcribe is issued."""
    transcribe_text = """
🎯 *English Audio Transcription Help:*

1️⃣ *Send Voice Message:*
   • Click the microphone icon
   • Record your message in English
   • Send it to me

2️⃣ *Send Audio File:*
   • Select a file from your device
   • Make sure it's in English
   • Make sure it's in a supported format
   • Send it to me

3️⃣ *Supported Formats:*
   • Voice Messages (OGG)
   • Audio Files (MP3, WAV, M4A, OGG, OPUS, MP4, WEBM)

⚠️ *Important Notes:*
   • Only English audio is supported
   • Maximum file size is 20MB
   • Clear audio quality gives better results
    """
    await update.message.reply_text(transcribe_text, parse_mode='Markdown')

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle audio messages."""
    try:
        # Send initial processing message
        processing_msg = await update.message.reply_text(
            "🎵 Receiving your audio...\n⚠️ Note: Only English audio is supported",
            parse_mode='Markdown'
        )

        # Get the audio file
        if update.message.voice:
            file = await update.message.voice.get_file()
            file_name = f"voice_{update.message.from_user.id}.ogg"
        elif update.message.audio:
            file = await update.message.audio.get_file()
            file_name = update.message.audio.file_name
            if not is_supported_format(file_name):
                await processing_msg.edit_text(
                    f"❌ Sorry, the format {get_file_extension(file_name)} is not supported.\n"
                    "Use /formats to see supported formats."
                )
                return
        else:
            await processing_msg.edit_text("❌ Please send a voice message or audio file.")
            return

        # Create unique file path
        file_path = TEMP_DIR / f"{update.message.from_user.id}_{file_name}"
        
        # Download the file
        await file.download_to_drive(str(file_path))
        
        # Update processing message
        await processing_msg.edit_text("🔄 Processing your audio... Please wait.")

        # Transcribe the audio
        transcription = transcribe_audio(str(file_path))

        if transcription:
            if transcription.startswith("⚠️ Sorry, this bot only transcribes English audio"):
                # If non-English audio was detected
                await processing_msg.edit_text(transcription)
            else:
                # Split long messages if needed (Telegram has a 4096 character limit)
                max_length = 4000
                messages = [transcription[i:i+max_length] for i in range(0, len(transcription), max_length)]
                
                # Send transcription
                await processing_msg.edit_text("✅ Transcription completed!")
                for i, msg in enumerate(messages, 1):
                    if len(messages) > 1:
                        header = f"*Part {i}/{len(messages)}:*\n\n"
                    else:
                        header = "*Transcription:*\n\n"
                    await update.message.reply_text(f"{header}{msg}", parse_mode='Markdown')
        else:
            await processing_msg.edit_text(
                "❌ Sorry, I couldn't transcribe the audio. Please try again with clear English audio."
            )

        # Clean up the temporary file
        if file_path.exists():
            file_path.unlink()

    except Exception as e:
        logger.error(f"Error handling audio: {str(e)}")
        await update.message.reply_text(
            "❌ Sorry, something went wrong. Please try again with clear English audio."
        )

async def formats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show supported audio formats."""
    formats_text = (
        "📝 *Supported Audio Formats:*\n\n"
        "• MP3 (.mp3)\n"
        "• WAV (.wav)\n"
        "• M4A (.m4a)\n"
        "• OGG (.ogg, .oga)\n"
        "• OPUS (.opus)\n"
        "• MP4 (.mp4)\n"
        "• MPEG (.mpeg, .mpga)\n"
        "• WEBM (.webm)\n\n"
        "✨ Just send me any audio file in these formats!"
    )
    await update.message.reply_text(formats_text, parse_mode='Markdown')

async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show supported language information."""
    lang_text = (
        "🌐 *Supported Language for Audio Transcription*\n\n"
        "Currently, this bot only supports:\n"
        "• English (US)\n"
        "• English (UK)\n"
        "• English (International)\n\n"
        "⚠️ *Important Notes:*\n"
        "• Clear pronunciation helps accuracy\n"
        "• Minimal background noise preferred\n"
        "• Good audio quality recommended\n\n"
        "🎯 *Best Practices:*\n"
        "• Speak clearly and at normal speed\n"
        "• Avoid heavy accents if possible\n"
        "• Use good quality recording equipment\n"
        "• Record in a quiet environment\n\n"
        "Use /transcribe to start transcribing!"
    )
    await update.message.reply_text(lang_text, parse_mode='Markdown')

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show voice message instructions."""
    voice_text = (
        "🎤 *Voice Message Instructions*\n\n"
        "To send a voice message:\n"
        "1. Click the microphone icon (🎤)\n"
        "2. Hold to record your message\n"
        "3. Speak clearly in English\n"
        "4. Release to send\n\n"
        "⚠️ *Tips for Best Results:*\n"
        "• Find a quiet location\n"
        "• Speak at a normal pace\n"
        "• Hold phone close to mouth\n"
        "• Avoid background noise\n\n"
        "Maximum duration: 20 minutes"
    )
    await update.message.reply_text(voice_text, parse_mode='Markdown')

async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show audio file instructions."""
    audio_text = (
        "🎵 *Audio File Instructions*\n\n"
        "To send an audio file:\n"
        "1. Click the attachment icon (📎)\n"
        "2. Select 'Audio'\n"
        "3. Choose your English audio file\n"
        "4. Send the file\n\n"
        "📝 *Requirements:*\n"
        "• English audio only\n"
        "• Maximum size: 20MB\n"
        "• Supported formats: use /formats\n\n"
        "⚠️ *Tips:*\n"
        "• High-quality audio works best\n"
        "• Clear speech is important\n"
        "• Minimal background noise\n"
        "• Single speaker preferred"
    )
    await update.message.reply_text(audio_text, parse_mode='Markdown')

def setup_bot(token: str) -> Application:
    """Initialize and configure the AIFusionBot bot"""
    try:
        # Create the Application
        app = Application.builder().token(token).build()
        
        # Add command handlers
        app.add_handler(CommandHandler('start', start_command))
        app.add_handler(CommandHandler('help', help_command))
        app.add_handler(CommandHandler('setgroqkey', setgroqkey_command))
        app.add_handler(CommandHandler('settogetherkey', settogetherkey_command))
        app.add_handler(CommandHandler('chat', chat_command))
        app.add_handler(CommandHandler('imagine', imagine_command))
        app.add_handler(CommandHandler('enhance', enhance_command))
        app.add_handler(CommandHandler('settings', settings_command))
        app.add_handler(CommandHandler('save', save_command))
        app.add_handler(CommandHandler('temperature', temperature_command))
        app.add_handler(CommandHandler('clear', clear_command))
        app.add_handler(CommandHandler('export', export_command))
        app.add_handler(CommandHandler('uploadenv', uploadenv_command))
        app.add_handler(CommandHandler('describe', describe_image))
        app.add_handler(CommandHandler('transcribe', transcribe_command))
        app.add_handler(CommandHandler('formats', formats_command))
        app.add_handler(CommandHandler('lang', lang_command))
        app.add_handler(CommandHandler('voice', voice_command))
        app.add_handler(CommandHandler('audio', audio_command))
        
        # Add message handlers
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_command))
        
        # Add callback query handler
        app.add_handler(CallbackQueryHandler(button_callback))
        
        # Add error handler
        app.add_error_handler(error_handler)
        
        logger.info("Bot setup completed successfully")
        return app
        
    except Exception as e:
        logger.error(f"Error setting up bot: {str(e)}")
        raise

def run_telegram_bot():
    """Main function to run the Telegram bot"""
    try:
        # Load environment variables
        load_dotenv()
        
        # Get bot token from environment
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
        
        # Setup and run the bot
        app = setup_bot(token)
        logger.info("Starting bot in polling mode...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Failed to start bot: {str(e)}")
        raise

if __name__ == "__main__":
    run_telegram_bot()