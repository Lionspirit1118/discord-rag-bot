#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class EvidenceCollectionService:
    """
    Web service version of the Evidence Collection System
    Designed to run as a Flask API on Render
    """
    
    def __init__(self):
        """Initialize the service with environment variables"""
        self.discord_webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
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
    
    def _initialize_google_apis(self):
        """Initialize Google API clients using service account credentials"""
        try:
            # For Render deployment, credentials can be set as environment variable
            credentials_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            
            if credentials_json:
                # Parse JSON string from environment variable
                credentials_info = json.loads(credentials_json)
                self.credentials = Credentials.from_service_account_info(
                    credentials_info, scopes=self.scopes
                )
            else:
                # Fallback to file-based credentials for local development
                credentials_path = 'credentials.json'
                self.credentials = Credentials.from_service_account_file(
                    credentials_path, scopes=self.scopes
                )
            
            self.sheets_client = gspread.authorize(self.credentials)
            self.docs_service = build('docs', 'v1', credentials=self.credentials)
            self.translate_service = build('translate', 'v2', credentials=self.credentials)
            
            logger.info("Google APIs initialized successfully")
            
        except Exception as error:
            logger.error(f"Failed to initialize Google APIs: {error}")
            raise
    
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
        if not text or text.strip() == '':
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
    
    def get_latest_submissions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the latest submissions from Google Sheets
        
        Args:
            limit: Maximum number of submissions to return
            
        Returns:
            List of submission dictionaries
        """
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
    
    def process_submission(self, submission_data: Dict[str, Any], entry_number: int) -> Dict[str, Any]:
        """
        Process a single submission
        
        Args:
            submission_data: Structured submission data
            entry_number: Entry number for formatting
            
        Returns:
            Processing result
        """
        try:
            # Add to Google Docs
            docs_result = self.add_to_docs(entry_number, submission_data)
            
            # Send Discord notification
            discord_result = self.send_discord_notification(entry_number, submission_data)
            
            # Prepare structured data
            structured_entry = self.prepare_structured_data(submission_data, entry_number)
            self.structured_data.append(structured_entry)
            
            return {
                'success': True,
                'entry_number': entry_number,
                'docs_added': docs_result,
                'discord_sent': discord_result,
                'structured_data': structured_entry
            }
            
        except Exception as error:
            logger.error(f'Error processing submission: {error}')
            return {
                'success': False,
                'error': str(error)
            }
    
    def add_to_docs(self, entry_number: int, data: Dict[str, Any]) -> bool:
        """
        Add formatted content to Google Docs
        
        Args:
            entry_number: Entry number for formatting
            data: Structured submission data
            
        Returns:
            Success status
        """
        try:
            # Translate the quote
            original_quote = data['quote']
            translated_quote = self.translate_text(original_quote, 'ja', 'en')
            
            # Format content
            title_content = f"{entry_number}. {data['title']} ({data['submitter']})"
            
            # Format tags
            tags_content = f"#{data['submitter']}"
            
            if data['aff_tags'] and data['aff_tags'][0]:
                tags_content += " [AFF]"
                for tag in data['aff_tags']:
                    tags_content += f" #{tag}"
            
            if data['neg_tags'] and data['neg_tags'][0]:
                tags_content += " [NEG]"
                for tag in data['neg_tags']:
                    tags_content += f" #{tag}"
            
            # Format main content
            table_content = (
                f"[資料番号:{entry_number}] {data['update_date']}: {data['eng_source']}\n"
                f"{data['source_url']}\n\n"
                f"【Original (Japanese)】\n{original_quote}\n\n"
                f"【English Translation】\n{translated_quote}"
            )
            
            # In production, you would use Google Docs API to append content
            # For now, we'll log the formatted content
            logger.info(f"Formatted content for Google Docs: {data['title']}")
            
            return True
            
        except Exception as error:
            logger.error(f'Error adding to docs: {error}')
            return False
    
    def send_discord_notification(self, entry_number: int, data: Dict[str, Any]) -> bool:
        """
        Send notification to Discord channel
        
        Args:
            entry_number: Entry number for formatting
            data: Structured submission data
            
        Returns:
            Success status
        """
        try:
            if not self.discord_webhook_url:
                logger.warning("Discord webhook URL not configured")
                return False
            
            # Translate the quote
            original_quote = data['quote']
            translated_quote = self.translate_text(original_quote, 'ja', 'en')
            
            # Format tags
            tags_text = ""
            if data['aff_tags'] and data['aff_tags'][0]:
                tags_text += "[AFF]"
                for tag in data['aff_tags']:
                    tags_text += f"#{tag} "
            
            if data['aff_tags'] and data['aff_tags'][0] and data['neg_tags'] and data['neg_tags'][0]:
                tags_text += "\n"
            
            if data['neg_tags'] and data['neg_tags'][0]:
                tags_text += "[NEG]"
                for tag in data['neg_tags']:
                    tags_text += f"#{tag} "
            
            # Format attachment and remark
            attachment_text = "\n添付ファイル：\n"
            if data['attachment']:
                attachment_text += data['attachment']
            else:
                attachment_text += "なし"
            
            remark_text = ""
            if data['remark']:
                remark_text = f"\n※{data['remark']}"
            
            # Build notification message
            message_content = (
                f"\n{tags_text}\n\n"
                f"```{original_quote}```\n\n"
                f"**English Translation:**\n"
                f"```{translated_quote}```"
                f"{remark_text}"
                f"{attachment_text}\n\n"
                f"【投稿者】{data['submitter']}\n"
                f"【引用元】{data['update_date']}\n"
                f"{data['source_url']}"
            )
            
            # Send to Discord
            discord_payload = {
                'content': f"{entry_number}. {data['title']} ({data['submitter']})\n{message_content}",
                'tts': False
            }
            
            response = requests.post(
                self.discord_webhook_url,
                json=discord_payload,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 204:
                logger.info(f"Discord notification sent successfully for: {data['title']}")
                return True
            else:
                logger.error(f"Discord notification failed: {response.status_code}")
                return False
                
        except Exception as error:
            logger.error(f'Error sending Discord notification: {error}')
            return False
    
    def prepare_structured_data(self, data: Dict[str, Any], entry_number: int) -> Dict[str, Any]:
        """
        Prepare structured data for vector database
        
        Args:
            data: Structured submission data
            entry_number: Entry number
            
        Returns:
            Structured data object
        """
        # Translate content
        translated_title = self.translate_text(data['title'], 'ja', 'en')
        translated_quote = self.translate_text(data['quote'], 'ja', 'en')
        
        structured_entry = {
            'id': f"entry_{entry_number}",
            'timestamp': data['timestamp'],
            'submitter': data['submitter'],
            'title': {
                'original': data['title'],
                'translated': translated_title
            },
            'quote': {
                'original': data['quote'],
                'translated': translated_quote
            },
            'tags': {
                'affirmative': data['aff_tags'],
                'negative': data['neg_tags']
            },
            'source': {
                'url': data['source_url'],
                'update_date': data['update_date'],
                'eng_source': data['eng_source']
            },
            'metadata': {
                'attachment': data['attachment'],
                'remark': data['remark'],
                'processed_at': datetime.now().isoformat()
            }
        }
        
        return structured_entry


# Initialize the service
try:
    evidence_service = EvidenceCollectionService()
    logger.info("Evidence Collection Service initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize service: {e}")
    evidence_service = None


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service_initialized': evidence_service is not None
    })


@app.route('/api/submissions/latest', methods=['GET'])
def get_latest_submissions():
    """Get the latest submissions from Google Sheets"""
    if not evidence_service:
        return jsonify({'error': 'Service not initialized'}), 500
    
    try:
        limit = request.args.get('limit', 10, type=int)
        submissions = evidence_service.get_latest_submissions(limit)
        
        return jsonify({
            'submissions': submissions,
            'count': len(submissions),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as error:
        logger.error(f'Error in get_latest_submissions: {error}')
        return jsonify({'error': str(error)}), 500


@app.route('/api/submissions/process', methods=['POST'])
def process_submission():
    """Process a specific submission"""
    if not evidence_service:
        return jsonify({'error': 'Service not initialized'}), 500
    
    try:
        data = request.get_json()
        
        if not data or 'submission_data' not in data:
            return jsonify({'error': 'Invalid request data'}), 400
        
        submission_data = data['submission_data']
        entry_number = data.get('entry_number', 1)
        
        result = evidence_service.process_submission(submission_data, entry_number)
        
        return jsonify(result)
        
    except Exception as error:
        logger.error(f'Error in process_submission: {error}')
        return jsonify({'error': str(error)}), 500


@app.route('/api/submissions/batch-process', methods=['POST'])
def batch_process_submissions():
    """Process multiple submissions in batch"""
    if not evidence_service:
        return jsonify({'error': 'Service not initialized'}), 500
    
    try:
        # Get latest submissions and process them
        submissions = evidence_service.get_latest_submissions()
        
        results = []
        for submission in submissions:
            result = evidence_service.process_submission(
                submission, 
                submission.get('row_number', 1)
            )
            results.append(result)
        
        return jsonify({
            'processed': len(results),
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as error:
        logger.error(f'Error in batch_process_submissions: {error}')
        return jsonify({'error': str(error)}), 500


@app.route('/api/data/structured', methods=['GET'])
def get_structured_data():
    """Get structured data for vector database"""
    if not evidence_service:
        return jsonify({'error': 'Service not initialized'}), 500
    
    try:
        return jsonify({
            'structured_data': evidence_service.structured_data,
            'count': len(evidence_service.structured_data),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as error:
        logger.error(f'Error in get_structured_data: {error}')
        return jsonify({'error': str(error)}), 500


@app.route('/api/webhook/form-submit', methods=['POST'])
def form_submit_webhook():
    """
    Webhook endpoint for Google Forms to trigger processing
    This can be called directly from Google Apps Script or form submissions
    """
    if not evidence_service:
        return jsonify({'error': 'Service not initialized'}), 500
    
    try:
        data = request.get_json()
        
        # Extract form data from webhook payload
        if 'namedValues' in data:
            # Convert Google Forms namedValues format to our format
            named_values = data['namedValues']
            
            row_data = [
                named_values.get('タイムスタンプ', [''])[0],
                named_values.get('名前', [''])[0],
                named_values.get('title', [''])[0],
                named_values.get('AFF tags', [''])[0],
                named_values.get('NEG tags', [''])[0],
                named_values.get('URL of the Quotation', [''])[0],
                named_values.get('The source, Update date, and Time(引用元・更新日時)', [''])[0],
                named_values.get('Eng Source', [''])[0],
                named_values.get('Quoted text(引用本文)', [''])[0],
                named_values.get('Attachments(添付ファイル)', [''])[0],
                named_values.get('Remarks(備考)', [''])[0]
            ]
            
            submission_data = evidence_service.extract_submission_data(row_data)
            
            if submission_data:
                result = evidence_service.process_submission(submission_data, 1)
                return jsonify(result)
            else:
                return jsonify({'error': 'Failed to extract submission data'}), 400
        
        return jsonify({'error': 'Invalid webhook data format'}), 400
        
    except Exception as error:
        logger.error(f'Error in form_submit_webhook: {error}')
        return jsonify({'error': str(error)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)