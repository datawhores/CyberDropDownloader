from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem
from yt_dlp import YoutubeDL
if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.downloader.youtube_downloader import YoutubeDownloader


async def run_youtube_crawler(manager,scrape_item):
    try:
        crawler=YoutubeCrawler(manager)
        await crawler.startup()
        await crawler.run(scrape_item)
        return True
    except:
        return False



class YoutubeCrawler(Crawler):
    def __init__(self, manager:Manager):
        super().__init__(manager,"","")
    async def startup(self) -> None:
        """Starts the crawler"""
        self.client = self.manager.client_manager.youtube_session
        self.downloader = YoutubeDownloader(self.manager, self.domain)
        await self.downloader.startup()
    

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Runs yt-dlp"""
        self.set_youtube_dl_info(scrape_item)
        await self.handle_file(scrape_item)

    async def handle_file(self, scrape_item: ScrapeItem):
        if not await self.check_download(scrape_item):
            return True
        media_item=await self.get_media_item_via_info(scrape_item)
        await self.handle_file_send_downloader(media_item)
        return True
    async def check_download(self,scrape_item:ScrapeItem):
        url=URL(self.info_dict["webpage_url"])
        filename=self.info_dict["title"]
        if not await self.handle_file_check(url,scrape_item,filename):
            return False
        return True
    async def get_media_item_via_info(self, scrape_item: ScrapeItem)  :
        ext=f".{self.info_dict["ext"]}"
        url=URL(self.info_dict["webpage_url"])
        title=self.info_dict["title"]
        filename=f"{title}{ext}"
        media_item=await self.get_media_item(url,scrape_item,filename,ext)
        media_item.filesize=0
        return media_item
    
    def set_youtube_dl_info(self,scrape_item:ScrapeItem) ->dict:
        ydl = YoutubeDL({
        'quiet': True,
        'no_warnings': True,
        'overwrites':False,
        
        })
        with ydl:
        # Extract information
            info_dict = ydl.extract_info(str(scrape_item.url), download=False)
            domain=info_dict["extractor"]
            self.domain=domain.lower()
            self.folder_domain=domain
            self.info_dict=info_dict




      