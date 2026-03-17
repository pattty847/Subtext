"""
Centralized path management for Subtext
"""
from pathlib import Path
import shutil


class ProjectPaths:
    """Centralized path management"""
    
    BASE_DIR = Path.cwd()
    ASSETS_DIR = BASE_DIR / "assets"
    
    # Content directories
    VIDEOS_DIR = ASSETS_DIR / "videos"
    TRANSCRIPTS_DIR = ASSETS_DIR / "transcripts"
    ANALYSIS_DIR = ASSETS_DIR / "analysis"
    LOGS_DIR = ASSETS_DIR / "logs"
    RUNTIME_DIR = ASSETS_DIR / "runtime"
    
    @classmethod
    def ensure_directories(cls):
        """Create all required directories"""
        for path in [
            cls.VIDEOS_DIR,
            cls.TRANSCRIPTS_DIR,
            cls.ANALYSIS_DIR,
            cls.LOGS_DIR,
            cls.RUNTIME_DIR,
        ]:
            path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def cleanup_old_structure(cls):
        """Remove old downloads/ folder structure"""
        old_downloads = cls.BASE_DIR / "downloads"
        if old_downloads.exists():
            try:
                shutil.rmtree(old_downloads)
                return True
            except Exception as e:
                print(f"Warning: Could not remove old downloads/ folder: {e}")
                return False
        return True
    
    @classmethod
    def initialize(cls):
        """Initialize folder structure (call on app startup)"""
        cls.ensure_directories()
        cls.cleanup_old_structure()

