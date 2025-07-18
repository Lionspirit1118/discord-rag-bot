#!/usr/bin/env python3
"""
Discord Bot for Evidence Collection System with OpenAI Integration

This bot combines the functionality of the Flask web service and Google Apps Script
into a unified Discord bot that can:
- Handle evidence collection and processing
- Integrate with Google Sheets and Docs
- Provide OpenAI GPT-4o-mini powered Q&A
- Deploy on Render as a persistent bot

Required environment variables:
- DISCORD_TOKEN: Discord bot token
- OPENAI_API_KEY: OpenAI API key
- GOOGLE_APPLICATION_CREDENTIALS: Google service account credentials (JSON string)
- SPREADSHEET_ID: Google Sheets ID for evidence collection
- DOCUMENT_ID: Google Docs ID for evidence compilation
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

import discord
from discord.ext import commands
from openai import OpenAI
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot configuration
intents = discord.Intents.default()
# Only enable message content intent if needed - this requires enabling in Discord Developer Portal
intents.message_content = True  # Comment out to avoid privileged intent error
bot = commands.Bot(command_prefix='!', intents=intents)

# OpenAI configuration
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


class EvidenceCollectionBot:
    """
    Discord Bot for Evidence Collection System
    Handles evidence processing, Google API integration, and OpenAI Q&A
    """
    
    def __init__(self):
        """Initialize the bot with environment variables and API clients"""
        self.spreadsheet_id = os.getenv('SPREADSHEET_ID')
        self.document_id = os.getenv('DOCUMENT_ID')
        
        # Google API scopes
        self.scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/cloud-translation'
        ]
        
        # Initialize Google API clients
        self._initialize_google_apis()
        
        # Data storage for structured entries
        self.structured_data = []
        
        logger.info("EvidenceCollectionBot initialized successfully")
    
    def _initialize_google_apis(self):
        """Initialize Google API clients using service account credentials"""
        try:
            # For Render deployment, credentials can be set as environment variable
            credentials_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            
            if credentials_json:
                try:
                    # Parse JSON string from environment variable
                    credentials_info = json.loads(credentials_json)
                    
                    # Validate required fields
                    required_fields = ['client_email', 'token_uri', 'private_key', 'project_id']
                    missing_fields = [field for field in required_fields if field not in credentials_info]
                    
                    if missing_fields:
                        logger.warning(f"Google credentials missing required fields: {missing_fields}")
                        logger.warning("Google API features will be disabled.")
                        self.credentials = None
                        return
                    
                    self.credentials = Credentials.from_service_account_info(
                        credentials_info, scopes=self.scopes
                    )
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in GOOGLE_APPLICATION_CREDENTIALS: {e}")
                    logger.warning("Google API features will be disabled.")
                    self.credentials = None
                    return
            else:
                # Fallback to file-based credentials for local development
                credentials_path = 'credentials.json'
                if os.path.exists(credentials_path):
                    self.credentials = Credentials.from_service_account_file(
                        credentials_path, scopes=self.scopes
                    )
                else:
                    logger.warning("No Google credentials found. Google API features will be disabled.")
                    self.credentials = None
                    return
            
            # Initialize Google API services
            self.sheets_client = gspread.authorize(self.credentials)
            self.docs_service = build('docs', 'v1', credentials=self.credentials)
            self.translate_service = build('translate', 'v2', credentials=self.credentials)
            
            logger.info("Google APIs initialized successfully")
            
        except Exception as error:
            logger.warning(f"Failed to initialize Google APIs: {error}")
            logger.warning("Google API features will be disabled.")
            self.credentials = None
    
    def translate_text(self, text: str, source_lang: str = 'ja', target_lang: str = 'en') -> str:
        """
        Translate text using Google Translate API
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            
        Returns:
            Translated text or original text if translation fails
        """
        if not text or text.strip() == '' or not self.credentials:
            return text
        
        try:
            result = self.translate_service.translations().list(
                source=source_lang,
                target=target_lang,
                q=[text]
            ).execute()
            
            if 'translations' in result and result['translations']:
                return result['translations'][0]['translatedText']
            else:
                return text
                
        except Exception as error:
            logger.error(f'Translation error: {error}')
            return text
    
    async def get_latest_submissions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the latest submissions from Google Sheets
        
        Args:
            limit: Maximum number of submissions to return
            
        Returns:
            List of submission dictionaries
        """
        if not self.credentials:
            return []
            
        try:
            spreadsheet = self.sheets_client.open_by_key(self.spreadsheet_id)
            worksheet = spreadsheet.worksheet('Responses')
            
            # Get all rows
            all_rows = worksheet.get_all_values()
            
            if len(all_rows) <= 1:
                return []
            
            # Get the latest submissions
            latest_rows = all_rows[-limit:] if len(all_rows) > limit else all_rows[1:]
            
            submissions = []
            for i, row_data in enumerate(latest_rows, start=len(all_rows) - len(latest_rows) + 1):
                submission = self.extract_submission_data(row_data)
                if submission:
                    submission['row_number'] = i
                    submissions.append(submission)
            
            return submissions
            
        except Exception as error:
            logger.error(f'Error getting latest submissions: {error}')
            return []
    
    def extract_submission_data(self, row_data: List[str]) -> Optional[Dict[str, Any]]:
        """
        Extract and structure form submission data
        
        Args:
            row_data: Raw row data from spreadsheet
            
        Returns:
            Structured submission data dictionary
        """
        try:
            if len(row_data) < 11:
                logger.warning(f'Insufficient data in row: {len(row_data)} columns')
                return None
            
            # Parse tags
            aff_tags = row_data[3].split(', ') if row_data[3] else []
            neg_tags = row_data[4].split(', ') if row_data[4] else []
            
            submission_data = {
                'timestamp': row_data[0],
                'submitter': row_data[1],
                'title': row_data[2],
                'aff_tags': aff_tags,
                'neg_tags': neg_tags,
                'source_url': row_data[5],
                'update_date': row_data[6],
                'eng_source': row_data[7],
                'quote': row_data[8],
                'attachment': row_data[9],
                'remark': row_data[10]
            }
            
            return submission_data
            
        except Exception as error:
            logger.error(f'Error extracting submission data: {error}')
            return None
    
    async def ask_gpt(self, question: str, context: str = "") -> str:
        """
        Ask OpenAI GPT-4o-mini a question with optional context
        
        Args:
            question: The question to ask
            context: Optional context to provide
            
        Returns:
            GPT response or error message
        """
        try:
            # Prepare the prompt
            system_prompt = """You are a helpful assistant for an evidence collection system. 
            You help users understand, analyze, and work with collected evidence data. 
            Provide clear, concise, and helpful responses."""
            
            user_prompt = question
            if context:
                user_prompt = f"Context: {context}\n\nQuestion: {question}"
            
            # Call OpenAI API
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Updated to GPT-4.1 mini
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as error:
            logger.error(f'OpenAI API error: {error}')
            return f"Sorry, I encountered an error while processing your question: {str(error)}"
    
    async def process_evidence_notification(self, channel, entry_number: int, data: Dict[str, Any]):
        """
        Process and send evidence notification to Discord channel
        
        Args:
            channel: Discord channel to send notification
            entry_number: Entry number for formatting
            data: Structured submission data
        """
        try:
            # Translate the quote
            original_quote = data['quote']
            translated_quote = self.translate_text(original_quote, 'ja', 'en')
            
            # Format tags
            tags_text = ""
            if data['aff_tags'] and data['aff_tags'][0]:
                tags_text += "[AFF] "
                for tag in data['aff_tags']:
                    tags_text += f"#{tag} "
            
            if data['aff_tags'] and data['aff_tags'][0] and data['neg_tags'] and data['neg_tags'][0]:
                tags_text += "\n"
            
            if data['neg_tags'] and data['neg_tags'][0]:
                tags_text += "[NEG] "
                for tag in data['neg_tags']:
                    tags_text += f"#{tag} "
            
            # Create Discord embed
            embed = discord.Embed(
                title=f"{entry_number}. {data['title']}",
                description=f"**Submitter:** {data['submitter']}",
                color=0x00ff00,
                timestamp=datetime.now()
            )
            
            if tags_text:
                embed.add_field(name="Tags", value=tags_text, inline=False)
            
            # Add original quote
            if original_quote:
                embed.add_field(
                    name="Original Quote (Japanese)",
                    value=f"```{original_quote[:1000]}{'...' if len(original_quote) > 1000 else ''}```",
                    inline=False
                )
            
            # Add translated quote
            if translated_quote and translated_quote != original_quote:
                embed.add_field(
                    name="English Translation",
                    value=f"```{translated_quote[:1000]}{'...' if len(translated_quote) > 1000 else ''}```",
                    inline=False
                )
            
            # Add source information
            embed.add_field(name="Source", value=data['eng_source'], inline=True)
            embed.add_field(name="Update Date", value=data['update_date'], inline=True)
            
            if data['source_url']:
                embed.add_field(name="URL", value=data['source_url'], inline=False)
            
            # Add attachments and remarks
            if data['attachment']:
                embed.add_field(name="Attachments", value=data['attachment'], inline=False)
            
            if data['remark']:
                embed.add_field(name="Remarks", value=f"※{data['remark']}", inline=False)
            
            await channel.send(embed=embed)
            
        except Exception as error:
            logger.error(f'Error sending evidence notification: {error}')
            await channel.send(f"Error processing evidence notification: {str(error)}")


