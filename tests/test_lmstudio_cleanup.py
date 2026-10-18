"""Offline LM Studio must not interrupt service shutdown."""
import unittest
from unittest.mock import AsyncMock, patch

import lmstudio as lms
from src.web.llm.lmstudio import LMStudioProvider


class LMStudioCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_provider_does_not_abort_cleanup(self) -> None:
        provider = LMStudioProvider()
        with patch.object(provider, '_run', new=AsyncMock(side_effect=lms.LMStudioRuntimeError('Offline'))):
            await provider.unload_all()
