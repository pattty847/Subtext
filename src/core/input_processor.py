"""
Input processing for mixed URL and file path detection
"""
import re
from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple


class InputType(Enum):
    URL = "url"
    FILE = "file"
    INVALID = "invalid"


class InputProcessor:
    """Process and validate mixed input types"""
    
    # URL patterns
    URL_PATTERNS = [
        r'^https?://',  # http:// or https://
        r'^www\.',      # www.example.com
        r'^[a-zA-Z0-9-]+\.(com|org|net|io|co|tv|be|de|fr|uk)',  # domain.com
    ]
    
    # Supported media extensions (video + audio)
    MEDIA_EXTENSIONS = {
        '.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.3gp',
        '.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg', '.opus', '.wma', '.aiff', '.aif'
    }
    
    @staticmethod
    def detect_input_type(input_text: str) -> InputType:
        """Detect if input is URL, file path, or invalid"""
        input_text = input_text.strip()
        
        if not input_text:
            return InputType.INVALID
        
        # Check for URL patterns
        for pattern in InputProcessor.URL_PATTERNS:
            if re.match(pattern, input_text, re.IGNORECASE):
                return InputType.URL
        
        # Check if it's a file path
        path = Path(input_text)
        if path.exists() and path.is_file():
            # Check if it's a supported media file
            if path.suffix.lower() in InputProcessor.MEDIA_EXTENSIONS:
                return InputType.FILE
            return InputType.INVALID
        
        # Check if it looks like a file path (absolute or relative)
        if path.suffix.lower() in InputProcessor.MEDIA_EXTENSIONS:
            # Might be a file that doesn't exist yet, but has valid extension
            return InputType.FILE
        
        # Default to invalid
        return InputType.INVALID
    
    @staticmethod
    def parse_mixed_input(input_text: str) -> Dict[str, List[str]]:
        """Parse input containing URLs and file paths separated by semicolons or newlines"""
        result = {
            "urls": [],
            "files": [],
            "invalid": []
        }
        
        # Split by semicolon or newline
        items = re.split(r'[;\n]', input_text)
        
        for item in items:
            item = item.strip()
            if not item:
                continue
            
            input_type = InputProcessor.detect_input_type(item)
            
            if input_type == InputType.URL:
                result["urls"].append(item)
            elif input_type == InputType.FILE:
                # Validate file exists
                path = Path(item)
                if path.exists() and path.is_file():
                    result["files"].append(item)
                else:
                    result["invalid"].append(f"{item} (file not found)")
            else:
                result["invalid"].append(item)
        
        return result

    @staticmethod
    def parse_url_list(input_text: str) -> List[str]:
        """Extract direct HTTP(S) URLs from free-form pasted text."""
        urls: List[str] = []
        seen: set[str] = set()

        for match in re.finditer(r"https?://[^\s,;]+", input_text or "", re.IGNORECASE):
            url = match.group(0).strip().rstrip(").,;]")
            if url and url not in seen:
                urls.append(url)
                seen.add(url)

        return urls
    
    @staticmethod
    def validate_files(file_paths: List[str]) -> Tuple[List[Path], List[str]]:
        """Validate file paths and return (valid_paths, invalid_messages)"""
        valid = []
        invalid = []
        
        for file_path in file_paths:
            path = Path(file_path)
            if path.exists() and path.is_file():
                if path.suffix.lower() in InputProcessor.MEDIA_EXTENSIONS:
                    valid.append(path)
                else:
                    invalid.append(f"{file_path} (not a supported media file)")
            else:
                invalid.append(f"{file_path} (file not found)")
        
        return valid, invalid