# Initialize the evidence collection bot
evidence_bot = EvidenceCollectionBot()


# Bot event handlers
@bot.event
async def on_ready():
    """Called when the bot is ready"""
    logger.info(f'{bot.user} has connected to Discord!')
    print(f'{bot.user} has connected to Discord!')


@bot.event
async def on_message(message):
    """Handle incoming messages"""
    # Don't respond to own messages
    if message.author == bot.user:
        return
    
    # Check if message is a question (not a command)
    if not message.content.startswith('!') and '?' in message.content:
        # Use OpenAI to answer the question
        response = await evidence_bot.ask_gpt(message.content)
        await message.channel.send(response)
    
    # Process commands
    await bot.process_commands(message)


# Bot commands
@bot.command(name='ping')
async def ping(ctx):
    """
    Simple ping command to test bot connectivity
    Usage: !ping
    """
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")


@bot.command(name='ask')
async def ask_question(ctx, *, question):
    """
    Ask a question to OpenAI GPT-3.5
    Usage: !ask <your question>
    """
    async with ctx.typing():
        response = await evidence_bot.ask_gpt(question)
        await ctx.send(response)


@bot.command(name='latest')
async def get_latest_evidence(ctx, limit: int = 5):
    """
    Get latest evidence submissions from Google Sheets
    Usage: !latest [number] (default: 5)
    """
    if limit > 10:
        limit = 10
    
    async with ctx.typing():
        submissions = await evidence_bot.get_latest_submissions(limit)
        
        if not submissions:
            await ctx.send("No submissions found or Google Sheets access not configured.")
            return
        
        for submission in submissions:
            await evidence_bot.process_evidence_notification(
                ctx.channel, 
                submission.get('row_number', 1), 
                submission
            )


