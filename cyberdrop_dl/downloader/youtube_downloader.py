from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from cyberdrop_dl.downloader.downloader import Downloader
if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager




class YoutubeDownloader(Downloader):
    def __init__(self, manager: Manager, domain: str):
        super().__init__(manager, domain)
    async def startup(self) -> None:
        """Starts the downloader"""
        self.client = self.manager.client_manager.youtube_session
        self._semaphore = asyncio.Semaphore(await self.manager.download_manager.get_download_limit(self.domain))


        # self.manager.path_manager.download_dir.mkdir(parents=True, exist_ok=True)
        # if self.manager.config_manager.settings_data['Sorting']['sort_downloads']:
        #     self.manager.path_manager.sorted_dir.mkdir(parents=True, exist_ok=True)