from functools import partial
import asyncio
from pathlib import Path
from yt_dlp import YoutubeDL

from cyberdrop_dl.clients.download_client import DownloadClient

from cyberdrop_dl.managers.client_manager import ClientManager
from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem
from cyberdrop_dl.utils.utilities import log

class YoutubeClient(DownloadClient):
    def __init__(self, manager: Manager, client_manager: ClientManager):
        super().__init__(manager, client_manager)
    async def download_file(self, manager: Manager, domain: str, media_item: MediaItem) -> bool:
        """Starts a file"""
        if self.manager.config_manager.settings_data['Download_Options']['skip_download_mark_completed']:
            await log(f"Download Skip {media_item.url} due to mark completed option", 10)
            await self.manager.progress_manager.download_progress.add_skipped()
            #set completed path
            await self.mark_incomplete(media_item, domain)
            await self.process_completed(media_item, domain)
            return False
        downloaded = await self._download(domain, manager, media_item)
        if downloaded:
            await self.process_completed(media_item, domain)
            await  self.handle_media_item_completion(media_item,downloaded=True)
        return downloaded
    async def _download(self, domain: str, manager: Manager, media_item: MediaItem):
        downloaded_filename = await self.manager.db_manager.history_table.get_downloaded_filename(domain, media_item)
        download_dir = await self.get_download_dir(media_item)
        media_item.partial_file = download_dir / f"{downloaded_filename}.part"
        await asyncio.sleep(self.client_manager.download_delay)
        if not isinstance(media_item.complete_file, Path):
            proceed, skip = await self.get_final_file_info(media_item, domain)
            await self.mark_incomplete(media_item, domain)
            if skip:
                await self.manager.progress_manager.download_progress.add_skipped()
                return False
            if not proceed:
                await log(f"Skipping {media_item.url} as it has already been downloaded", 10)
                await self.manager.progress_manager.download_progress.add_previously_completed(False)
                await self.process_completed(media_item, domain)
                await  self.handle_media_item_completion(media_item,downloaded=False)
                return False
            await self.save_content(manager,media_item)
            return True
    async def save_content(self,manager,media_item) -> None:
            await self._append_content(media_item, partial(manager.progress_manager.file_progress.advance_file, media_item.task_id))
    async def _append_content(self, media_item,update_progress: partial):
        ydl_opts={
            "outtmpl":{"default":str(media_item.complete_file.absolute()),
           },
            "overwrites":False
        }
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([str(media_item.url)])

