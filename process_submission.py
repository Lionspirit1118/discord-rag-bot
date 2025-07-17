#!/usr/bin/env python3
import os
import time
import json
import re
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class EvidenceCollectionSystem:
    """
    Main class for processing Google Form submissions, translating content,
    and distributing to Google Docs and Discord
    """
    
    def __init__(self, credentials_path: str, discord_webhook_url: str):
        """
        Initialize the evidence collection system
        
        Args:
            credentials_path: Path to Google service account credentials JSON
            discord_webhook_url: Discord webhook URL for notifications
        """
        self.credentials_path = credentials_path
        self.discord_webhook_url = discord_webhook_url
        
        # Google API scopes needed for Sheets, Docs, and Translate
        self.scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/cloud-translation'
        ]
        
        # Initialize Google API clients
        self.credentials = Credentials.from_service_account_file(
            credentials_path, scopes=self.scopes
        )
        self.sheets_client = gspread.authorize(self.credentials)
        self.docs_service = build('docs', 'v1', credentials=self.credentials)
        self.translate_service = build('translate', 'v2', credentials=self.credentials)
        
        # Track last processed row to avoid duplicates
        self.last_processed_row = 0
        
        # Store structured data for vector database
        self.structured_data = []
    
    def translate_text(self, text: str, source_lang: str = 'ja', target_lang: str = 'en') -> str:
        """
        Translate text using Google Translate API
        Replicates the translateText function from the original Apps Script
        
        Args:
            text: Text to translate
            source_lang: Source language code (default: 'ja')
            target_lang: Target language code (default: 'en')
            
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
            print(f'Translation error: {error}')
            return text
    
    def monitor_spreadsheet(self, spreadsheet_id: str, sheet_name: str = 'Responses') -> None:
        """
        Monitor Google Spreadsheet for new entries
        
        Args:
            spreadsheet_id: Google Sheets ID to monitor
            sheet_name: Name of the sheet to monitor (default: 'Responses')
        """
        try:
            spreadsheet = self.sheets_client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            
            # Get all rows
            all_rows = worksheet.get_all_values()
            
            if len(all_rows) <= 1:  # Only header row
                return
            
            # Process new rows since last check
            current_row_count = len(all_rows)
            
            if current_row_count > self.last_processed_row:
                # Process new rows
                for row_index in range(max(2, self.last_processed_row + 1), current_row_count + 1):
                    row_data = all_rows[row_index - 1]  # Convert to 0-based index
                    self.process_submission(row_data, row_index)
                
                self.last_processed_row = current_row_count
                
        except Exception as error:
            print(f'Error monitoring spreadsheet: {error}')
    
    def process_submission(self, row_data: List[str], row_number: int) -> None:
        """
        Process a single form submission
        Replicates the shareEvi function from the original Apps Script
        
        Args:
            row_data: List of form field values
            row_number: Row number in the spreadsheet
        """
        try:
            # Extract data from row (based on original getData function)
            submission_data = self.extract_submission_data(row_data)
            
            if not submission_data:
                return
            
            # Add to Google Docs
            self.add_to_docs(row_number - 1, submission_data)  # Adjust for numbering
            
            # Send Discord notification
            self.send_discord_notification(row_number - 1, submission_data)
            
            # Prepare structured data for vector database
            structured_entry = self.prepare_structured_data(submission_data, row_number)
            self.structured_data.append(structured_entry)
            
        except Exception as error:
            print(f'Error processing submission at row {row_number}: {error}')
    
    def extract_submission_data(self, row_data: List[str]) -> Optional[Dict[str, Any]]:
        """
        Extract and structure form submission data
        Based on the original getData function
        
        Args:
            row_data: Raw row data from spreadsheet
            
        Returns:
            Structured submission data dictionary
        """
        try:
            # Expected columns based on original form structure:
            # [Timestamp, Submitter, Title, AFF_tags, NEG_tags, SourceURL, UpdateDate, EngSource, Quote, Attachment, Remark]
            
            if len(row_data) < 11:
                print(f'Insufficient data in row: {len(row_data)} columns')
                return None
            
            # Parse tags (comma-separated values)
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
            print(f'Error extracting submission data: {error}')
            return None
    
    def add_to_docs(self, entry_number: int, data: Dict[str, Any]) -> None:
        """
        Add formatted content to Google Docs
        Replicates the addToDocs function from the original Apps Script
        
        Args:
            entry_number: Entry number for formatting
            data: Structured submission data
        """
        try:
            # This would need the document ID - in practice, you'd get this from configuration
            # For now, we'll prepare the content structure
            
            # Translate the quote
            original_quote = data['quote']
            translated_quote = self.translate_text(original_quote, 'ja', 'en')
            
            # Format content similar to original
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
            
            # Format the main content
            table_content = (
                f"[資料番号:{entry_number}] {data['update_date']}: {data['eng_source']}\n"
                f"{data['source_url']}\n\n"
                f"【Original (Japanese)】\n{original_quote}\n\n"
                f"【English Translation】\n{translated_quote}"
            )
            
            # Store formatted content for potential Google Docs API calls
            formatted_content = {
                'title': title_content,
                'tags': tags_content,
                'remark': data['remark'],
                'table_content': table_content,
                'attachment': data['attachment']
            }
            
            # In a real implementation, you would use the Google Docs API to append this content
            print(f"Content prepared for Google Docs: {data['title']}")
            
        except Exception as error:
            print(f'Error adding to docs: {error}')
    
    def send_discord_notification(self, entry_number: int, data: Dict[str, Any]) -> None:
        """
        Send notification to Discord channel
        Replicates the notify function from the original Apps Script
        
        Args:
            entry_number: Entry number for formatting
            data: Structured submission data
        """
        try:
            # Translate the quote for notification
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
            
            # Format attachment info
            attachment_text = "\n添付ファイル：\n"
            if data['attachment']:
                attachment_text += data['attachment']
            else:
                attachment_text += "なし"
            
            # Format remark
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
                print(f"Discord notification sent successfully for: {data['title']}")
            else:
                print(f"Discord notification failed: {response.status_code}")
                
        except Exception as error:
            print(f'Error sending Discord notification: {error}')
    
    def prepare_structured_data(self, data: Dict[str, Any], row_number: int) -> Dict[str, Any]:
        """
        Prepare structured data for vector database and RAG system
        
        Args:
            data: Structured submission data
            row_number: Row number in spreadsheet
            
        Returns:
            Structured data object for vector database
        """
        # Translate content for English search capabilities
        translated_title = self.translate_text(data['title'], 'ja', 'en')
        translated_quote = self.translate_text(data['quote'], 'ja', 'en')
        
        structured_entry = {
            'id': f"entry_{row_number}",
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
    
    def save_structured_data(self, output_path: str) -> None:
        """
        Save structured data to JSON file for vector database ingestion
        
        Args:
            output_path: Path to save the structured data JSON file
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.structured_data, f, ensure_ascii=False, indent=2)
            print(f"Structured data saved to: {output_path}")
        except Exception as error:
            print(f'Error saving structured data: {error}')
    
    def run_monitoring_loop(self, spreadsheet_id: str, interval_seconds: int = 60) -> None:
        """
        Run continuous monitoring loop
        
        Args:
            spreadsheet_id: Google Sheets ID to monitor
            interval_seconds: Polling interval in seconds
        """
        print(f"Starting monitoring loop for spreadsheet: {spreadsheet_id}")
        print(f"Polling interval: {interval_seconds} seconds")
        
        while True:
            try:
                self.monitor_spreadsheet(spreadsheet_id)
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                print("Monitoring stopped by user")
                break
            except Exception as error:
                print(f'Error in monitoring loop: {error}')
                time.sleep(interval_seconds)


def main():
    """
    Main function to run the evidence collection system
    """
    # Configuration - these would typically come from environment variables or config files
    credentials_path = 'path/to/your/service-account-credentials.json'
    discord_webhook_url = 'https://discord.com/api/webhooks/YOUR_WEBHOOK_URL'
    spreadsheet_id = 'YOUR_GOOGLE_SHEETS_ID'
    
    # Initialize the system
    evidence_system = EvidenceCollectionSystem(credentials_path, discord_webhook_url)
    
    # Run monitoring loop
    evidence_system.run_monitoring_loop(spreadsheet_id)


if __name__ == "__main__":
    main()