@bot.command(name='search')
async def search_evidence(ctx, *, query):
    """
    Search through evidence data using OpenAI
    Usage: !search <search query>
    """
    async with ctx.typing():
        # Get recent submissions for context
        submissions = await evidence_bot.get_latest_submissions(20)
        
        if not submissions:
            await ctx.send("No data available for search.")
            return
        
        # Prepare context from submissions
        context = "Recent evidence submissions:\n"
        for sub in submissions[:10]:  # Limit context to avoid token limits
            context += f"- {sub['title']} by {sub['submitter']}: {sub['quote'][:200]}...\n"
        
        # Ask GPT to search/analyze
        search_prompt = f"Based on the evidence data, please help with this search query: {query}"
        response = await evidence_bot.ask_gpt(search_prompt, context)
        await ctx.send(response)


@bot.command(name='analyze')
async def analyze_evidence(ctx, *, prompt):
    """
    Analyze evidence data using OpenAI
    Usage: !analyze <analysis prompt>
    """
    async with ctx.typing():
        # Get recent submissions for analysis
        submissions = await evidence_bot.get_latest_submissions(10)
        
        if not submissions:
            await ctx.send("No data available for analysis.")
            return
        
        # Prepare context from submissions
        context = "Evidence data for analysis:\n"
        for sub in submissions:
            context += f"Title: {sub['title']}\n"
            context += f"Submitter: {sub['submitter']}\n"
            context += f"Quote: {sub['quote'][:300]}...\n"
            context += f"Tags: AFF={sub['aff_tags']}, NEG={sub['neg_tags']}\n\n"
        
        # Ask GPT to analyze
        analysis_prompt = f"Please analyze this evidence data: {prompt}"
        response = await evidence_bot.ask_gpt(analysis_prompt, context)
        await ctx.send(response)


