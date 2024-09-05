from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem
from yt_dlp import YoutubeDL
if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class YoutubeCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "cyberfile", "Cyberfile")
        self.api_files = URL('https://cyberfile.me/account/ajax/load_files')
        self.api_details = URL('https://cyberfile.me/account/ajax/file_details')
        self.request_limiter = AsyncLimiter(5, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def run(self, item: ScrapeItem) -> None:
        try:
            await super().run(item)
            return True
        except:
            return False
    

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Runs yt-dlp"""
        info_dict=self.get_youtube_dl_info(scrape_item)
        #skip already downloaded
        await self.handle_file(scrape_item,info_dict)

    async def handle_file(self, scrape_item: ScrapeItem,info_dict:dict):
        if not await self.check_download(scrape_item, info_dict):
            return True
        media_item,filename=await self.get_media_item_and_filename(scrape_item,info_dict)
        download_filename=f"{str(media_item.download_folder)}/{filename}"
        download_url=str(scrape_item.url)
        _real_main(["-o",download_filename,"--continue",download_url])
        return True
    async def check_download(self,scrape_item:ScrapeItem,info_dict:dict):
        url=URL(info_dict["webpage_url"])
        filename=info_dict["title"]
        if not await self.handle_file_check(url,scrape_item,filename):
            return False
        return True
    async def get_media_item_and_filename(self, scrape_item: ScrapeItem,info_dict:dict)  :
  
        ext=info_dict["ext"]
        url=URL(info_dict["webpage_url"])
        filename=info_dict["title"]
        domain=info_dict["extractor"]
        self.domain=domain.lower()
        self.folder_domain=domain
        media_item=await self.get_media_item(url,scrape_item,filename,ext)
        return media_item,filename
    
    def get_youtube_dl_info(self,scrape_item:ScrapeItem) ->dict:
        ydl = YoutubeDL({
        'quiet': True,
        'no_warnings': True,
        
        })
        with ydl:
        # Extract information
            info_dict = ydl.extract_info(str(scrape_item.url), download=False)
            return info_dict




      