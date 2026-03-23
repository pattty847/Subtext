"""
Worker thread for AI analysis
"""
import asyncio

from PySide6.QtCore import QThread, Signal

from src.core.analyzer import DEFAULT_ANALYSIS_MODEL, OllamaAnalyzer


class AnalysisWorker(QThread):
    """Worker thread for AI analysis"""
    progress_updated = Signal(str)  # Progress message
    analysis_completed = Signal(object)  # AnalysisResult
    error_occurred = Signal(str)  # Error message
    
    def __init__(self, transcript: str, model: str = DEFAULT_ANALYSIS_MODEL):
        super().__init__()
        self.transcript = transcript
        self.model = model
        self.analyzer = OllamaAnalyzer(model)
        
    def run(self):
        """Run the AI analysis"""
        try:
            # Create event loop for async operations
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run analysis
            loop.run_until_complete(self.run_analysis())
            
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            if 'loop' in locals():
                loop.close()
                
    async def run_analysis(self):
        """Run the full analysis"""
        try:
            self.progress_updated.emit("🤖 Checking model availability...")
            
            # Ensure model is available
            if not await self.analyzer.ensure_model():
                available = await self.analyzer.list_available_models()
                details = ", ".join(available[:8]) if available else "none detected"
                raise Exception(f"Could not load model '{self.model}'. Available local models: {details}")
                
            self.progress_updated.emit("🔍 Running AI analysis...")
            
            # Run full analysis
            result = await self.analyzer.full_analysis(self.transcript)
            
            self.progress_updated.emit("✅ Analysis completed!")
            self.analysis_completed.emit(result)
            
        except Exception as e:
            self.error_occurred.emit(f"Analysis failed: {str(e)}")


class CustomAnalysisWorker(QThread):
    """Worker thread for custom one-off transcript analysis prompts."""
    progress_updated = Signal(str)
    analysis_completed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, transcript: str, model: str, prompt: str):
        super().__init__()
        self.transcript = transcript
        self.model = model
        self.prompt = prompt
        self.analyzer = OllamaAnalyzer(model)

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.run_custom())
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            if "loop" in locals():
                loop.close()

    async def run_custom(self):
        try:
            self.progress_updated.emit("🤖 Preparing custom analysis...")
            if not await self.analyzer.ensure_model():
                raise Exception(f"Could not load model: {self.model}")

            self.progress_updated.emit("🔍 Running custom prompt...")
            result = await self.analyzer.custom_analysis(self.transcript, self.prompt)
            self.analysis_completed.emit(result)
            self.progress_updated.emit("✅ Custom analysis completed!")
        except Exception as e:
            self.error_occurred.emit(f"Custom analysis failed: {str(e)}")


class InstallModelWorker(QThread):
    """Worker to install/pull a selected Ollama model."""
    progress_updated = Signal(str)
    install_completed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, model: str):
        super().__init__()
        self.model = model
        self.analyzer = OllamaAnalyzer(model)

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.run_install())
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            if "loop" in locals():
                loop.close()

    async def run_install(self):
        try:
            self.progress_updated.emit(f"Installing model '{self.model}'...")
            if not await self.analyzer.ensure_model():
                raise Exception(f"Could not install model '{self.model}'.")
            self.install_completed.emit(self.analyzer.model)
            self.progress_updated.emit(f"Model ready: {self.analyzer.model}")
        except Exception as e:
            self.error_occurred.emit(f"Model install failed: {str(e)}")


class ModelTestWorker(QThread):
    """Worker to run a minimal test inference against selected model."""
    progress_updated = Signal(str)
    test_completed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, model: str):
        super().__init__()
        self.model = model
        self.analyzer = OllamaAnalyzer(model)

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.run_test())
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            if "loop" in locals():
                loop.close()

    async def run_test(self):
        try:
            self.progress_updated.emit(f"Testing model '{self.model}'...")
            if not await self.analyzer.ensure_model():
                raise Exception(f"Could not load model '{self.model}'.")
            response = await self.analyzer.test_model_response()
            self.test_completed.emit(response)
            self.progress_updated.emit("Model test completed.")
        except Exception as e:
            self.error_occurred.emit(f"Model test failed: {str(e)}")