@bot.command(name='help_bot')
async def help_command(ctx):
    """
    Show available bot commands
    Usage: !help_bot
    """
    embed = discord.Embed(
        title="Evidence Collection Bot - Commands",
        description="Available commands for the Evidence Collection Bot",
        color=0x0099ff
    )
    
    embed.add_field(
        name="!ping",
        value="Test bot connectivity and latency",
        inline=False
    )
    
    embed.add_field(
        name="!ask <question>",
        value="Ask a question to OpenAI GPT-4o-mini",
        inline=False
    )
    
    embed.add_field(
        name="!latest [number]",
        value="Get latest evidence submissions (default: 5, max: 10)",
        inline=False
    )
    
    embed.add_field(
        name="!search <query>",
        value="Search through evidence data using AI",
        inline=False
    )
    
    embed.add_field(
        name="!analyze <prompt>",
        value="Analyze evidence data using AI",
        inline=False
    )
    
    embed.add_field(
        name="Natural Questions",
        value="Ask questions naturally in chat (with '?') and I'll respond using OpenAI!",
        inline=False
    )
    
    await ctx.send(embed=embed)


@bot.command(name='status')
async def bot_status(ctx):
    """
    Show bot status and configuration
    Usage: !status
    """
    embed = discord.Embed(
        title="Bot Status",
        color=0x00ff00
    )
    
    embed.add_field(
        name="Discord Bot",
        value="✅ Connected",
        inline=True
    )
    
    embed.add_field(
        name="OpenAI API",
        value="✅ Configured" if openai_client.api_key else "❌ Not configured",
        inline=True
    )
    
    embed.add_field(
        name="Google APIs",
        value="✅ Connected" if evidence_bot.credentials else "❌ Not configured",
        inline=True
    )
    
    embed.add_field(
        name="Spreadsheet",
        value="✅ Configured" if evidence_bot.spreadsheet_id else "❌ Not configured",
        inline=True
    )
    
    embed.add_field(
        name="Document",
        value="✅ Configured" if evidence_bot.document_id else "❌ Not configured",
        inline=True
    )
    
    await ctx.send(embed=embed)


# Error handling
@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found. Use `!help_bot` to see available commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument. Use `!help_bot` for command usage.")
    else:
        logger.error(f'Command error: {error}')
        await ctx.send(f"An error occurred: {str(error)}")


# Main execution
if __name__ == '__main__':
    # Get Discord token
    discord_token = os.getenv('DISCORD_TOKEN')
    
    if not discord_token:
        logger.error("DISCORD_TOKEN not found in environment variables")
        exit(1)
    
    if not openai_client.api_key:
        logger.error("OPENAI_API_KEY not found in environment variables")
        exit(1)
    
    # Run the bot
    try:
        bot.run(discord_token)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as error:
        logger.error(f"Bot crashed: {error}")
